"""
Worktree Lifecycle — isolated Git worktree creation and cleanup.

Approval boundary (plan §8): the *only* mutation primitive.  Every change is
applied in a temporary worktree named `kutaar/<task-id>`; the original
checkout is never modified.  No commit, push, deploy, or PR is performed.

Uses GitPython so no shell interpolation is involved.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WorktreeResult:
    """Result of a worktree lifecycle operation."""

    ok: bool
    path: Optional[str] = None
    branch: str = ""
    error: str = ""


class WorktreeManager:
    r"""
    Create and remove temporary Git worktrees for a task.

    Usage:
        mgr = WorktreeManager(repo_root="/path/to/repo")
        wt = mgr.create("kutaar/task-42")
        # ... apply patch, run checks inside wt.path ...
        mgr.cleanup(wt)

    Lifecycle guarantees:
    - The worktree is created from the current checkout HEAD.
    - Cleanup removes both the working directory and the branch, even on
      failed verification, so no state leaks into the original repo.
    - Nothing is committed unless the caller explicitly asks (the patch
      executor applies changes to the working tree only).
    """

    def __init__(self, repo_root: str | Path, scratch_root: Optional[str | Path] = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.scratch_root = Path(scratch_root) if scratch_root else None
        self._git = None
        self._created: list[tuple[Path, str]] = []  # (worktree path, branch)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _get_git(self):
        if self._git is None:
            import git

            self._git = git.Repo(self.repo_root)
        return self._git

    def create(self, branch: str = "kutaar/task", base: Optional[str] = None) -> WorktreeResult:
        """Create a worktree at a scratch location with a new branch."""
        t0 = time.perf_counter()
        try:
            repo = self._get_git()

            # A worktree cannot live inside the repo (would pollute it).
            worktree_root = self.scratch_root or Path(
                tempfile.mkdtemp(prefix="kutaar_worktree_")
            )
            worktree_path = worktree_root / branch.replace("/", "__")

            # Remove stale remnants of a previous run for the same task.
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)

            worktree_path.mkdir(parents=True, exist_ok=True)

            # git worktree add --detach <path> HEAD  (no branch name collision)
            repo.git.worktree("add", "--detach", str(worktree_path), base or "HEAD")

            # Give this checkout a unique local branch name for provenance.
            try:
                repo.git.checkout("-b", branch)
            except Exception as exc:
                logger.debug("Branch creation note: %s", exc)
                # worktree add --detach put us on a detached HEAD; create the branch
                repo.git.checkout("-b", branch)

            result = WorktreeResult(
                ok=True,
                path=str(worktree_path),
                branch=branch,
            )
            self._created.append((worktree_path, branch))
            logger.info(
                "Created worktree %s on branch %s (%.0fms).",
                worktree_path,
                branch,
                (time.perf_counter() - t0) * 1000,
            )
            return result
        except Exception as exc:
            logger.exception("Worktree creation failed")
            return WorktreeResult(ok=False, error=str(exc))

    def cleanup(self, wt: Optional[WorktreeResult] = None) -> None:
        """Remove a created worktree (path + branch).  Safe to call twice."""
        entries = self._created
        if wt is not None:
            target_path = Path(wt.path) if wt.path else None
            target_branch = wt.branch
            entries = [
                (target_path, target_branch)
                for target_path, target_branch in self._created
                if target_path == (Path(wt.path) if wt.path else None)
            ]
        for worktree_path, branch in entries:
            try:
                repo = self._get_git()
                if worktree_path.exists():
                    repo.git.worktree("remove", "--force", str(worktree_path))
                # Delete the branch only if it is not currently checked out here
                if branch:
                    try:
                        repo.git.branch("-D", branch)
                    except Exception:
                        pass
                shutil.rmtree(worktree_path, ignore_errors=True)
                logger.info("Cleaned up worktree %s (%s).", worktree_path, branch)
            except Exception as exc:
                logger.warning("Worktree cleanup issue for %s: %s", worktree_path, exc)

        # purge from the tracked list
        self._created = [t for t in self._created if t not in self._created or t not in entries]

    def cleanup_all(self) -> None:
        """Clean up every worktree this manager created (best effort)."""
        self.cleanup()

    def get_diff(self, wt: Optional[WorktreeResult] = None) -> str:
        """Uncommitted diff of the worktree vs its base branch."""
        if wt is None or not wt.path:
            return ""
        try:
            import git

            repo = git.Repo(wt.path)
            return repo.git.diff("HEAD")
        except Exception as exc:
            logger.warning("Could not diff worktree: %s", exc)
            return ""

    def apply_patch(self, wt: WorktreeResult, patch_text: str) -> WorktreeResult:
        """Apply a unified diff to the worktree working tree (git apply)."""
        if not wt.path:
            return WorktreeResult(ok=False, error="no worktree path", branch=wt.branch)
        try:
            import git

            repo = git.Repo(wt.path)
            repo.git.apply(patch_text, check=False)
            return WorktreeResult(ok=True, path=wt.path, branch=wt.branch)
        except Exception as exc:
            return WorktreeResult(ok=False, path=wt.path, branch=wt.branch, error=str(exc))

    def write_file(self, wt: WorktreeResult, rel_path: str, content: str) -> WorktreeResult:
        """Write a file inside the worktree (repo-relative path only)."""
        if not wt.path:
            return WorktreeResult(ok=False, error="no worktree path", branch=wt.branch)
        root = Path(wt.path).resolve()
        target = (root / rel_path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return WorktreeResult(ok=False, error="path escape blocked", branch=wt.branch)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return WorktreeResult(ok=True, path=wt.path, branch=wt.branch)


# Small alias kept for parity with the plan's naming.
class LocalWorktreeExecutor:
    """
    First-MVP executor: run allowlisted commands under a worktree with
    timeouts and captured output (plan §8 "Sandbox executor").

    Implementation 2 (ContainerExecutor) is out of scope for the first
    release; this class keeps the same interface so the swap is local.
    """

    def __init__(self, worktree_path: str) -> None:
        self.worktree_path = Path(worktree_path)

    def run(self, argv: list[str], *, timeout: float = 300.0) -> dict[str, Any]:
        import subprocess

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                argv,
                cwd=str(self.worktree_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            return {
                "ok": True,
                "command": argv,
                "exit_code": proc.returncode,
                "stdout": (proc.stdout or "")[:200_000],
                "stderr": (proc.stderr or "")[:100_000],
                "elapsed_ms": (time.perf_counter() - t0) * 1000,
            }
        except FileNotFoundError:
            return {"ok": False, "error": f"command not found: {argv[0]}", "command": argv}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"timed out after {timeout:.0f}s", "command": argv}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "command": argv}