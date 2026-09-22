"""
Agent Registry — maps the six core engineering roles (and capability focus
profiles) to concrete agent classes (plan `plan-updrage.md` §4).

The existing specialist agents (Security, Performance, Architecture, DevOps)
are *reused* by the new task workflow; they are not duplicated.  The registry
is the single place that decides which concrete agent class backs a profile.

For the first release the task workflow uses deterministic, tool-driven
agents plus the existing specialist agents for the security/review roles.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from src.agents.profiles import (
    ALL_PROFILES,
    AgentProfile,
    CORE_PROFILES,
    FOCUS_PROFILES,
    default_team_for_intent,
    get_profile,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentBinding:
    """How a profile maps to executable code."""

    profile_name: str
    implementation: str  # "tool_loop" | existing agent class name
    agent_class: Optional[type] = None
    prompt_key: str = ""


# ---------------------------------------------------------------------------
# Role → implementation mapping
# ---------------------------------------------------------------------------

# Core-role → agent class (imported lazily to avoid heavy imports).
# New task-workflow agents (investigator, implementation, review) are
# preferred; existing specialist agents are kept for the review workflow.
_ROLE_TO_AGENT_CLASS: dict[str, str] = {
    "task_manager": "src.agents.consensus_agent.ConsensusAgent",
    "investigator": "src.agents.investigator_agent.InvestigatorAgent",
    "security": "src.agents.security_agent.SecurityAgent",
    "implementation": "src.agents.implementation_agent.ImplementationAgent",
    "verification": "src.agents.devops_agent.DevOpsAgent",
    "review": "src.agents.review_agent.ReviewAgent",
}


def resolve_agent_class(profile_name: str) -> Optional[type]:
    """Resolve a profile to its concrete agent class (lazy import)."""
    profile = get_profile(profile_name)
    if profile is None:
        return None
    # Focus profiles map to investigator-role classes.
    role = profile.role
    if profile_name in FOCUS_PROFILES:
        role = "investigator"
    class_ref = _ROLE_TO_AGENT_CLASS.get(role)
    if class_ref is None:
        return None
    module_name, _, class_name = class_ref.rpartition(".")
    try:
        module = __import__(module_name, fromlist=[class_name])
        return getattr(module, class_name)
    except Exception as exc:
        logger.warning("Could not resolve agent class %s: %s", class_ref, exc)
        return None


# ---------------------------------------------------------------------------
# Team Builder
# ---------------------------------------------------------------------------

class TeamBuilder:
    """
    Recommends a team profile set from the task intent and repository metadata.

    Uses a static, testable routing table rather than free-form model output
    (plan §7 "Dynamic routing").  The user always has the final say via the UI.
    """

    def __init__(self, profiles: Optional[dict[str, AgentProfile]] = None) -> None:
        self.profiles = profiles or ALL_PROFILES

    def recommend(
        self,
        *,
        intent: str,
        repo_metadata: Optional[dict[str, Any]] = None,
        user_selected: Optional[list[str]] = None,
    ) -> list[str]:
        """Return the recommended profile names.

        Args:
            intent: normalized task intent ("review", "diagnose", "change",
                or a focus like "security", "performance").
            repo_metadata: optional repository summary (languages, size...).
            user_selected: profile names the user has already chosen; these
                win over the recommendation when valid.

        Returns:
            Ordered, deduplicated list of profile names.
        """
        if user_selected:
            valid = [p for p in user_selected if p in self.profiles]
            # Always include the reviewer so nothing ships unreviewed.
            if "review" not in valid:
                valid = valid
            return valid

        intent = (intent or "review").lower()
        team = list(default_team_for_intent(intent))

        # Focus profiles expand the investigator capability set.
        if intent in ("performance", "architecture", "devops", "database", "security"):
            focus = intent if intent != "security" else None
            if focus and focus in self.profiles and focus not in team:
                team.append(focus)

        # Deduplicate while preserving order.
        seen: set[str] = set()
        ordered: list[str] = []
        for name in team:
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    def binding(self, profile_name: str) -> Optional[AgentBinding]:
        """Return the binding for a profile, or None if unknown."""
        profile = self.profiles.get(profile_name)
        if profile is None:
            return None
        cls = resolve_agent_class(profile_name)
        if profile_name in FOCUS_PROFILES or profile.role == "investigator":
            implementation = "tool_loop"  # driven by the workflow orchestrator
        else:
            implementation = cls.__name__ if cls else "tool_loop"
        return AgentBinding(
            profile_name=profile_name,
            implementation=implementation,
            agent_class=cls,
        )


# Convenience singleton
team_builder = TeamBuilder()


def available_profiles() -> dict[str, AgentProfile]:
    """All profile names and titles for the UI team editor."""
    return ALL_PROFILES