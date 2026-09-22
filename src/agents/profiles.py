"""
Capability Profiles — the supported engineering roles and their tool
permissions (plan `plan-updrage.md` §4, "Capability profiles, not agent
proliferation").

Six core roles ship in the first release.  Frontend/backend/database/DevOps/
performance/architecture concerns are represented as *profiles* selected by
the Team Builder, mapped onto the six core roles.

Each profile declares:
- `role`: the core role it belongs to (task_manager|investigator|security|
  implementation|verification|review)
- `allowed_tools`: explicit allowlist enforced by the orchestrator
- `artifact_types`: what the profile may produce
- `limits`: bounded observation budget (max tool calls per phase, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

RoleName = Literal[
    "task_manager",
    "investigator",
    "security",
    "implementation",
    "verification",
    "review",
]


@dataclass(frozen=True)
class ToolAllowance:
    """Permission to invoke one tool, possibly with bounded output."""

    name: str
    max_output_chars: int = 50_000


@dataclass(frozen=True)
class AgentLimits:
    """Bounded autonomy per phase (plan §7 and §12)."""

    max_tool_calls: int = 8
    time_limit_seconds: float = 60.0
    max_output_chars: int = 50_000


@dataclass(frozen=True)
class AgentProfile:
    """A named engineering capability with its tool permissions."""

    name: str                         # unique profile id, e.g. "investigator"
    role: RoleName                    # core role this profile maps to
    title: str                        # display title
    description: str
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    artifact_types: tuple[str, ...] = field(default_factory=tuple)
    limits: AgentLimits = field(default_factory=AgentLimits)

    def allows(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools


# ---------------------------------------------------------------------------
# Common tool sets (P0 tools from plan §6.2)
# ---------------------------------------------------------------------------

READ_TOOLS: tuple[str, ...] = ("list_files", "read_file", "search_code")
REPO_TOOLS: tuple[str, ...] = READ_TOOLS + ("git_log", "git_status", "repo_summary")
STRUCTURAL_TOOLS: tuple[str, ...] = (
    "python_ast_summary",
    "find_definition",
    "find_references",
    "import_graph",
)
RAG_TOOLS: tuple[str, ...] = ("semantic_search",)
SECURITY_TOOLS: tuple[str, ...] = ("bandit", "semgrep", "dependency_audit", "secret_scan")
CHECK_TOOLS: tuple[str, ...] = (
    "discover_checks",
    "run_test",
    "run_linter",
    "run_build",
    "git_diff",
    "git_status",
)
PATCH_TOOLS: tuple[str, ...] = ("git_diff", "read_file", "search_code")


# ---------------------------------------------------------------------------
# The six core profiles
# ---------------------------------------------------------------------------

def _profile(
    name: str,
    role: RoleName,
    title: str,
    description: str,
    tools: tuple[str, ...],
    artifacts: tuple[str, ...],
    limits: Optional[AgentLimits] = None,
) -> AgentProfile:
    return AgentProfile(
        name=name,
        role=role,
        title=title,
        description=description,
        allowed_tools=tools,
        artifact_types=artifacts,
        limits=limits or AgentLimits(),
    )


# Task Manager — validates the request, no repository access beyond a summary.
TASK_MANAGER = _profile(
    name="task_manager",
    role="task_manager",
    title="Task Manager",
    description="Validates the request, scope, and constraints; produces the TaskBrief.",
    tools=("repo_summary",),
    artifacts=("TaskBrief",),
    limits=AgentLimits(max_tool_calls=2, time_limit_seconds=30),
)

# Investigator — explores the repository and records evidence.
INVESTIGATOR = _profile(
    name="investigator",
    role="investigator",
    title="Repository Investigator",
    description="Explores the repository, traces code, records evidence.",
    tools=REPO_TOOLS + STRUCTURAL_TOOLS + ("semantic_search",),
    artifacts=("Evidence", "Diagnosis"),
    limits=AgentLimits(max_tool_calls=10, time_limit_seconds=120),
)

# Security Reviewer — reads and runs static security scanners.
SECURITY_REVIEWER = _profile(
    name="security_reviewer",
    role="security",
    title="Security Reviewer",
    description="Identifies security and dependency risks with verified findings.",
    tools=READ_TOOLS + SECURITY_TOOLS,
    artifacts=("AgentFinding",),
    limits=AgentLimits(max_tool_calls=8, time_limit_seconds=120),
)

# Implementation Agent — proposes a minimal patch after approval.
IMPLEMENTATION_AGENT = _profile(
    name="implementation",
    role="implementation",
    title="Implementation Agent",
    description="Proposes a minimal patch tied to evidence, applied only in a worktree.",
    tools=PATCH_TOOLS,
    artifacts=("PatchProposal",),
    limits=AgentLimits(max_tool_calls=8, time_limit_seconds=120),
)

# Verification Agent — discovers and runs approved check commands.
VERIFICATION_AGENT = _profile(
    name="verification",
    role="verification",
    title="Verification Agent",
    description="Discovers and runs tests, lint, build, and scanners in the worktree.",
    tools=CHECK_TOOLS,
    artifacts=("VerificationResult",),
    limits=AgentLimits(max_tool_calls=8, time_limit_seconds=180),
)

# Review Agent — reviews the patch and all verification evidence.
REVIEW_AGENT = _profile(
    name="review",
    role="review",
    title="Review Agent",
    description="Reviews the patch and evidence; approves, rejects, or requests revision.",
    tools=PATCH_TOOLS + ("discover_checks",),
    artifacts=("ReviewVerdict",),
    limits=AgentLimits(max_tool_calls=4, time_limit_seconds=60),
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CORE_PROFILES: dict[str, AgentProfile] = {
    p.name: p
    for p in (
        TASK_MANAGER,
        INVESTIGATOR,
        SECURITY_REVIEWER,
        IMPLEMENTATION_AGENT,
        VERIFICATION_AGENT,
        REVIEW_AGENT,
    )
}

# Capability focuses (plan §4): these are NOT separate agents yet, they
# select tool/artifact subsets of the core roles.
FOCUS_PROFILES: dict[str, AgentProfile] = {
    "performance": _profile(
        name="performance",
        role="investigator",
        title="Performance Focus",
        description="Performance-focused investigation: profiles and hotspots.",
        tools=REPO_TOOLS + STRUCTURAL_TOOLS + ("run_build",),
        artifacts=("Evidence", "AgentFinding"),
    ),
    "architecture": _profile(
        name="architecture",
        role="investigator",
        title="Architecture Focus",
        description="Architecture-focused investigation: imports, structure, coupling.",
        tools=REPO_TOOLS + STRUCTURAL_TOOLS + ("semantic_search",),
        artifacts=("Evidence", "AgentFinding"),
    ),
    "devops": _profile(
        name="devops",
        role="investigator",
        title="DevOps Focus",
        description="Deployment/config focused investigation: Docker, CI, manifests.",
        tools=REPO_TOOLS + ("dockerfile_validator", "dependency_audit"),
        artifacts=("Evidence", "AgentFinding"),
    ),
    "database": _profile(
        name="database",
        role="investigator",
        title="Database Focus",
        description="Data-layer focused investigation: queries and schema concerns.",
        tools=REPO_TOOLS + STRUCTURAL_TOOLS,
        artifacts=("Evidence", "AgentFinding"),
    ),
}

ALL_PROFILES: dict[str, AgentProfile] = {**CORE_PROFILES, **FOCUS_PROFILES}


def get_profile(name: str) -> Optional[AgentProfile]:
    return ALL_PROFILES.get(name)


def default_team_for_intent(intent: str) -> list[str]:
    """The default team recommended for each supported task intent."""
    if intent == "security":
        return ["investigator", "security_reviewer", "review"]
    if intent == "change":
        return ["investigator", "implementation", "verification", "review"]
    if intent == "diagnose":
        return ["investigator", "verification", "review"]
    # review / default
    return ["investigator", "review"]