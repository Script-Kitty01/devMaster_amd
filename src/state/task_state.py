"""
Task State — LangGraph TypedDict governing the isolated task workflow.

This is a *second* state type, intentionally separate from
`ConversationState` so the existing review graph is not destabilized
(plan `plan-updrage.md` §7: "Implement a second workflow first").

Fields are grouped by phase so the UI can render an explicit timeline:
intake → investigation → plan → approval → implementation → verification
→ review → report.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph.message import add_messages

from src.models.artifacts import (
    CheckStatus,
    Diagnosis,
    Evidence,
    PatchProposal,
    ReviewVerdict,
    RiskLevel,
    TaskBrief,
    VerificationResult,
)


class TaskState(TypedDict, total=False):
    """
    The full state of one Kutaar task run.

    Messages accumulate via LangGraph's `add_messages` reducer; every other
    field is replaced wholesale by the node that produces it.
    """

    # --- Chat history (auto-reduced by add_messages) ---
    messages: Annotated[list, add_messages]

    # --- Intake ---
    repo_path: str                 # absolute path to the target repository
    task_text: str                 # raw user request
    task_brief: Optional[TaskBrief]

    # --- Phase tracking (UI timeline) ---
    phase: str                     # intake|recon|team|investigate|plan|approval|implement|verify|review|report|blocked
    phase_detail: str
    error: Optional[str]

    # --- Repository reconnaissance ---
    repo_summary: Optional[dict[str, Any]]   # tree summary, languages, tests, git info

    # --- Investigation artifacts ---
    evidence: list[Evidence]       # append-only collection of observations
    diagnoses: list[Diagnosis]
    findings: list[dict[str, Any]] # AgentFinding-compatible records w/ evidence_ids

    # --- Team selection ---
    selected_profiles: list[str]
    recommended_profiles: list[str]

    # --- Plan / approval ---
    implementation_plan: str
    task_plan: str                 # alias of implementation_plan (plan.md contract name)
    risk_level: RiskLevel          # low | medium | high (assessed deterministically)
    verification_required: bool    # gate: completion needs passing checks
    patch_proposal: Optional[PatchProposal]
    approval_required: bool
    approved: bool
    approval_rationale: str

    # --- Isolated execution ---
    worktree_path: Optional[str]
    worktree_branch: str

    # --- Verification ---
    verification_results: list[VerificationResult]
    verification_status: str       # passed | blocked | skipped | not_run
    retry_count: int
    max_retries: int

    # --- Review ---
    review_verdict: Optional[ReviewVerdict]
    review_notes: str

    # --- Report ---
    report: str

    # --- Tool log (task-scoped) ---
    tool_logs: list[dict[str, Any]]


def initial_task_state(
    *,
    repo_path: str,
    task_text: str,
    max_retries: int = 2,
) -> TaskState:
    """Build a fresh TaskState for a new task run."""
    return TaskState(
        repo_path=repo_path,
        task_text=task_text,
        phase="intake",
        phase_detail="Task accepted; validating request.",
        approval_required=False,
        approved=False,
        worktree_path=None,
        worktree_branch="",
        task_plan="",
        implementation_plan="",
        risk_level="low",
        verification_required=False,
        evidence=[],
        diagnoses=[],
        findings=[],
        selected_profiles=[],
        recommended_profiles=[],
        verification_results=[],
        verification_status="not_run",
        retry_count=0,
        max_retries=max_retries,
        review_verdict=None,
        review_notes="",
        report="",
        tool_logs=[],
        error=None,
    )