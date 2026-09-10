"""
Task Workflow — LangGraph StateGraph governing the isolated task workflow.

Implements the lifecycle defined in plan `plan-updrage.md` §7:
intake → recon → team → investigate → plan → approval → implement → verify
→ review → report (with bounded retry loop on verification failure).

This is a second, independent workflow using `TaskState` so the existing
`KutaarWorkflow` (in `src/graph/workflow.py`) remains stable.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agents.agent_registry import team_builder
from src.agents.consensus_agent import ConsensusAgent
from src.agents.implementation_agent import ImplementationAgent
from src.agents.investigator_agent import InvestigatorAgent
from src.agents.review_agent import ReviewAgent
from src.agents.security_agent import SecurityAgent
from src.execution.worktree import WorktreeManager, WorktreeResult
from src.models.artifacts import (
    Diagnosis,
    Evidence,
    PatchProposal,
    ReviewVerdict,
    TaskBrief,
    VerificationResult,
    downgrade_finding_without_evidence,
    evidence_from_tool_result,
    new_id,
    now_iso,
    validate_patch_proposal,
    validate_task_brief,
)
from src.state.task_state import TaskState, initial_task_state
from src.tools.check_runner import CheckRunner
from src.tools.intelligence_tools import register_intelligence_tools
from src.tools.tool_registry import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


class TaskWorkflow:
    """
    The main LangGraph workflow for autonomous, evidence-driven tasks.

    Usage:
        wf = TaskWorkflow(llm, rag_store=rag, tool_registry=tools)
        app = wf.compile()
        state = initial_task_state(repo_path="/path/to/repo", task_text="Fix auth bug")
        result = app.invoke(state)
    """

    def __init__(
        self,
        llm: Any,
        *,
        rag_store: Any = None,
        tool_registry: Optional[ToolRegistry] = None,
        worktree_manager: Optional[WorktreeManager] = None,
        auto_approve: bool = False,
    ) -> None:
        self.llm = llm
        self.rag_store = rag_store
        self.auto_approve = auto_approve

        # Initialize tools
        self.tool_registry = tool_registry or ToolRegistry(repo_path=".")
        register_intelligence_tools(self.tool_registry, rag_store=rag_store)

        self.worktree_manager = worktree_manager

        # Initialize agents
        self.investigator = InvestigatorAgent(
            llm, tool_registry=self.tool_registry, rag_store=rag_store
        )
        self.security = SecurityAgent(
            llm, tool_registry=self.tool_registry, rag_store=rag_store
        )
        self.implementation = ImplementationAgent(
            llm, tool_registry=self.tool_registry, rag_store=rag_store
        )
        self.review = ReviewAgent(
            llm, tool_registry=self.tool_registry, rag_store=rag_store
        )
        self.consensus = ConsensusAgent(
            llm, tool_registry=self.tool_registry, rag_store=rag_store
        )

    # ------------------------------------------------------------------
    # Graph Construction
    # ------------------------------------------------------------------

    def build_graph(self) -> StateGraph:
        """Construct the StateGraph for TaskState."""
        workflow = StateGraph(TaskState)

        # Register nodes
        workflow.add_node("intake", self._node_intake)
        workflow.add_node("recon", self._node_recon)
        workflow.add_node("team", self._node_team)
        workflow.add_node("investigate", self._node_investigate)
        workflow.add_node("plan", self._node_plan)
        workflow.add_node("approval", self._node_approval)
        workflow.add_node("implement", self._node_implement)
        workflow.add_node("verify", self._node_verify)
        workflow.add_node("review", self._node_review)
        workflow.add_node("report", self._node_report)

        # Set entry point
        workflow.set_entry_point("intake")

        # Edges
        workflow.add_edge("intake", "recon")
        workflow.add_edge("recon", "team")
        workflow.add_edge("team", "investigate")
        workflow.add_edge("investigate", "plan")

        # Conditional after plan:
        # If change task -> approval; if review/diagnose -> review or report
        workflow.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {
                "approval": "approval",
                "review": "review",
                "report": "report",
            },
        )

        # Conditional after approval:
        # If approved -> implement; else -> report (blocked/unapproved)
        workflow.add_conditional_edges(
            "approval",
            self._route_after_approval,
            {
                "implement": "implement",
                "report": "report",
            },
        )

        workflow.add_edge("implement", "verify")
        workflow.add_edge("verify", "review")

        # Conditional after review:
        # If request_revision and retries remain -> implement (retry); else -> report
        workflow.add_conditional_edges(
            "review",
            self._route_after_review,
            {
                "implement": "implement",
                "report": "report",
            },
        )

        workflow.add_edge("report", END)

        return workflow

    def compile(self, checkpointer: Optional[Any] = None) -> Any:
        """Build and compile the workflow into a runnable app."""
        graph = self.build_graph()
        return graph.compile(checkpointer=checkpointer)

    # ------------------------------------------------------------------
    # Routing Conditions
    # ------------------------------------------------------------------

    def _route_after_plan(self, state: TaskState) -> str:
        """Route to approval for change tasks, or review/report for others."""
        brief = state.get("task_brief") or {}
        intent = brief.get("intent", "review")
        if intent == "change":
            return "approval"
        # For review/diagnose with findings: review them, otherwise go to report
        if state.get("findings"):
            return "review"
        return "report"

    def _route_after_approval(self, state: TaskState) -> str:
        """Route to implement if approved (or auto-approved); else report."""
        if state.get("approved") or self.auto_approve:
            return "implement"
        return "report"

    def _route_after_review(self, state: TaskState) -> str:
        """Route to retry loop if revision requested, else report."""
        verdict = state.get("review_verdict")
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 2)

        if verdict == "request_revision" and retry_count < max_retries:
            logger.info(
                "[TaskWorkflow] Revision requested; retry %d/%d",
                retry_count + 1,
                max_retries,
            )
            return "implement"
        return "report"

    # ------------------------------------------------------------------
    # Node Implementations
    # ------------------------------------------------------------------

    def _node_intake(self, state: TaskState) -> dict[str, Any]:
        """Intake node: validate user request, infer intent, construct TaskBrief."""
        logger.info("[TaskWorkflow] Phase: intake")
        task_text = state.get("task_text", "")
        repo_path = state.get("repo_path", ".")

        # Update tool registry repo path if provided
        tool_registry = getattr(self, "tool_registry", None)
        if repo_path and tool_registry is not None and hasattr(tool_registry, "repo_path"):
            tool_registry.repo_path = repo_path

        # Infer intent (review, diagnose, change)
        lower_task = task_text.lower()
        if any(w in lower_task for w in ["fix", "patch", "repair", "implement", "change", "refactor", "update", "modify", "add"]):
            intent = "change"
        elif any(w in lower_task for w in ["why", "diagnose", "debug", "root cause", "investigate", "trace"]):
            intent = "diagnose"
        else:
            intent = "review"

        approval_required = (intent == "change") and not self.auto_approve

        brief = TaskBrief(
            task_id=new_id("task"),
            user_request=task_text,
            intent=intent,
            scope_paths=[],
            constraints=["read-only until approval", "isolated worktree execution"],
            selected_profiles=state.get("selected_profiles", []),
            approval_required=approval_required,
        )

        return {
            "task_brief": brief,
            "phase": "recon",
            "phase_detail": f"Task accepted (intent: {intent}); discovering repository.",
            "approval_required": approval_required,
            "approved": self.auto_approve or state.get("approved", False),
        }

    def _node_recon(self, state: TaskState) -> dict[str, Any]:
        """Reconnaissance node: discover structure, languages, manifests, test commands."""
        logger.info("[TaskWorkflow] Phase: recon")
        repo_path = state.get("repo_path", ".")
        tool_logs = list(state.get("tool_logs", []))

        # 1. Run repo_summary tool
        summary_res = self.tool_registry.invoke("repo_summary", repo_path=repo_path)
        tool_logs.append({
            "tool": "repo_summary",
            "success": summary_res.success,
            "summary": summary_res.summary,
            "elapsed_ms": summary_res.elapsed_ms,
        })
        repo_summary_data = summary_res.details[0] if summary_res.details else {}

        # 2. Run discover_checks tool
        checks_res = self.tool_registry.invoke("discover_checks", repo_path=repo_path)
        tool_logs.append({
            "tool": "discover_checks",
            "success": checks_res.success,
            "summary": checks_res.summary,
            "elapsed_ms": checks_res.elapsed_ms,
        })

        # 3. Recommend team profiles
        brief = state.get("task_brief") or {}
        intent = brief.get("intent", "review")
        recommended = team_builder.recommend(
            intent=intent,
            repo_metadata=repo_summary_data,
            user_selected=state.get("selected_profiles"),
        )

        return {
            "repo_summary": repo_summary_data,
            "recommended_profiles": recommended,
            "tool_logs": tool_logs,
            "phase": "team",
            "phase_detail": f"Reconnaissance complete ({repo_summary_data.get('total_files', 0)} files); team recommended.",
        }

    def _node_team(self, state: TaskState) -> dict[str, Any]:
        """Team node: resolve selected profiles for this run."""
        logger.info("[TaskWorkflow] Phase: team")
        selected = state.get("selected_profiles") or state.get("recommended_profiles") or ["investigator", "review"]

        brief = state.get("task_brief")
        if brief:
            brief["selected_profiles"] = selected

        return {
            "selected_profiles": selected,
            "task_brief": brief,
            "phase": "investigate",
            "phase_detail": f"Team assembled: {', '.join(selected)}.",
        }

    def _node_investigate(self, state: TaskState) -> dict[str, Any]:
        """Investigation node: run bounded observation loop, collect evidence & diagnoses."""
        logger.info("[TaskWorkflow] Phase: investigate")
        task_text = state.get("task_text", "")
        repo_path = state.get("repo_path", ".")
        selected = state.get("selected_profiles", [])
        evidence_list: list[Evidence] = list(state.get("evidence", []))
        diagnoses_list: list[Diagnosis] = list(state.get("diagnoses", []))
        findings_list: list[dict[str, Any]] = list(state.get("findings", []))
        tool_logs = list(state.get("tool_logs", []))

        # RAG context if available
        rag_context: list[dict[str, Any]] = []
        if self.rag_store and hasattr(self.rag_store, "query") and hasattr(self.llm, "embed"):
            try:
                rag_context = self.rag_store.query(task_text, self.llm.embed, k=5)
            except Exception as exc:
                logger.debug("RAG query in investigate: %s", exc)

        # 1. Run InvestigatorAgent
        inv_res = self.investigator.investigate(
            task_text=task_text,
            repo_path=repo_path,
            rag_context=rag_context,
        )
        evidence_list.extend(inv_res.get("evidence", []))
        diagnoses_list.extend(inv_res.get("diagnoses", []))
        findings_list.extend(inv_res.get("findings", []))

        # 2. Run SecurityReviewer if selected
        if "security" in selected or "security_reviewer" in selected:
            sec_findings = self.security.analyze(task_text, rag_context, "")
            findings_list.extend(sec_findings)

        # Ensure all findings have evidence / downgraded status
        verified_findings = [downgrade_finding_without_evidence(f) for f in findings_list]

        return {
            "evidence": evidence_list,
            "diagnoses": diagnoses_list,
            "findings": verified_findings,
            "tool_logs": tool_logs,
            "phase": "plan",
            "phase_detail": f"Investigation complete ({len(evidence_list)} evidence, {len(diagnoses_list)} diagnoses, {len(verified_findings)} findings).",
        }

    def _node_plan(self, state: TaskState) -> dict[str, Any]:
        """Plan node: synthesize diagnoses into implementation plan and patch proposal."""
        logger.info("[TaskWorkflow] Phase: plan")
        task_text = state.get("task_text", "")
        brief = state.get("task_brief") or {}
        intent = brief.get("intent", "review")
        diagnoses = state.get("diagnoses", [])
        evidence = state.get("evidence", [])

        # Formulate implementation plan text
        if diagnoses:
            plan_lines = ["### Implementation Plan"]
            for i, d in enumerate(diagnoses, 1):
                plan_lines.append(
                    f"{i}. Address `{d.get('root_cause_file', 'unknown')}`: {d.get('proposed_change', d.get('summary', ''))}"
                )
            plan_text = "\n".join(plan_lines)
        else:
            plan_text = f"Review/investigation plan for: {task_text}"

        patch_prop: Optional[PatchProposal] = None
        if intent == "change":
            patch_prop = self.implementation.propose_patch(
                task_text=task_text,
                diagnoses=diagnoses,
                evidence=evidence,
                implementation_plan=plan_text,
            )

        return {
            "implementation_plan": plan_text,
            "patch_proposal": patch_prop,
            "phase": "approval" if intent == "change" else "report",
            "phase_detail": "Plan and proposal generated.",
        }

    def _node_approval(self, state: TaskState) -> dict[str, Any]:
        """Approval boundary node: gate mutation on user approval."""
        logger.info("[TaskWorkflow] Phase: approval")
        approved = state.get("approved", False) or self.auto_approve

        if not approved:
            return {
                "phase": "blocked",
                "phase_detail": "Awaiting explicit user approval before isolated worktree mutation.",
            }

        return {
            "approved": True,
            "phase": "implement",
            "phase_detail": "User approved; proceeding to isolated worktree implementation.",
        }

    def _node_implement(self, state: TaskState) -> dict[str, Any]:
        """Implement node: create Git worktree, apply patch proposal, capture diff."""
        logger.info("[TaskWorkflow] Phase: implement")
        repo_path = state.get("repo_path", ".")
        patch_prop = state.get("patch_proposal")
        retry_count = state.get("retry_count", 0)

        # Initialize or reuse worktree manager
        wt_mgr = self.worktree_manager or WorktreeManager(repo_root=repo_path)
        self.worktree_manager = wt_mgr

        task_id = (state.get("task_brief") or {}).get("task_id", new_id("task"))
        branch_name = f"kutaar/{task_id}"

        wt_res: WorktreeResult = wt_mgr.create(branch=branch_name)
        if not wt_res.ok or not wt_res.path:
            logger.warning("[TaskWorkflow] Worktree creation failed: %s", wt_res.error)
            # Fallback: if git worktree fails (e.g., in a non-git folder in tests), use repo_path directly
            worktree_path = repo_path
        else:
            worktree_path = wt_res.path

        # If this is a retry, refine the patch first
        if retry_count > 0 and patch_prop:
            patch_prop = self.implementation.refine_patch(
                original_proposal=patch_prop,
                review_notes=state.get("review_notes", ""),
                verification_failures=[
                    v for v in state.get("verification_results", []) if v.get("status") == "failed"
                ],
                evidence=state.get("evidence", []),
            )

        # Apply patch if present
        if patch_prop and patch_prop.get("unified_diff") and wt_res.ok:
            wt_mgr.apply_patch(wt_res, patch_prop["unified_diff"])

        return {
            "worktree_path": worktree_path,
            "worktree_branch": branch_name,
            "patch_proposal": patch_prop,
            "retry_count": retry_count,
            "phase": "verify",
            "phase_detail": f"Patch applied to isolated worktree `{worktree_path}`.",
        }

    def _node_verify(self, state: TaskState) -> dict[str, Any]:
        """Verify node: discover and run verification checks against the worktree."""
        logger.info("[TaskWorkflow] Phase: verify")
        worktree_path = state.get("worktree_path") or state.get("repo_path", ".")

        # Run CheckRunner in worktree
        runner = CheckRunner(worktree_path=worktree_path)
        verification_results = runner.run_all()

        return {
            "verification_results": verification_results,
            "phase": "review",
            "phase_detail": f"Verification checks complete ({len(verification_results)} checks executed).",
        }

    def _node_review(self, state: TaskState) -> dict[str, Any]:
        """Review node: ReviewAgent assesses patch proposal, verification evidence, and diagnoses."""
        logger.info("[TaskWorkflow] Phase: review")
        task_text = state.get("task_text", "")
        patch_prop = state.get("patch_proposal") or PatchProposal(
            id=new_id("patch"),
            summary="Review-only run",
            rationale="",
            files_changed=[],
            unified_diff="",
            linked_evidence_ids=[ev.get("id", "") for ev in state.get("evidence", [])[:1]],
            risk_level="low",
            verification_commands=[],
        )
        verification_results = state.get("verification_results", [])
        evidence = state.get("evidence", [])
        diagnoses = state.get("diagnoses", [])
        retry_count = state.get("retry_count", 0)

        review_res = self.review.review(
            task_text=task_text,
            patch_proposal=patch_prop,
            verification_results=verification_results,
            evidence=evidence,
            diagnoses=diagnoses,
        )

        verdict = review_res.get("verdict", "approve")
        notes = review_res.get("notes", "")

        # If revision requested, increment retry count
        new_retry_count = retry_count + 1 if verdict == "request_revision" else retry_count

        return {
            "review_verdict": verdict,
            "review_notes": notes,
            "retry_count": new_retry_count,
            "phase": "report",
            "phase_detail": f"Review complete. Verdict: {verdict.upper()}.",
        }

    def _node_report(self, state: TaskState) -> dict[str, Any]:
        """Report node: format the comprehensive final markdown report."""
        logger.info("[TaskWorkflow] Phase: report")
        brief = state.get("task_brief") or {}
        verdict = state.get("review_verdict") or "N/A"
        findings = state.get("findings", [])
        evidence = state.get("evidence", [])
        diagnoses = state.get("diagnoses", [])
        verification = state.get("verification_results", [])
        patch_prop = state.get("patch_proposal")
        worktree_branch = state.get("worktree_branch", "None")

        report_lines = [
            f"# Kutaar Task Execution Report\n",
            f"**Task ID:** `{brief.get('task_id', 'N/A')}` | **Intent:** `{brief.get('intent', 'N/A')}` | **Verdict:** `{verdict}`\n",
            f"**User Request:** {state.get('task_text', '')}\n",
            f"---\n",
        ]

        # 1. Timeline & Status
        report_lines.append(f"### Status\n")
        report_lines.append(f"- **Current Phase:** `{state.get('phase', 'done')}`")
        report_lines.append(f"- **Detail:** {state.get('phase_detail', '')}")
        report_lines.append(f"- **Isolated Worktree Branch:** `{worktree_branch}`")
        report_lines.append(f"- **Retries Used:** {state.get('retry_count', 0)} / {state.get('max_retries', 2)}\n")

        # 2. Diagnoses & Findings
        report_lines.append(f"### Findings & Diagnoses ({len(findings)} findings, {len(diagnoses)} diagnoses)\n")
        if diagnoses:
            report_lines.append("#### Diagnoses")
            for d in diagnoses:
                ev_str = ", ".join(d.get("linked_evidence_ids", [])) or "None"
                report_lines.append(
                    f"- **{d.get('summary', '')}** (Root cause: `{d.get('root_cause_file', 'unknown')}`, Evidence: `{ev_str}`)"
                )
            report_lines.append("")

        if findings:
            report_lines.append("#### Findings Table")
            report_lines.append("| Severity | Title | File | Verification Status | Evidence IDs |")
            report_lines.append("|---|---|---|---|---|")
            for f in findings:
                ev_ids = ", ".join(f.get("evidence_ids", [])) or "None"
                v_status = f.get("verification_status", "hypothesis")
                report_lines.append(
                    f"| {f.get('severity', 'info')} | {f.get('title', '')} | `{f.get('file_path', '')}` | {v_status} | {ev_ids} |"
                )
            report_lines.append("")

        # 3. Patch Proposal
        if patch_prop and patch_prop.get("unified_diff"):
            report_lines.append("### Proposed Patch\n")
            report_lines.append(f"- **Summary:** {patch_prop.get('summary', '')}")
            report_lines.append(f"- **Risk Level:** `{patch_prop.get('risk_level', 'medium')}`")
            report_lines.append(f"- **Files Changed:** {', '.join(patch_prop.get('files_changed', []))}")
            report_lines.append(f"```diff\n{patch_prop.get('unified_diff', '')}\n```\n")

        # 4. Verification Table
        if verification:
            report_lines.append("### Verification Results\n")
            report_lines.append("| Check | Status | Exit Code | Summary |")
            report_lines.append("|---|---|---|---|")
            for v in verification:
                emoji = {"passed": "✅", "failed": "❌", "blocked": "⚠️", "skipped": "⏭️"}.get(
                    v.get("status", ""), "❓"
                )
                report_lines.append(
                    f"| `{v.get('name', 'unknown')}` | {emoji} {v.get('status', 'unknown')} | {v.get('exit_code', 'N/A')} | {v.get('summary', '')[:80]} |"
                )
            report_lines.append("")

        # 5. Review Notes
        if state.get("review_notes"):
            report_lines.append(f"### Review Notes\n{state.get('review_notes')}\n")

        if state.get("approval_required") and not state.get("approved"):
            report_lines.append("### Approval Required\n")
            report_lines.append("The proposal has not been applied. Approve it in the workspace before implementation.")

        final_report = "\n".join(report_lines)

        return {
            "report": final_report,
            "phase": "report",
            "phase_detail": (
                "Awaiting explicit approval before implementation."
                if state.get("approval_required") and not state.get("approved")
                else "Task execution completed successfully."
            ),
        }
