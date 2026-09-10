"""
Implementation Agent — approval-gated patch proposal.

Produces a PatchProposal artifact tied to evidence, applied only in an
isolated worktree (plan §5, §8).  The agent never mutates the original
checkout; it proposes a unified diff that the review agent must approve
before it can be merged.

Key design constraints:
- Only operates inside a worktree (never the original checkout).
- Every patch must cite linked_evidence_ids.
- Risk level is self-assessed but can be overridden by the review agent.
- The patch is a *proposal* — it is not applied until approved.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.agents.profiles import AgentProfile, get_profile
from src.models.artifacts import (
    Evidence,
    PatchProposal,
    new_id,
    now_iso,
    validate_patch_proposal,
)
from src.state.conversation_state import AgentFinding
from src.tools.tool_registry import ToolResult

logger = logging.getLogger(__name__)

IMPLEMENTATION_SYSTEM_PROMPT = """You are the **Implementation Agent** of Kutaar, an evidence-driven engineering assistant.

Your mission:
- Propose minimal, targeted code changes that address the diagnosed issues.
- Every change must cite the evidence that justifies it.
- Assess the risk level of your proposed change (low/medium/high).
- Provide verification commands that can confirm the change works.

Constraints:
- Propose the *smallest* change that fixes the issue.  Do not refactor unrelated code.
- Never delete code without explaining why.
- Never add new dependencies without justification.
- If the change is risky (high risk), explain what could go wrong and how to mitigate it.

Output your patch proposal as JSON:
{
  "summary": "one-line description",
  "rationale": "why this change is needed and why it's safe",
  "files_changed": ["path/to/file.py"],
  "unified_diff": "diff --git a/...",
  "linked_evidence_ids": ["ev-abc123"],
  "risk_level": "low|medium|high",
  "verification_commands": [["pytest", "-q"], ["ruff", "check", "."]]
}"""


class ImplementationAgent(BaseAgent):
    """Produces approval-gated patch proposals tied to evidence."""

    agent_name = "implementation"
    agent_emoji = "🔧"
    system_prompt = IMPLEMENTATION_SYSTEM_PROMPT

    def __init__(
        self,
        llm: Any,
        tool_registry: Any = None,
        rag_store: Any = None,
        *,
        profile: Optional[AgentProfile] = None,
    ) -> None:
        super().__init__(llm, tool_registry, rag_store)
        self.profile = profile or get_profile("implementation")

    # ------------------------------------------------------------------
    # BaseAgent interface (used by the existing review workflow)
    # ------------------------------------------------------------------

    def analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Implementation agent doesn't produce findings in the review workflow."""
        return []

    # ------------------------------------------------------------------
    # Task-workflow entry point
    # ------------------------------------------------------------------

    def propose_patch(
        self,
        *,
        task_text: str,
        diagnoses: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        implementation_plan: str = "",
        worktree_diff: str = "",
    ) -> PatchProposal:
        """
        Produce a PatchProposal from diagnoses and evidence.

        The LLM is given the diagnoses, evidence, and any existing plan,
        and asked to produce a minimal unified diff.

        Args:
            task_text: The original user request.
            diagnoses: List of Diagnosis dicts from the investigator.
            evidence: List of Evidence dicts collected during investigation.
            implementation_plan: Optional plan text from the planning phase.
            worktree_diff: Current diff in the worktree (if any prior changes).

        Returns:
            A PatchProposal dict (may be empty/invalid if the LLM fails).
        """
        evidence_summary = self._format_evidence(evidence)
        diagnoses_summary = self._format_diagnoses(diagnoses)

        prompt = f"""## Task
{task_text}

## Diagnoses
{diagnoses_summary}

## Supporting Evidence
{evidence_summary}

## Implementation Plan
{implementation_plan or "No specific plan provided; use your judgment."}

## Current Worktree Diff
{worktree_diff or "No prior changes in the worktree."}

Based on the diagnoses and evidence, propose a minimal patch. Remember:
- Cite specific evidence IDs in linked_evidence_ids.
- Keep the change as small as possible.
- Assess risk honestly.
- Provide verification commands.

Output as JSON:
{{"summary": "...", "rationale": "...", "files_changed": [...], "unified_diff": "...", "linked_evidence_ids": [...], "risk_level": "low|medium|high", "verification_commands": [...]}}"""

        response = self._call_llm(prompt, max_tokens=2048)
        parsed = self._parse_json_response(response)

        proposal = PatchProposal(
            id=new_id("patch"),
            summary=parsed.get("summary", "Untitled patch"),
            rationale=parsed.get("rationale", ""),
            files_changed=parsed.get("files_changed", []),
            unified_diff=parsed.get("unified_diff", ""),
            linked_evidence_ids=parsed.get("linked_evidence_ids", []),
            risk_level=parsed.get("risk_level", "medium"),
            verification_commands=parsed.get("verification_commands", []),
        )

        # Validate and log
        errors = validate_patch_proposal(proposal)
        if errors:
            logger.warning("[Implementation] Patch validation issues: %s", errors)
            # Don't discard — the review agent will catch these.

        logger.info(
            "[Implementation] Proposed patch %s: %s (risk=%s, %d files)",
            proposal.get("id", "?"),
            proposal.get("summary", "")[:60],
            proposal.get("risk_level", "?"),
            len(proposal.get("files_changed", [])),
        )
        return proposal

    def refine_patch(
        self,
        *,
        original_proposal: PatchProposal,
        review_notes: str,
        verification_failures: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> PatchProposal:
        """
        Refine a patch after review feedback or verification failures.

        Used when the review agent requests revisions or when verification
        fails and the implementation agent gets a retry.
        """
        failures_summary = ""
        for v in verification_failures:
            failures_summary += f"- {v.get('name', '?')}: {v.get('summary', '')}\n"

        prompt = f"""## Original Patch
Summary: {original_proposal.get('summary', '')}
Rationale: {original_proposal.get('rationale', '')}
Risk: {original_proposal.get('risk_level', '')}
Files: {original_proposal.get('files_changed', [])}

## Unified Diff (original)
```
{original_proposal.get('unified_diff', '')}
```

## Review Notes
{review_notes or "No specific review notes."}

## Verification Failures
{failures_summary or "No verification failures."}

## Available Evidence
{self._format_evidence(evidence)}

Please refine the patch to address the review notes and verification failures.
Keep the change minimal. Output the same JSON format as before."""

        response = self._call_llm(prompt, max_tokens=2048)
        parsed = self._parse_json_response(response)

        refined = PatchProposal(
            id=new_id("patch"),
            summary=parsed.get("summary", original_proposal.get("summary", "Refined patch")),
            rationale=parsed.get("rationale", original_proposal.get("rationale", "")),
            files_changed=parsed.get("files_changed", original_proposal.get("files_changed", [])),
            unified_diff=parsed.get("unified_diff", original_proposal.get("unified_diff", "")),
            linked_evidence_ids=parsed.get(
                "linked_evidence_ids", original_proposal.get("linked_evidence_ids", [])
            ),
            risk_level=parsed.get("risk_level", original_proposal.get("risk_level", "medium")),
            verification_commands=parsed.get(
                "verification_commands", original_proposal.get("verification_commands", [])
            ),
        )

        logger.info("[Implementation] Refined patch %s", refined.get("id", "?"))
        return refined

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_evidence(self, evidence: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for i, ev in enumerate(evidence[:15], 1):
            lines.append(
                f"[{ev.get('id', i)}] {ev.get('source', '?')}: "
                f"{ev.get('file_path', 'N/A')} "
                f"L{ev.get('line_start', '?')}-{ev.get('line_end', '?')} "
                f"(conf={ev.get('confidence', 0):.2f})\n"
                f"  {ev.get('excerpt', '')[:300]}"
            )
        return "\n".join(lines) if lines else "No evidence available."

    def _format_diagnoses(self, diagnoses: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for i, d in enumerate(diagnoses[:10], 1):
            lines.append(
                f"[{d.get('id', i)}] {d.get('summary', '')}\n"
                f"  Root cause: {d.get('root_cause_file', '?')} "
                f"L{d.get('root_cause_lines', [])}\n"
                f"  Confidence: {d.get('confidence', 0):.2f}\n"
                f"  Proposed change: {d.get('proposed_change', '')}"
            )
        return "\n".join(lines) if lines else "No diagnoses available."
