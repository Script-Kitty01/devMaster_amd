"""
Review Agent — reviews the patch and all verification evidence, produces
a ReviewVerdict (plan §5, §9).

The review agent is the final gate before a patch can be applied to the
original repository.  It examines:
- The patch proposal (risk, scope, evidence linkage)
- Verification results (tests, lint, build)
- The original diagnoses and evidence

It produces one of three verdicts:
- approve: patch is safe and effective
- reject: patch is fundamentally flawed or too risky
- request_revision: patch needs changes (with specific notes)

Key design constraints:
- Never approves a high-risk patch without all mandatory checks passing.
- Never approves a patch with no linked evidence.
- Must explain its reasoning in review_notes.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.agents.profiles import AgentProfile, get_profile
from src.models.artifacts import (
    CheckStatus,
    Evidence,
    PatchProposal,
    ReviewVerdict,
    VerificationResult,
    new_id,
    now_iso,
    severity_rank,
)
from src.state.conversation_state import AgentFinding
from src.tools.tool_registry import ToolResult

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """You are the **Review Agent** of Kutaar, an evidence-driven engineering assistant.

Your mission:
- Review the proposed patch for correctness, safety, and completeness.
- Check that all verification checks passed.
- Ensure the patch cites the evidence that justifies it.
- Produce a final verdict: approve, reject, or request_revision.

Review criteria:
1. **Evidence linkage**: Does the patch cite specific evidence IDs? Are those evidence records present?
2. **Risk assessment**: Is the self-assessed risk level appropriate? For high-risk changes, are all mandatory checks passing?
3. **Scope**: Is the change minimal? Does it avoid unrelated refactoring?
4. **Correctness**: Does the diff look syntactically correct? Does it address the diagnosed issue?
5. **Verification**: Did all checks pass? Are there any blocked checks that should be treated as failures?
6. **Completeness**: Does the patch address all the diagnoses, or are some left unhandled?

Decision rules:
- If any mandatory check failed → reject
- If no evidence is linked → request_revision
- If the patch is high-risk and not all checks passed → request_revision
- If the patch is low/medium risk, all checks passed, and evidence is linked → approve
- If the patch needs minor adjustments → request_revision with specific notes

Output your review as JSON:
{
  "verdict": "approve|reject|request_revision",
  "notes": "detailed explanation of your decision",
  "risk_assessment": "low|medium|high",
  "concerns": ["concern 1", "concern 2"],
  "conditions": ["condition that must be met for approval"]
}"""


class ReviewAgent(BaseAgent):
    """Reviews patches and verification evidence; produces ReviewVerdict."""

    agent_name = "review"
    agent_emoji = "📋"
    system_prompt = REVIEW_SYSTEM_PROMPT

    def __init__(
        self,
        llm: Any,
        tool_registry: Any = None,
        rag_store: Any = None,
        *,
        profile: Optional[AgentProfile] = None,
    ) -> None:
        super().__init__(llm, tool_registry, rag_store)
        self.profile = profile or get_profile("review")

    # ------------------------------------------------------------------
    # BaseAgent interface (used by the existing review workflow)
    # ------------------------------------------------------------------

    def analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Review agent doesn't produce findings in the review workflow."""
        return []

    # ------------------------------------------------------------------
    # Task-workflow entry point
    # ------------------------------------------------------------------

    def review(
        self,
        *,
        task_text: str,
        patch_proposal: PatchProposal,
        verification_results: list[VerificationResult],
        evidence: list[Evidence],
        diagnoses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Review a patch proposal against verification results and evidence.

        Returns:
            Dict with: verdict, notes, risk_assessment, concerns, conditions
        """
        # Pre-check: deterministic rules that can short-circuit the LLM call.
        pre_check = self._pre_check(patch_proposal, verification_results, evidence)
        if pre_check is not None:
            logger.info("[Review] Pre-check verdict: %s", pre_check["verdict"])
            return pre_check

        # LLM-based review
        evidence_summary = self._format_evidence(evidence)
        verification_summary = self._format_verification(verification_results)
        diagnoses_summary = self._format_diagnoses(diagnoses)

        prompt = f"""## Task
{task_text}

## Patch Proposal
- ID: {patch_proposal.get('id', '?')}
- Summary: {patch_proposal.get('summary', '')}
- Rationale: {patch_proposal.get('rationale', '')}
- Risk Level: {patch_proposal.get('risk_level', 'medium')}
- Files Changed: {patch_proposal.get('files_changed', [])}
- Linked Evidence: {patch_proposal.get('linked_evidence_ids', [])}

### Unified Diff
```
{patch_proposal.get('unified_diff', '')}
```

## Verification Results
{verification_summary}

## Supporting Evidence
{evidence_summary}

## Diagnoses
{diagnoses_summary}

Review this patch proposal. Consider evidence linkage, risk, scope, correctness,
verification, and completeness. Produce your verdict.

Output as JSON:
{{"verdict": "approve|reject|request_revision", "notes": "...", "risk_assessment": "low|medium|high", "concerns": [...], "conditions": [...]}}"""

        response = self._call_llm(prompt, max_tokens=1024)
        parsed = self._parse_json_response(response)

        verdict = parsed.get("verdict", "request_revision")
        # Sanitize verdict
        if verdict not in ("approve", "reject", "request_revision"):
            verdict = "request_revision"

        result = {
            "verdict": verdict,
            "notes": parsed.get("notes", ""),
            "risk_assessment": parsed.get("risk_assessment", patch_proposal.get("risk_level", "medium")),
            "concerns": parsed.get("concerns", []),
            "conditions": parsed.get("conditions", []),
        }

        logger.info(
            "[Review] Verdict: %s (risk=%s, concerns=%d)",
            result["verdict"],
            result["risk_assessment"],
            len(result["concerns"]),
        )
        return result

    # ------------------------------------------------------------------
    # Deterministic pre-checks
    # ------------------------------------------------------------------

    def _pre_check(
        self,
        patch: PatchProposal,
        verification: list[VerificationResult],
        evidence: list[Evidence],
    ) -> Optional[dict[str, Any]]:
        """
        Run deterministic checks that can short-circuit the LLM call.

        Returns None if the LLM should decide, or a verdict dict if the
        decision is clear-cut.
        """
        # 1. No evidence linked → must request revision
        linked_ids = set(patch.get("linked_evidence_ids", []))
        if not linked_ids:
            return {
                "verdict": "request_revision",
                "notes": "Patch proposal has no linked evidence IDs. Every change must cite the evidence that justifies it.",
                "risk_assessment": patch.get("risk_level", "medium"),
                "concerns": ["No evidence linkage"],
                "conditions": ["Link at least one evidence record to the patch"],
            }

        # 2. Evidence IDs referenced but not found in the evidence list
        available_ids = {ev.get("id", "") for ev in evidence}
        missing_ids = linked_ids - available_ids
        if missing_ids and len(missing_ids) == len(linked_ids):
            return {
                "verdict": "request_revision",
                "notes": f"None of the linked evidence IDs ({missing_ids}) were found in the collected evidence.",
                "risk_assessment": patch.get("risk_level", "medium"),
                "concerns": [f"Missing evidence: {', '.join(list(missing_ids)[:5])}"],
                "conditions": ["Ensure evidence IDs reference actual collected evidence"],
            }

        # 3. Any mandatory check failed → reject
        for v in verification:
            if v.get("status") == "failed":
                return {
                    "verdict": "reject",
                    "notes": f"Verification check '{v.get('name', '?')}' failed: {v.get('summary', '')}",
                    "risk_assessment": "high",
                    "concerns": [f"Failed check: {v.get('name', '?')}"],
                    "conditions": ["All verification checks must pass before approval"],
                }

        # 4. High-risk patch with blocked checks → request revision
        if patch.get("risk_level") == "high":
            blocked = [v for v in verification if v.get("status") == "blocked"]
            if blocked:
                return {
                    "verdict": "request_revision",
                    "notes": f"High-risk patch has blocked verification checks: {', '.join(v.get('name', '?') for v in blocked)}. Blocked checks cannot be treated as passing for high-risk changes.",
                    "risk_assessment": "high",
                    "concerns": [f"Blocked check: {v.get('name', '?')}" for v in blocked],
                    "conditions": ["Resolve blocked verification checks or reduce risk level"],
                }

        # 5. No verification results at all → request revision
        if not verification:
            return {
                "verdict": "request_revision",
                "notes": "No verification results available. A patch cannot be approved without at least one verification check.",
                "risk_assessment": patch.get("risk_level", "medium"),
                "concerns": ["No verification performed"],
                "conditions": ["Run at least one verification check"],
            }

        # No clear-cut decision — let the LLM decide.
        return None

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_evidence(self, evidence: list[Evidence]) -> str:
        lines: list[str] = []
        for ev in evidence[:15]:
            lines.append(
                f"[{ev.get('id', '?')}] {ev.get('source', '?')}: "
                f"{ev.get('file_path', 'N/A')} "
                f"L{ev.get('line_start', '?')}-{ev.get('line_end', '?')} "
                f"(conf={ev.get('confidence', 0):.2f})"
            )
        return "\n".join(lines) if lines else "No evidence available."

    def _format_verification(self, results: list[VerificationResult]) -> str:
        lines: list[str] = []
        for v in results:
            status_emoji = {"passed": "✅", "failed": "❌", "blocked": "⚠️", "skipped": "⏭️"}.get(
                v.get("status", ""), "❓"
            )
            lines.append(
                f"{status_emoji} {v.get('name', '?')}: {v.get('status', '?')} "
                f"(exit={v.get('exit_code', '?')}) — {v.get('summary', '')[:200]}"
            )
        return "\n".join(lines) if lines else "No verification results."

    def _format_diagnoses(self, diagnoses: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for d in diagnoses[:10]:
            lines.append(
                f"[{d.get('id', '?')}] {d.get('summary', '')} "
                f"(conf={d.get('confidence', 0):.2f})"
            )
        return "\n".join(lines) if lines else "No diagnoses available."
