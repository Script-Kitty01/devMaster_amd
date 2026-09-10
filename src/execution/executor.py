"""
Executor — command execution abstraction (plan §8 "Sandbox executor").

`LocalWorktreeExecutor` in `worktree.py` is the first-MVP implementation; the
`ContainerExecutor` is a documented later step.  This module re-exports the
interface and adds the command-policy guard so every command that runs under
a worktree passes through validation first.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from src.tools.policy import CommandPolicy, PolicyViolation
from src.execution.worktree import LocalWorktreeExecutor, WorktreeResult, WorktreeManager

logger = logging.getLogger(__name__)


# Re-export for convenience and interface parity.
__all__ = ["LocalWorktreeExecutor", "WorktreeManager", "WorktreeResult", "Executor", "CommandPolicy"]


class Executor:
    """
    Facade over the worktree-based executor with policy enforcement.

    Usage:
        executor = Executor(worktree_path=wt.path, policy=CommandPolicy())
        result = executor.run(["pytest", "-q"])
    """

    def __init__(
        self,
        worktree_path: str,
        policy: Optional[CommandPolicy] = None,
    ) -> None:
        self._inner = LocalWorktreeExecutor(worktree_path)
        self.policy = policy or CommandPolicy()

    def run(self, argv: list[str], *, timeout: float = 300.0) -> dict[str, Any]:
        violation: Optional[PolicyViolation] = self.policy.validate(argv)
        if violation is not None:
            return {
                "ok": False,
                "error": f"policy blocked: {violation.reason}",
                "command": argv,
                "violation": violation.to_mapping(),
            }
        return self._inner.run(argv, timeout=timeout)