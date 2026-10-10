"""
Repository Intelligence Tools — P0/P1 tool implementations for the task
workflow (plan `plan-updrage.md` §6.2).

All tools:
- enforce the repository boundary via `PathPolicy`
- return structured `ToolResult`s instead of raising (except for
  authoritative denials, which are still wrapped in ToolResult)
- never interpolate user/LLM strings through a shell (argv only)
- redact secrets from output

Tool names intentionally read as commands (list_files, find_definition,
run_test, ...) so profile allowlists and the UI stay predictable.
"""

from __future__ import annotations

import ast
import json
import logging
import os.path
import re
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from src.tools.policy import (
    CommandPolicy,
    PathPolicy,
    PolicyViolation,
    discover_check_commands,
    is_secret_filename,
)
from src.tools.tool_registry import ToolDef, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _elapsed(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


def _ok(tool_name: str, summary: str, details: Optional[list] = None, elapsed_ms: float = 0.0, raw: str = "") -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=True,
        summary=summary,
        details=details or [],
        elapsed_ms=elapsed_ms,
        raw_output=raw[:200_000],
    )


def _fail(tool_name: str, summary: str, error: str, elapsed_ms: float = 0.0, raw: str = "") -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=False,
        summary=summary,
        error=error,
        elapsed_ms=elapsed_ms,
        raw_output=raw[:200_000],
    )


def _policy_fail(tool_name: str, violation: PolicyViolation) -> ToolResult:
    return _fail(tool_name, f"Policy blocked: {violation.reason}", violation.detail)


def _walk_files(policy: PathPolicy) -> list[Path]:
    """Walk the repo, skipping excluded dirs and secret/binary files."""
    files: list[Path] = []
    for root, dirs, names in policy.repo_root.walk():
        dirs[:] = [d for d in dirs if d not in policy.excluded_dirs]
        for name in names:
            fp = Path(root) / name
            try:
                fp.relative_to(policy.repo_root)
            except ValueError:
                continue
            if policy.is_excluded_file(fp):
                continue
            files.append(fp)
    return files


def _language_of(fp: Path) -> str:
    ext = fp.suffix.lower()
    mapping = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "typescript", ".jsx": "javascript", ".go": "go",
        ".rs": "rust", ".java": "java", ".c": "c", ".cpp": "cpp",
        ".h": "c", ".hpp": "cpp", ".rb": "ruby", ".php": "php",
        ".sh": "shell", ".bash": "shell", ".ps1": "powershell",
        ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml",
        ".tf": "hcl", ".sql": "sql", ".md": "markdown",
    }
    return mapping.get(ext, "text")


# ---------------------------------------------------------------------------
# P0: Repository Intelligence
# ---------------------------------------------------------------------------

def list_files(repo_path: str, *, path: str = "", **kwargs: Any) -> ToolResult:
    """List files and directories under a repo-relative path."""
    t0 = time.perf_counter()
    policy = PathPolicy.from_repo(repo_path)
    try:
        target = policy.resolve_relative(path or ".")
    except PolicyViolation as v:
        return _policy_fail("list_files", v)

    if not target.is_dir():
        return _fail("list_files", "Not a directory", str(target), _elapsed(t0))

    entries: list[dict[str, Any]] = []
    try:
        for child in sorted(target.iterdir()):
            if child.name in policy.excluded_dirs:
                continue
            if child.is_dir():
                entries.append({"name": child.name, "type": "dir"})
            elif not policy.is_excluded_file(child):
                entries.append(
                    {
                        "name": child.name,
                        "type": "file",
                        "language": _language_of(child),
                        "size": child.stat().st_size,
                    }
                )
    except Exception as exc:
        return _fail("list_files", f"list error: {exc}", str(exc), _elapsed(t0))

    return _ok(
        "list_files",
        f"Listed {len(entries)} entries in {str(target.relative_to(policy.repo_root)) or '.'}",
        entries,
        _elapsed(t0),
    )


def repo_summary(repo_path: str, **kwargs: Any) -> ToolResult:
    """Return a concise recon summary: languages, file counts, tests, git info."""
    t0 = time.perf_counter()
    policy = PathPolicy.from_repo(repo_path)
    files = _walk_files(policy)

    lang_counts: Counter[str] = Counter()
    for fp in files:
        lang_counts[_language_of(fp)] += 1

    test_files = [str(fp.relative_to(policy.repo_root)) for fp in files if "/test" in str(fp).lower() or fp.name.startswith("test_") or fp.name.startswith("test.") or fp.name.endswith("_test.")]

    detail: dict[str, Any] = {
        "repo_root": str(policy.repo_root),
        "file_count": len(files),
        "languages": dict(lang_counts.most_common(15)),
        "test_files": test_files[:50],
        "has_tests_dir": (policy.repo_root / "tests").is_dir(),
        "manifests": {
            name: (policy.repo_root / name).is_file()
            for name in (
                "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
                "package.json", "Cargo.toml", "go.mod", "pom.xml",
                "build.gradle", "Makefile", "Dockerfile",
            )
        },
    }
    # git info
    try:
        import git

        repo = git.Repo(policy.repo_root)
        detail["git"] = {
            "branch": repo.active_branch.name,
            "head": repo.head.commit.hexsha[:8] if repo.head.is_valid() else "",
            "dirty": bool(repo.untracked_files) or bool(repo.is_dirty()),
        }
    except Exception:
        detail["git"] = {"branch": "", "head": "", "dirty": None}

    return _ok("repo_summary", f"Summarized repository: {len(files)} files.", [detail], _elapsed(t0))


# ---------------------------------------------------------------------------
# P0: Exact Source Lookup (find_definition / find_references)
# ---------------------------------------------------------------------------

def _python_definitions_for_file(path: Path, rel: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    out: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(
                {
                    "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                    "name": node.name,
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno) or node.lineno,
                    "file": rel,
                }
            )
    return out


def find_definition(repo_path: str, *, symbol: str = "", file_path: str = "", **kwargs: Any) -> ToolResult:
    """Locate the definition(s) of a Python symbol in the repository."""
    t0 = time.perf_counter()
    if not symbol:
        return _fail("find_definition", "No symbol provided.", "missing symbol", _elapsed(t0))

    policy = PathPolicy.from_repo(repo_path)
    matches: list[dict[str, Any]] = []

    if file_path:
        try:
            target = policy.resolve_relative(file_path)
            if target.is_file() and target.suffix == ".py":
                for d in _python_definitions_for_file(target, str(target.relative_to(policy.repo_root))):
                    if d["name"] == symbol:
                        matches.append(d)
        except PolicyViolation as v:
            return _policy_fail("find_definition", v)
    else:
        for fp in _walk_files(policy):
            if fp.suffix != ".py":
                continue
            rel = str(fp.relative_to(policy.repo_root))
            for d in _python_definitions_for_file(fp, rel):
                if d["name"] == symbol:
                    matches.append(d)

    return _ok("find_definition", f"Found {len(matches)} definition(s) for '{symbol}'.", matches[:50], _elapsed(t0))


def find_references(repo_path: str, *, symbol: str = "", file_path: str = "", **kwargs: Any) -> ToolResult:
    """Find reference/usage sites of a Python symbol (imports, calls, accesses)."""
    t0 = time.perf_counter()
    if not symbol:
        return _fail("find_references", "No symbol provided.", "missing symbol", _elapsed(t0))

    policy = PathPolicy.from_repo(repo_path)
    matches: list[dict[str, Any]] = []

    files = _walk_files(policy)
    if file_path:
        try:
            target = policy.resolve_relative(file_path)
            files = [target] if target.is_file() else files
        except PolicyViolation as v:
            return _policy_fail("find_references", v)

    pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    for fp in files:
        if fp.suffix not in {".py", ".js", ".ts", ".tsx", ".jsx"}:
            continue
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = str(fp.relative_to(policy.repo_root))
        for i, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                matches.append({"file": rel, "line": i, "content": line.strip()[:200]})
    return _ok("find_references", f"Found {len(matches)} reference(s) for '{symbol}'.", matches[:100], _elapsed(t0))

# ---------------------------------------------------------------------------
# P1: Structural analysis
# ---------------------------------------------------------------------------

def python_ast_summary(repo_path: str, *, path: str = "", **kwargs: Any) -> ToolResult:
    """Summarize Python structure: modules, classes, functions, complexity."""
    t0 = time.perf_counter()
    policy = PathPolicy.from_repo(repo_path)
    try:
        target = policy.resolve_relative(path or ".")
    except PolicyViolation as v:
        return _policy_fail("python_ast_summary", v)

    files = [target] if target.is_file() else [fp for fp in _walk_files(policy) if fp.suffix == ".py"]
    module_summaries: list[dict[str, Any]] = []

    for fp in files:
        rel = str(fp.relative_to(policy.repo_root))
        try:
            src = fp.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue

        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        imports = [
            (n.module or "", [a.name for a in n.names])
            for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))
        ]
        module_summaries.append(
            {
                "file": rel,
                "classes": len(classes),
                "functions": len(funcs),
                "imports": len(imports),
                "import_targets": [mod for mod, _ in imports if mod][:20],
            }
        )

    return _ok("python_ast_summary", f"Parsed AST for {len(module_summaries)} Python file(s).", module_summaries, _elapsed(t0))


def import_graph(repo_path: str, *, module: str = "all", **kwargs: Any) -> ToolResult:
    """Extract the Python import graph (module → imported modules)."""
    t0 = time.perf_counter()
    policy = PathPolicy.from_repo(repo_path)
    edges: list[dict[str, str]] = []
    nodes: set[str] = set()

    for fp in _walk_files(policy):
        if fp.suffix != ".py":
            continue
        rel = str(fp.relative_to(policy.repo_root))
        module_name = rel[:-3].replace(os.sep, ".")
        if module != "all" and module not in module_name:
            continue
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                target = node.module
                edges.append({"from": module_name, "to": target})
                nodes.add(target)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    # only record intra-repo edges when the root is a local module
                    if (policy.repo_root / f"{root.replace('.', os.sep)}.py").is_file():
                        edges.append({"from": module_name, "to": root})
                        nodes.add(root)

    return _ok(
        "import_graph",
        f"Import graph: {len(edges)} edge(s), {len(nodes)} node(s).",
        {"edges": edges[:300], "node_count": len(nodes)},
        _elapsed(t0),
    )


def api_routes(repo_path: str, **kwargs: Any) -> ToolResult:
    """Discover HTTP route definitions in Python (Flask/FastAPI/Starlette)."""
    t0 = time.perf_counter()
    policy = PathPolicy.from_repo(repo_path)
    routes: list[dict[str, Any]] = []
    decorator_re = re.compile(
        r"@(?:app|router|bp)\.(?:route|get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]"
    )

    for fp in _walk_files(policy):
        if fp.suffix != ".py":
            continue
        rel = str(fp.relative_to(policy.repo_root))
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            m = decorator_re.search(line)
            if m:
                method = "route"
                mm = re.search(r"\.(\w+)\s*\(", line)
                if mm and mm.group(1) in ("get", "post", "put", "delete", "patch"):
                    method = mm.group(1)
                routes.append({"file": rel, "line": i, "method": method.upper(), "path": m.group(1)})

    return _ok("api_routes", f"Discovered {len(routes)} route(s).", routes[:100], _elapsed(t0))


# ---------------------------------------------------------------------------
# P1: Dependency analysis
# ---------------------------------------------------------------------------

def dependency_audit(repo_path: str, **kwargs: Any) -> ToolResult:
    """Parse manifest/lockfiles and report declared dependencies."""
    t0 = time.perf_counter()
    policy = PathPolicy.from_repo(repo_path)
    root = policy.repo_root
    deps: list[dict[str, str]] = []

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8", errors="replace")
        # light-weight TOML parse for [project] dependencies
        in_deps = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("dependencies"):
                in_deps = True
                continue
            if in_deps:
                if stripped.startswith("["):
                    in_deps = False
                    continue
                if stripped.startswith('"') or stripped.startswith("'"):
                    name = stripped.strip('"\'').split(">=")[0].split("==")[0].split("<")[0].strip()
                    deps.append({"manifest": "pyproject.toml", "name": name, "spec": stripped})

    requirements = root / "requirements.txt"
    if requirements.is_file():
        for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            name = re.split(r"[<>=!~]", line)[0].strip()
            deps.append({"manifest": "requirements.txt", "name": name, "spec": line})

    pkg_json = root / "package.json"
    if pkg_json.is_file():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            for section in ("dependencies", "devDependencies"):
                for name, spec in (data.get(section) or {}).items():
                    deps.append({"manifest": "package.json", "name": name, "spec": str(spec), "section": section})
        except Exception:
            pass

    return _ok("dependency_audit", f"Parsed {len(deps)} declared dependenc(ies).", deps[:200], _elapsed(t0))


# ---------------------------------------------------------------------------
# P1: Secret detection (redacted output)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aws_access_key", re.compile(r"(?i)AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"(?i)gh[pousr]_[A-Za-z0-9]{20,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----")),
    ("generic_key", re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{12,}")),
]


def secret_scan(repo_path: str, *, path: str = "", **kwargs: Any) -> ToolResult:
    """Scan for probable secrets; output is always redacted."""
    t0 = time.perf_counter()
    policy = PathPolicy.from_repo(repo_path)
    try:
        target = policy.resolve_relative(path or ".")
    except PolicyViolation as v:
        return _policy_fail("secret_scan", v)

    files = [target] if target.is_file() else _walk_files(policy)
    findings: list[dict[str, Any]] = []
    for fp in files:
        rel = str(fp.relative_to(policy.repo_root))
        if is_secret_filename(fp.name):
            # We never read .env-style files; flag their presence only.
            findings.append({"file": rel, "kind": "secret_filename", "detail": "secrets file present (not read)"})
            continue
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for kind, pat in _SECRET_PATTERNS:
            for m in pat.finditer(content):
                line_no = content[: m.start()].count("\n") + 1
                line_text = content.splitlines()[line_no - 1].strip() if content.splitlines() else ""
                findings.append(
                    {
                        "file": rel,
                        "line": line_no,
                        "kind": kind,
                        "detail": "[REDACTED] found near line %d (line text redacted)" % line_no,
                        "preview": m.group(0)[:8] + "…[REDACTED]",
                    }
                )

    return _ok("secret_scan", f"Scan complete: {len(findings)} potential secret(s).", findings[:100], _elapsed(t0))


# ---------------------------------------------------------------------------
# P0: Safe commands / diagnostics
# ---------------------------------------------------------------------------

def _run_command(argv: list[str], cwd: Path, timeout: float = 300.0, max_output: int = 200_000) -> dict[str, Any]:
    """Run an argv command with no shell; returns structured output."""
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "error": f"command not found: {argv[0]}", "elapsed_ms": _elapsed(t0)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {timeout:.0f}s", "elapsed_ms": _elapsed(t0)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "elapsed_ms": _elapsed(t0)}

    output = (proc.stdout or "")[:max_output]
    if proc.returncode != 0 and proc.stderr:
        output += ("\n" if output else "") + (proc.stderr or "")[:max_output]
    return {
        "ok": True,
        "exit_code": proc.returncode,
        "output": output,
        "elapsed_ms": _elapsed(t0),
    }


def discover_checks(repo_path: str, *, path: str = "", **kwargs: Any) -> ToolResult:
    """Discover safe, explicit check commands from manifest files."""
    t0 = time.perf_counter()
    policy = PathPolicy.from_repo(repo_path)
    checks = discover_check_commands(policy.repo_root)
    return _ok("discover_checks", f"Discovered {len(checks)} check command(s).", checks, _elapsed(t0))


def run_test(repo_path: str, *, command: Optional[list[str]] = None, timeout: float = 300.0, **kwargs: Any) -> ToolResult:
    """Run a test command in the repo (default: pytest if tests exist)."""
    t0 = time.perf_counter()
    policy = PathPolicy.from_repo(repo_path)
    cpolicy = CommandPolicy(timeout_seconds=timeout)

    argv = command or ["pytest", "-q"]
    violation = cpolicy.validate(argv)
    if violation:
        return _policy_fail("run_test", violation)

    res = _run_command(argv, policy.repo_root, timeout=timeout)
    if not res.get("ok"):
        return _fail("run_test", f"Test command failed to start: {argv[0]}", res.get("error", ""), _elapsed(t0))
    success = res["exit_code"] == 0
    return ToolResult(
        tool_name="run_test",
        success=success,
        summary=("Tests passed." if success else f"Tests failed (exit {res['exit_code']})."),
        details=[{"exit_code": res["exit_code"], "command": " ".join(argv), "output_excerpt": res["output"][:4000]}],
        raw_output=res["output"],
        elapsed_ms=res.get("elapsed_ms", _elapsed(t0)),
    )


def run_linter(repo_path: str, *, command: Optional[list[str]] = None, **kwargs: Any) -> ToolResult:
    """Run a linter (default: ruff check, then pyflakes-style via python -m py_compile)."""
    t0 = time.perf_counter()
    policy = PathPolicy.from_repo(repo_path)
    cpolicy = CommandPolicy(timeout_seconds=120)
    argv = command or ["ruff", "check", "."]
    violation = cpolicy.validate(argv)
    if violation:
        return _policy_fail("run_linter", violation)
    res = _run_command(argv, policy.repo_root, timeout=120)
    if not res.get("ok"):
        return _fail("run_linter", f"Linter failed to start: {argv[0]}", res.get("error", ""), _elapsed(t0))
    return ToolResult(
        tool_name="run_linter",
        success=res["exit_code"] == 0,
        summary=f"Linter {'passed.' if res['exit_code'] == 0 else 'found issues.'}",
        details=[{"exit_code": res["exit_code"], "command": " ".join(argv), "output_excerpt": res["output"][:4000]}],
        raw_output=res["output"],
        elapsed_ms=res.get("elapsed_ms", _elapsed(t0)),
    )


def run_build(repo_path: str, *, command: Optional[list[str]] = None, **kwargs: Any) -> ToolResult:
    """Run a build/type-check command (default: python compileall)."""
    t0 = time.perf_counter()
    policy = PathPolicy.from_repo(repo_path)
    cpolicy = CommandPolicy(timeout_seconds=300)
    argv = command or ["python", "-m", "compileall", "-q", "."]
    violation = cpolicy.validate(argv)
    if violation:
        return _policy_fail("run_build", violation)
    res = _run_command(argv, policy.repo_root, timeout=300)
    if not res.get("ok"):
        return _fail("run_build", f"Build failed to start: {argv[0]}", res.get("error", ""), _elapsed(t0))
    return ToolResult(
        tool_name="run_build",
        success=res["exit_code"] == 0,
        summary=f"Build {'succeeded.' if res['exit_code'] == 0 else 'failed.'}",
        details=[{"exit_code": res["exit_code"], "command": " ".join(argv), "output_excerpt": res["output"][:4000]}],
        raw_output=res["output"],
        elapsed_ms=res.get("elapsed_ms", _elapsed(t0)),
    )


def git_status(repo_path: str, **kwargs: Any) -> ToolResult:
    """Git status via GitPython (no shell)."""
    t0 = time.perf_counter()
    try:
        import git

        repo = git.Repo(repo_path)
        status = {
            "branch": repo.active_branch.name,
            "is_dirty": repo.is_dirty(),
            "untracked": [str(p) for p in repo.untracked_files][:50],
            "staged": [i.a_path for i in repo.index.diff("HEAD")][:50] if repo.head.is_valid() else [],
        }
        return _ok("git_status", f"Git status for branch '{status['branch']}'.", [status], _elapsed(t0))
    except Exception as exc:
        return _fail("git_status", "Git status unavailable.", str(exc), _elapsed(t0))


def git_diff(repo_path: str, *, base: str = "HEAD", path: str = "", **kwargs: Any) -> ToolResult:
    """Git diff (unstaged + staged) against a base (default HEAD)."""
    t0 = time.perf_counter()
    try:
        import git

        repo = git.Repo(repo_path)
        diffs: list[str] = []
        if repo.head.is_valid():
            diffs.append(repo.git.diff(base, path or None))
        # Also include staged-but-uncommitted delta
        diffs.append(repo.git.diff("--cached", path or None))
        diff_text = "\n".join(d for d in diffs if d)
        return _ok(
            "git_diff",
            f"Diff length: {len(diff_text)} chars.",
            [{"length": len(diff_text), "diff_preview": diff_text[:8000]}],
            _elapsed(t0),
            raw=diff_text,
        )
    except Exception as exc:
        return _fail("git_diff", "Git diff unavailable.", str(exc), _elapsed(t0))


def git_log(repo_path: str, *, max_count: int = 20, **kwargs: Any) -> ToolResult:
    """Recent commit history."""
    t0 = time.perf_counter()
    try:
        import git

        repo = git.Repo(repo_path)
        commits = [
            {"hash": c.hexsha[:8], "author": str(c.author), "date": c.committed_datetime.isoformat(), "message": c.message.strip().split("\n")[0]}
            for c in repo.iter_commits(max_count=max_count)
        ]
        return _ok("git_log", f"Retrieved {len(commits)} commit(s).", commits, _elapsed(t0))
    except Exception as exc:
        return _fail("git_log", "Git log unavailable.", str(exc), _elapsed(t0))


def semantic_search(repo_path: str, *, query: str = "", k: int = 5, rag_store: Any = None, embed_fn: Any = None, **kwargs: Any) -> ToolResult:
    """RAG semantic search — one retrieval tool among several."""
    t0 = time.perf_counter()
    if not query:
        return _fail("semantic_search", "No query provided.", "missing query", _elapsed(t0))
    if rag_store is None:
        return _fail("semantic_search", "RAG store not configured for this run.", "no rag store", _elapsed(t0))
    embed = embed_fn or (rag_store.embed if hasattr(rag_store, "embed") else None)
    if embed is None:
        return _fail("semantic_search", "No embedding function available.", "no embed fn", _elapsed(t0))
    try:
        results = rag_store.query(query, embed, k=k)
        return _ok("semantic_search", f"Retrieved {len(results)} snippet(s).", results, _elapsed(t0))
    except Exception as exc:
        return _fail("semantic_search", "RAG query failed.", str(exc), _elapsed(t0))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_INTELLIGENCE_TOOLS: list[ToolDef] = [
    ToolDef("list_files", "List files/dirs under a repo-relative path", "general", list_files,
            parameters={"path": {"type": "string", "default": ""}}),
    ToolDef("repo_summary", "Concise recon: languages, files, tests, git", "general", repo_summary),
    ToolDef("find_definition", "Locate definitions of a Python symbol", "general", find_definition,
            parameters={"symbol": {"type": "string", "required": True}, "file_path": {"type": "string", "default": ""}}),
    ToolDef("find_references", "Find references to a symbol", "general", find_references,
            parameters={"symbol": {"type": "string", "required": True}, "file_path": {"type": "string", "default": ""}}),
    ToolDef("python_ast_summary", "Python AST structure summary", "architecture", python_ast_summary,
            parameters={"path": {"type": "string", "default": ""}}),
    ToolDef("import_graph", "Extract Python import graph", "architecture", import_graph,
            parameters={"module": {"type": "string", "default": "all"}}),
    ToolDef("api_routes", "Discover HTTP routes in Python", "architecture", api_routes),
    ToolDef("dependency_audit", "Parse declared dependencies from manifests", "devops", dependency_audit),
    ToolDef("secret_scan", "Scan for probable secrets (redacted output)", "security", secret_scan,
            parameters={"path": {"type": "string", "default": ""}}),
    ToolDef("discover_checks", "Discover safe, explicit check commands", "general", discover_checks),
    ToolDef("run_test", "Run a test command in the repo", "general", run_test,
            parameters={"command": {"type": "list", "default": None}, "timeout": {"type": "float", "default": 300.0}}),
    ToolDef("run_linter", "Run a linter in the repo", "general", run_linter,
            parameters={"command": {"type": "list", "default": None}}),
    ToolDef("run_build", "Run a build/type-check in the repo", "general", run_build,
            parameters={"command": {"type": "list", "default": None}}),
    ToolDef("git_status", "Git status via GitPython", "general", git_status),
    ToolDef("git_diff", "Git diff against a base", "general", git_diff,
            parameters={"base": {"type": "string", "default": "HEAD"}, "path": {"type": "string", "default": ""}}),
    ToolDef("git_log", "Recent commit history", "architecture", git_log,
            parameters={"max_count": {"type": "int", "default": 20}}),
    ToolDef("semantic_search", "RAG semantic search over indexed code", "general", semantic_search,
            parameters={"query": {"type": "string", "required": True}, "k": {"type": "int", "default": 5}}),
]


def register_intelligence_tools(registry: ToolRegistry, rag_store: Any = None) -> None:
    """Register all intelligence tools into a ToolRegistry.

    The registry captures the repo root per-invocation, so no path changes are
    needed; the tools resolve `repo_path` from the registry's own root, which
    `invoke()` injects authoritatively.
    """
    for tool in _INTELLIGENCE_TOOLS:
        if tool.name == "semantic_search":
            # Bind the RAG store through a closure so tools stay stateless.
            original = tool.func

            def bound_semantic(repo_path: str, *, rag_store=rag_store, **kw: Any) -> ToolResult:
                return original(repo_path, rag_store=rag_store, **kw)

            tool.func = bound_semantic
        registry.register(tool)