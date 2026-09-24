"""
Check Runner — discovers allowed checks and runs them against a worktree,
producing structured `VerificationResult`s (plan `plan-updrage.md` §6.2 and
§8 "Verification must record exactly what ran...").

A passing final result requires all mandatory checks to pass; missing
prerequisites are `blocked`, never silently treated as success.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from src.execution.executor import Executor
from src.models.artifacts import VerificationResult, new_id, now_iso
from src.tools.policy import CommandPolicy, discover_check_commands

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

class CheckAdapter:
    """Base adapter: knows how to build a command and judge its output."""

    name: str = "unknown"

    def build_command(self, discovery: dict[str, Any]) -> list[str]:
        raise NotImplementedError

    def summarize(self, exit_code: int, output: str) -> str:
        if exit_code == 0:
            return "passed"
        last_lines = [l for l in (output or "").splitlines() if l.strip()][-5:]
        return f"exit={exit_code}; " + " | ".join(last_lines)[:300]


class AdapterRegistry:
    """Map a discovered check to an adapter by name/marker."""

    def __init__(self) -> None:
        self._adapters: dict[str, CheckAdapter] = {}

    def register(self, adapter: CheckAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def adapter_for(self, name: str) -> Optional[CheckAdapter]:
        return self._adapters.get(name)


# Built-in adapters ---------------------------------------------------------

class PytestAdapter(CheckAdapter):
    name = "pytest"

    def build_command(self, discovery: dict[str, Any]) -> list[str]:
        # `python -m pytest` (not bare `pytest`) so rootdir imports like
        # `from app import ...` resolve on pytest 8 / Python 3.13.
        return ["python", "-m", "pytest", "-q", "tests"]


class NpmScriptAdapter(CheckAdapter):
    name = "npm-script"

    def build_command(self, discovery: dict[str, Any]) -> list[str]:
        return discovery.get("command") or ["npm", "run", "check"]


class CargoAdapter(CheckAdapter):
    name = "cargo"

    def build_command(self, discovery: dict[str, Any]) -> list[str]:
        return discovery.get("command") or ["cargo", "test", "--quiet"]


class GoAdapter(CheckAdapter):
    name = "go"

    def build_command(self, discovery: dict[str, Any]) -> list[str]:
        return discovery.get("command") or ["go", "test", "./..."]


class MavenAdapter(CheckAdapter):
    name = "mvn"

    def build_command(self, discovery: dict[str, Any]) -> list[str]:
        return discovery.get("command") or ["mvn", "-q", "test"]


class GradleAdapter(CheckAdapter):
    name = "gradle"

    def build_command(self, discovery: dict[str, Any]) -> list[str]:
        return discovery.get("command") or ["gradle", "test"]


class CompileAllAdapter(CheckAdapter):
    """Python syntax/byte-compile check (no deps needed)."""

    name = "compileall"

    def build_command(self, discovery: dict[str, Any]) -> list[str]:
        return ["python", "-m", "compileall", "-q", "."]


class RuffAdapter(CheckAdapter):
    name = "ruff"

    def build_command(self, discovery: dict[str, Any]) -> list[str]:
        return ["ruff", "check", "."]


class BanditAdapter(CheckAdapter):
    name = "bandit"

    def build_command(self, discovery: dict[str, Any]) -> list[str]:
        return ["bandit", "-r", ".", "-q"]


class SemgrepAdapter(CheckAdapter):
    name = "semgrep"

    def build_command(self, discovery: dict[str, Any]) -> list[str]:
        return ["semgrep", "scan", "--config", "auto", "--json", "."]


DEFAULT_ADAPTERS: list[CheckAdapter] = [
    PytestAdapter(),
    NpmScriptAdapter(),
    CargoAdapter(),
    GoAdapter(),
    MavenAdapter(),
    GradleAdapter(),
    CompileAllAdapter(),
    RuffAdapter(),
    BanditAdapter(),
    SemgrepAdapter(),
]


# ---------------------------------------------------------------------------
# Check runner
# ---------------------------------------------------------------------------

class CheckRunner:
    """Runs discovered checks against a worktree via the Executor."""

    def __init__(
        self,
        worktree_path: str,
        *,
        adapters: Optional[list[CheckAdapter]] = None,
        policy: Optional[CommandPolicy] = None,
        artifact_dir: Optional[str | Path] = None,
        mandatory: Optional[list[str]] = None,
    ) -> None:
        self.worktree_path = worktree_path
        self.adapter_registry = AdapterRegistry()
        for adapter in (adapters or DEFAULT_ADAPTERS):
            self.adapter_registry.register(adapter)
        self.executor = Executor(worktree_path, policy=policy)
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        # Tools that are likely not installed should still be attempted, but a
        # missing binary is `blocked`, not a pass or fail.
        self.mandatory: set[str] = set(mandatory or [])

    # ------------------------------------------------------------------

    def _pick_adapter(self, discovery: dict[str, Any]) -> Optional[CheckAdapter]:
        """Pick the adapter by the command's base or the check's name."""
        name = discovery.get("name", "")
        command = discovery.get("command", [])
        base = (command[0] if command else "").split("/")[-1].lower()

        for key in (name, base):
            if key and self.adapter_registry.adapter_for(key):
                return self.adapter_registry.adapter_for(key)
        # Fallback: compileall for python manifests, npm for package.json
        if "pyproject.toml" == discovery.get("marker"):
            return self.adapter_registry.adapter_for("compileall")
        return self.adapter_registry.adapter_for(base) or CompileAllAdapter()

    def _write_artifact(self, check_id: str, payload: dict[str, Any]) -> str:
        if self.artifact_dir is None:
            return ""
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        out = self.artifact_dir / f"{check_id}.json"
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return str(out)

    def run_check(self, discovery: dict[str, Any], *, timeout: float = 300.0) -> VerificationResult:
        """Run one discovered check and return a structured VerificationResult."""
        check_id = new_id("check")
        name = discovery.get("name", "unknown")
        adapter = self._pick_adapter(discovery)
        command = adapter.build_command(discovery) if adapter else discovery.get("command", [])

        res = self.executor.run(command, timeout=timeout)

        if not res.get("ok"):
            status = "blocked"
            summary = f"command could not start: {res.get('error', '')}"
            exit_code = None
        else:
            exit_code = res.get("exit_code")
            if exit_code == 0:
                status = "passed"
                summary = adapter.summarize(0, "") if adapter else "passed"
            elif exit_code in (127, 2, 9009) or "command not found" in (res.get("stderr") or ""):
                status = "blocked"
                summary = "tool not found in this environment"
            else:
                status = "failed"
                summary = adapter.summarize(exit_code, res.get("stdout", "") + res.get("stderr", "")) if adapter else f"exit={exit_code}"

        # Mandatory checks must pass for the final gate.
        if name in self.mandatory and status == "blocked":
            status = "failed"

        result = VerificationResult(
            check_id=check_id,
            name=name,
            command=command,
            status=status,
            exit_code=exit_code,
            summary=summary[:1000],
            output_path=self._write_artifact(
                check_id,
                {
                    "check_id": check_id,
                    "name": name,
                    "command": command,
                    "status": status,
                    "exit_code": exit_code,
                    "summary": summary,
                    "stdout": res.get("stdout", ""),
                    "stderr": res.get("stderr", ""),
                    "elapsed_ms": res.get("elapsed_ms", 0.0),
                    "observed_at": now_iso(),
                },
            ),
        )
        logger.info("[CheckRunner] %s -> %s (exit=%s)", name, status, exit_code)
        return result

    def discover(self) -> list[dict[str, Any]]:
        """Discover safe checks from the worktree manifest files."""
        return discover_check_commands(self.worktree_path)

    def run_all(
        self,
        *,
        only: Optional[list[str]] = None,
        max_checks: int = 10,
        timeout: float = 300.0,
    ) -> list[VerificationResult]:
        """Discover + run checks, returning all VerificationResults.

        Missing prerequisites are recorded as `blocked` and never silently
        counted as success (plan §8).
        """
        discovered = self.discover()
        results: list[VerificationResult] = []
        ran = 0
        for d in discovered[:max_checks]:
            if only and d.get("name") not in only:
                continue
            results.append(self.run_check(d, timeout=timeout))
            ran += 1
        # If nothing was discovered, run a conservative default set so the
        # task is never silently "verified" without any check.
        if ran == 0:
            for default in self._default_checks():
                results.append(self.run_check(default, timeout=timeout))
        return results

    def _default_checks(self) -> list[dict[str, Any]]:
        defaults: list[dict[str, Any]] = []
        if (Path(self.worktree_path) / "tests").is_dir():
            defaults.append({"name": "pytest", "command": ["python", "-m", "pytest", "-q", "tests"], "marker": "default"})
        defaults.append({"name": "compileall", "command": ["python", "-m", "compileall", "-q", "."], "marker": "default"})
        return defaults

    def passed_all(self, results: list[VerificationResult]) -> bool:
        """True when every result is passed (blocked/failed ⇒ not verified)."""
        return bool(results) and all(r["status"] == "passed" for r in results)