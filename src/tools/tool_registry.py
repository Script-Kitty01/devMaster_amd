"""
Tool Registry — defines and manages all tools agents can invoke.

Tools:
- run_bandit: Python security scanning
- run_semgrep: Multi-language pattern scanning
- analyze_git: Git history analysis
- validate_dockerfile: Dockerfile best-practice checks
- profile_rocm: Parse ROCm profiler output
- search_code: Regex search across repo
- read_file: Read a specific file from the repo
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool Result
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """Standardized result from any tool invocation."""

    tool_name: str
    success: bool
    summary: str
    details: list[dict[str, Any]] = field(default_factory=list)
    raw_output: str = ""
    elapsed_ms: float = 0.0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Tool Definition
# ---------------------------------------------------------------------------

@dataclass
class ToolDef:
    """Metadata for a registered tool."""

    name: str
    description: str
    category: str  # "security", "performance", "architecture", "devops", "general"
    func: Callable[..., ToolResult]
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

def _run_bandit(repo_path: str, **kwargs: Any) -> ToolResult:
    """Run Bandit security scanner on a Python repository."""
    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            ["bandit", "-r", repo_path, "-f", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        elapsed = (time.perf_counter() - t0) * 1000

        if result.returncode not in (0, 1):  # 1 = issues found (expected)
            return ToolResult(
                tool_name="bandit",
                success=False,
                summary="Bandit execution failed",
                raw_output=result.stderr,
                elapsed_ms=elapsed,
                error=result.stderr,
            )

        import json

        data = json.loads(result.stdout) if result.stdout else {"results": []}
        issues = data.get("results", [])

        details = []
        for issue in issues:
            details.append(
                {
                    "severity": issue.get("issue_severity", "unknown"),
                    "confidence": issue.get("issue_confidence", "unknown"),
                    "test": issue.get("test_name", ""),
                    "file": issue.get("filename", ""),
                    "line": issue.get("line_number", 0),
                    "code": issue.get("code", ""),
                    "message": issue.get("issue_text", ""),
                }
            )

        return ToolResult(
            tool_name="bandit",
            success=True,
            summary=f"Bandit found {len(details)} issue(s) across the codebase.",
            details=details,
            raw_output=result.stdout[:5000],
            elapsed_ms=elapsed,
        )

    except FileNotFoundError:
        return ToolResult(
            tool_name="bandit",
            success=False,
            summary="Bandit is not installed.",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error="bandit not found in PATH",
        )
    except Exception as exc:
        return ToolResult(
            tool_name="bandit",
            success=False,
            summary=f"Bandit error: {exc}",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )


def _run_semgrep(repo_path: str, *, config: str = "auto", **kwargs: Any) -> ToolResult:
    """Run Semgrep on the repository."""
    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            ["semgrep", "scan", "--config", config, "--json", repo_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        elapsed = (time.perf_counter() - t0) * 1000

        import json

        data = json.loads(result.stdout) if result.stdout else {"results": []}
        findings = data.get("results", [])

        details = []
        for f in findings:
            details.append(
                {
                    "severity": f.get("extra", {}).get("severity", "unknown"),
                    "check_id": f.get("check_id", ""),
                    "file": f.get("path", ""),
                    "line": f.get("start", {}).get("line", 0),
                    "message": f.get("extra", {}).get("message", ""),
                }
            )

        return ToolResult(
            tool_name="semgrep",
            success=True,
            summary=f"Semgrep found {len(details)} finding(s).",
            details=details,
            raw_output=result.stdout[:5000],
            elapsed_ms=elapsed,
        )

    except FileNotFoundError:
        return ToolResult(
            tool_name="semgrep",
            success=False,
            summary="Semgrep is not installed.",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error="semgrep not found in PATH",
        )
    except Exception as exc:
        return ToolResult(
            tool_name="semgrep",
            success=False,
            summary=f"Semgrep error: {exc}",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )


def _analyze_git(repo_path: str, **kwargs: Any) -> ToolResult:
    """Analyze git history for churn, contributors, and recent changes."""
    t0 = time.perf_counter()
    try:
        import git

        repo = git.Repo(repo_path)

        # Recent commits
        commits = list(repo.iter_commits(max_count=20))
        commit_details = [
            {
                "hash": c.hexsha[:8],
                "author": str(c.author),
                "date": c.committed_datetime.isoformat(),
                "message": c.message.strip().split("\n")[0],
            }
            for c in commits
        ]

        # Top changed files
        churn: dict[str, int] = {}
        for commit in commits[:50]:
            if commit.parents:
                diffs = commit.parents[0].diff(commit, create_patch=False)
                for d in diffs:
                    path = d.a_path or d.b_path or ""
                    churn[path] = churn.get(path, 0) + 1

        top_churn = sorted(churn.items(), key=lambda x: x[1], reverse=True)[:10]

        return ToolResult(
            tool_name="git_analyzer",
            success=True,
            summary=f"Analyzed {len(commits)} recent commits. Top churn: {len(top_churn)} files.",
            details=[
                {"type": "recent_commits", "data": commit_details},
                {"type": "top_churn", "data": [{"file": f, "changes": c} for f, c in top_churn]},
            ],
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    except ImportError:
        return ToolResult(
            tool_name="git_analyzer",
            success=False,
            summary="GitPython not installed.",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error="gitpython not installed",
        )
    except Exception as exc:
        return ToolResult(
            tool_name="git_analyzer",
            success=False,
            summary=f"Git analysis error: {exc}",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )


def _validate_dockerfile(repo_path: str, **kwargs: Any) -> ToolResult:
    """Check Dockerfiles for best practices."""
    t0 = time.perf_counter()

    dockerfiles = list(Path(repo_path).rglob("Dockerfile*"))
    if not dockerfiles:
        return ToolResult(
            tool_name="dockerfile_validator",
            success=True,
            summary="No Dockerfiles found in repository.",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Best-practice checks
    checks = {
        "uses_pin_version": (r"FROM\s+\S+:\S+", "Base image should be pinned to a specific version"),
        "no_latest": (r"FROM\s+\S+:latest", "Avoid using ':latest' tag — pin to a specific version"),
        "uses_copy_not_add": (r"\bADD\s+", "Prefer COPY over ADD for simple file copies"),
        "has_healthcheck": (r"HEALTHCHECK", "Consider adding a HEALTHCHECK instruction"),
        "runs_as_nonroot": (r"USER\s+(?!root\b)\S+", "Container should run as non-root user"),
        "multi_stage": (r"FROM\s+\S+\s+AS\s+", "Consider multi-stage builds to reduce image size"),
        "no_secrets_in_env": (r"ENV\s+\S*(SECRET|PASSWORD|TOKEN|KEY)\S*\s*=", "Avoid hardcoding secrets in ENV"),
    }

    details = []
    for df in dockerfiles:
        content = df.read_text(encoding="utf-8", errors="replace")
        df_findings = {"file": str(df.relative_to(repo_path)), "checks": []}

        for check_name, (pattern, advice) in checks.items():
            matches = re.findall(pattern, content, re.IGNORECASE)
            if check_name.startswith("no_") or check_name.startswith("uses_"):
                # These are "bad if found" checks
                if matches and not check_name.startswith("uses_"):
                    df_findings["checks"].append(
                        {"check": check_name, "status": "warning", "advice": advice, "matches": matches[:5]}
                    )
                elif check_name.startswith("uses_") and not matches:
                    df_findings["checks"].append(
                        {"check": check_name, "status": "warning", "advice": advice}
                    )
            else:
                # These are "good if found" checks
                if not matches:
                    df_findings["checks"].append(
                        {"check": check_name, "status": "info", "advice": advice}
                    )
                else:
                    df_findings["checks"].append(
                        {"check": check_name, "status": "ok", "advice": advice}
                    )

        details.append(df_findings)

    total_warnings = sum(
        1 for d in details for c in d["checks"] if c["status"] == "warning"
    )

    return ToolResult(
        tool_name="dockerfile_validator",
        success=True,
        summary=f"Checked {len(dockerfiles)} Dockerfile(s). Found {total_warnings} warning(s).",
        details=details,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


def _search_code(repo_path: str, *, pattern: str = "", file_pattern: str = "*", **kwargs: Any) -> ToolResult:
    """Regex search across repository files."""
    t0 = time.perf_counter()

    if not pattern:
        return ToolResult(
            tool_name="code_search",
            success=False,
            summary="No search pattern provided.",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error="missing pattern",
        )

    matches = []
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
        repo = Path(repo_path)

        for fp in repo.rglob(file_pattern):
            if not fp.is_file():
                continue
            if any(skip in fp.parts for skip in {".git", "__pycache__", "node_modules", ".venv"}):
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    if compiled.search(line):
                        matches.append(
                            {
                                "file": str(fp.relative_to(repo)),
                                "line": i,
                                "content": line.strip()[:200],
                            }
                        )
            except Exception:
                continue

    except re.error as exc:
        return ToolResult(
            tool_name="code_search",
            success=False,
            summary=f"Invalid regex: {exc}",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )

    return ToolResult(
        tool_name="code_search",
        success=True,
        summary=f"Found {len(matches)} match(es) for '{pattern}'.",
        details=matches[:50],
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


def _read_file(repo_path: str, *, file_path: str = "", start_line: int = 1, end_line: int = 0, **kwargs: Any) -> ToolResult:
    """Read a specific file (or range) from the repository."""
    t0 = time.perf_counter()

    if not file_path:
        return ToolResult(
            tool_name="read_file",
            success=False,
            summary="No file path provided.",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error="missing file_path",
        )

    full_path = Path(repo_path) / file_path
    if not full_path.exists():
        return ToolResult(
            tool_name="read_file",
            success=False,
            summary=f"File not found: {file_path}",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error="file not found",
        )

    try:
        lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if end_line == 0:
            end_line = len(lines)
        start = max(0, start_line - 1)
        end = min(len(lines), end_line)
        snippet = "\n".join(lines[start:end])

        return ToolResult(
            tool_name="read_file",
            success=True,
            summary=f"Read {file_path}: lines {start_line}-{end} ({len(snippet)} chars).",
            details=[{"file": file_path, "start_line": start_line, "end_line": end, "content": snippet}],
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as exc:
        return ToolResult(
            tool_name="read_file",
            success=False,
            summary=f"Error reading {file_path}: {exc}",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    r"""
    Registry of all available tools that agents can invoke.

    Usage:
        registry = ToolRegistry(repo_path="/path/to/repo")
        result = registry.invoke("bandit")
        result = registry.invoke("code_search", pattern="eval\(")
    """

    def __init__(self, repo_path: str) -> None:
        self.repo_path = repo_path
        self._tools: dict[str, ToolDef] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register all built-in tools."""
        self.register(
            ToolDef(
                name="bandit",
                description="Run Bandit static security scanner on Python code",
                category="security",
                func=_run_bandit,
                parameters={"repo_path": {"type": "string", "required": True}},
            )
        )
        self.register(
            ToolDef(
                name="semgrep",
                description="Run Semgrep multi-language pattern scanner",
                category="security",
                func=_run_semgrep,
                parameters={
                    "repo_path": {"type": "string", "required": True},
                    "config": {"type": "string", "default": "auto"},
                },
            )
        )
        self.register(
            ToolDef(
                name="git_analyzer",
                description="Analyze git history for churn, contributors, and recent changes",
                category="architecture",
                func=_analyze_git,
                parameters={"repo_path": {"type": "string", "required": True}},
            )
        )
        self.register(
            ToolDef(
                name="dockerfile_validator",
                description="Validate Dockerfiles against best practices",
                category="devops",
                func=_validate_dockerfile,
                parameters={"repo_path": {"type": "string", "required": True}},
            )
        )
        self.register(
            ToolDef(
                name="code_search",
                description="Regex search across repository files",
                category="general",
                func=_search_code,
                parameters={
                    "repo_path": {"type": "string", "required": True},
                    "pattern": {"type": "string", "required": True},
                    "file_pattern": {"type": "string", "default": "*"},
                },
            )
        )
        self.register(
            ToolDef(
                name="read_file",
                description="Read a specific file or line range from the repository",
                category="general",
                func=_read_file,
                parameters={
                    "repo_path": {"type": "string", "required": True},
                    "file_path": {"type": "string", "required": True},
                    "start_line": {"type": "int", "default": 1},
                    "end_line": {"type": "int", "default": 0},
                },
            )
        )

    def register(self, tool: ToolDef) -> None:
        """Register a new tool."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s (%s)", tool.name, tool.category)

    def invoke(self, tool_name: str, **kwargs: Any) -> ToolResult:
        """Invoke a tool by name with the given arguments."""
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                summary=f"Unknown tool: {tool_name}",
                error=f"Tool '{tool_name}' not registered",
            )

        # Always inject repo_path
        kwargs.setdefault("repo_path", self.repo_path)

        logger.info("Invoking tool: %s with args: %s", tool_name, {k: str(v)[:80] for k, v in kwargs.items()})
        result = tool.func(**kwargs)
        result.tool_name = tool_name
        return result

    def list_tools(self, category: Optional[str] = None) -> list[ToolDef]:
        """List all registered tools, optionally filtered by category."""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    def get_tool(self, name: str) -> Optional[ToolDef]:
        """Get a specific tool definition."""
        return self._tools.get(name)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
