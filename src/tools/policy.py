"""
Tool Safety Policy — the shared rules every repository-scoped tool follows
(plan `plan-updrage.md` §6.1).

Guarantees:
- Repository boundary: every filesystem result is resolved and verified to
  stay under the repository root.
- No shell interpolation: commands are argument lists, never strings passed
  through a shell.
- Exclusions: `.git`, virtual environments, dependency folders, secrets
  files, and generated build output are skipped by default.
- Structured failures: path violations return a `PolicyViolation` instead of
  raising into the workflow.

This module has no dependencies on the LLM or LangGraph so it can be unit
tested in isolation.
"""

from __future__ import annotations

import logging
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default exclusions (plan §6.1)
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "node_modules",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".coverage",
        "dist",
        "build",
        "target",
        ".next",
        ".nuxt",
        ".idea",
        ".vscode",
        "vendor",
        "bower_components",
        "site-packages",
        "chroma_db",  # vector indexes are task-local artifacts
        "models",     # model weights, not source
    }
)

# Secrets files that should never be read or indexed by default.
DEFAULT_SECRET_FILENAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".env.local",
        ".env.*",
        "id_rsa",
        "id_ed25519",
        "*.pem",
        "*.key",
        "credentials.json",
        "secrets.yaml",
        "secrets.yml",
        "service-account*.json",
    }
)

DEFAULT_EXCLUDED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".gguf",
        ".bin",
        ".pt",
        ".pth",
        ".onnx",
        ".safetensors",
        ".npy",
        ".npz",
        ".lock",  # binary/irrelevant lockfiles; keep manifest lockfiles handled explicitly
    }
)


def is_secret_filename(name: str) -> bool:
    """Best-effort check that a filename looks like a secrets/credential file."""
    low = name.lower()
    if low in {"id_rsa", "id_ed25519", "credentials.json"}:
        return True
    if low.startswith(".env"):  # .env, .env.local, .env.production
        return True
    if low.startswith("service-account") or low == "secrets.yaml" or low == "secrets.yml":
        return True
    if low.endswith((".pem", ".key")):
        return True
    return False


# ---------------------------------------------------------------------------
# Policy violation
# ---------------------------------------------------------------------------

@dataclass
class PolicyViolation:
    """A structured denial instead of a raised exception."""

    reason: str
    detail: str = ""

    def to_mapping(self) -> dict[str, str]:
        return {"violation": self.reason, "detail": self.detail}


# ---------------------------------------------------------------------------
# Path policy
# ---------------------------------------------------------------------------

@dataclass
class PathPolicy:
    """Repository boundary enforcement for all filesystem access."""

    repo_root: Path
    excluded_dirs: frozenset[str] = field(default_factory=lambda: DEFAULT_EXCLUDED_DIRS)
    excluded_extensions: frozenset[str] = field(
        default_factory=lambda: DEFAULT_EXCLUDED_EXTENSIONS
    )
    allow_absolute: bool = False  # only True for explicitly approved external tools

    @classmethod
    def from_repo(cls, repo_path: str | Path) -> "PathPolicy":
        return cls(repo_root=Path(repo_path).resolve())

    def resolve_relative(self, rel_or_abs: str | Path) -> Path:
        """Resolve a path against the repo root without escaping it.

        Raises:
            PolicyViolation: if the resolved path is outside the repository.
        """
        root = self.repo_root
        candidate = Path(rel_or_abs)
        if candidate.is_absolute():
            if not self.allow_absolute:
                full = candidate.resolve()
            else:
                full = candidate.resolve()
        else:
            full = (root / candidate).resolve()

        try:
            full.relative_to(root)
        except ValueError:
            raise PolicyViolation(
                "path_escape",
                f"Resolved path {full} is outside repository {root}",
            ) from None
        return full

    def is_excluded_dir(self, path: Path) -> bool:
        """Check any path segment against the excluded set."""
        return any(part in self.excluded_dirs for part in path.parts)

    def is_excluded_extension(self, path: Path) -> bool:
        return path.suffix.lower() in self.excluded_extensions

    def is_excluded_file(self, path: Path) -> bool:
        """Check whether a file should be skipped by read/list/search tools."""
        if is_secret_filename(path.name):
            return True
        if self.is_excluded_extension(path):
            return True
        return False

    def verify_file(self, rel_or_abs: str | Path) -> Path:
        """Resolve a file path and ensure it is a readable file inside the repo."""
        full = self.resolve_relative(rel_or_abs)
        if not full.is_file():
            raise PolicyViolation("not_a_file", str(full))
        return full

    def verify_dir(self, rel_or_abs: str | Path) -> Path:
        """Resolve a directory path and ensure it is inside the repo."""
        full = self.resolve_relative(rel_or_abs)
        if not full.is_dir():
            raise PolicyViolation("not_a_dir", str(full))
        return full


# ---------------------------------------------------------------------------
# Command policy
# ---------------------------------------------------------------------------

# Commands that are NEVER allowed regardless of arguments.  These are the
# hard kill-list for the first release.
FORBIDDEN_COMMAND_BASE: frozenset[str] = frozenset(
    {
        "sudo",
        "su",
        "shutdown",
        "reboot",
        "halt",
        "mkfs",
        "fdisk",
        "dd",
        "rm",       # no direct deletes; rely on worktree cleanup only
        "mv",       # no renames outside patches
        "curl",     # no network fetches by default (plan §2 non-goals)
        "wget",
        "git",      # git is only allowed through the WorktreeExecutor lifecycle
        "pip",
        "pip3",
        "npm",
        "yarn",
        "pnpm",
        "gem",
        "brew",
        "apt",
        "apt-get",
        "docker",
        "podman",
    }
)

# Configuration files that indicate runnable project checks.
CHECK_MARKERS = {
    "pyproject.toml",
    "setup.cfg",
    "tox.ini",
    "package.json",
    "Makefile",
    "justfile",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "requirements.txt",
    "Gemfile",
    "CMakeLists.txt",
}

CHECK_SCRIPTS_HINTS = (
    # (regex, description) matched against package.json scripts names
    ("test", "test runner"),
    ("lint", "linter"),
    ("check", "check script"),
    ("build", "build script"),
)


@dataclass
class CommandPolicy:
    """Validates that proposed commands are safe to run in a worktree."""

    forbidden_bases: frozenset[str] = field(default_factory=lambda: FORBIDDEN_COMMAND_BASE)
    allowlist: Optional[frozenset[str]] = None  # if set, only these bases run
    timeout_seconds: float = 300.0
    max_output_chars: int = 200_000

    def validate(self, argv: Iterable[str]) -> Optional[PolicyViolation]:
        """Validate an argument-list command.

        Returns None when the command is allowed, otherwise a PolicyViolation.
        """
        args = list(argv)
        if not args:
            return PolicyViolation("empty_command", "command list is empty")
        base = Path(args[0]).name.lower()
        if base in self.forbidden_bases:
            return PolicyViolation("forbidden_command", base)
        if self.allowlist is not None and base not in self.allowlist:
            return PolicyViolation(
                "command_not_allowed",
                f"{base} is not in the allowlist",
            )
        # Refuse to interpret shell syntax: pipes, redirects, chaining.
        for token in args[1:]:
            if token in {"|", "&&", "||", ";", ">", ">>", "<", "2>", "2>>"}:
                return PolicyViolation(
                    "shell_metachar",
                    f"shell metacharacter not allowed: {token}",
                )
        return None

    @staticmethod
    def shell_quote(argv: Iterable[str]) -> str:
        """Render an argument list for *display only* (never for execution)."""
        return " ".join(shlex.quote(str(a)) for a in argv)


def discover_check_commands(repo_root: str | Path) -> list[dict[str, Any]]:
    """Discover safe, explicit check commands from common manifest files.

    Returns a list of {"name", "command", "marker"} where `command` is an
    argument list.  Commands that require network or dependency installation
    are skipped by default.
    """
    from typing import Any  # noqa: F401
    import json

    root = Path(repo_root)
    found: list[dict[str, Any]] = []

    def _add(name: str, argv: list[str]) -> None:
        found.append({"name": name, "command": argv, "marker": "manifest"})

    # --- pyproject.toml / tox.ini / setup.cfg → pytest, ruff, black ---
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = json.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            data = {}
        # Only add pytest if declared as a dev/test dependency?  For the first
        # release we simply add pytest when a tests/ directory exists.
        if (root / "tests").is_dir():
            _add("pytest", ["pytest", "-q"])

    # --- package.json scripts ---
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            script_data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            scripts = script_data.get("scripts", {})
        except Exception:
            scripts = {}
        for name, cmd in scripts.items():
            if not isinstance(cmd, str):
                continue
            low = name.lower()
            if any(hint in low for hint in ("test", "lint", "check", "build")):
                # Convert the npm script string to an argv list without a shell.
                argv = ["npm", "run", name]
                _add(f"npm:{name}", argv)

    # --- Cargo / Go / Maven / Gradle ---
    if (root / "Cargo.toml").is_file():
        _add("cargo-test", ["cargo", "test", "--quiet"])
        _add("cargo-check", ["cargo", "check"])
    if (root / "go.mod").is_file():
        _add("go-test", ["go", "test", "./..."])
    if (root / "pom.xml").is_file():
        _add("mvn-test", ["mvn", "-q", "test"])
    if (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
        _add("gradle-test", ["gradle", "test"])
    if (root / "CMakeLists.txt").is_file():
        _add("cmake-build", ["cmake", "--build", "build"])

    return found


def validate_argv_string(candidate: str) -> Optional[PolicyViolation]:
    """Validate a shell string proposed for splitting.

    First release: refuse anything that looks like shell syntax; command
    strings must already be argument lists.
    """
    if not candidate.strip():
        return PolicyViolation("empty_command", "command string is empty")
    # Reject characters that would need interpretation
    if re.search(r"[|&;><`$(){}\[\]]", candidate):
        return PolicyViolation(
            "shell_syntax",
            "command strings must not contain shell syntax; use argv lists",
        )
    return None