"""
Conversation State — LangGraph TypedDict for multi-turn, multi-agent conversations.

Tracks:
- Message history (user, agent, system)
- Active repository context (RAG)
- Agent findings (security, performance, architecture, devops)
- Cross-review debate rounds
- Tool invocation logs
- Consensus verdict
"""

from __future__ import annotations

from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph.message import add_messages


# ---------------------------------------------------------------------------
# Agent Finding — structured output from each specialist agent
# ---------------------------------------------------------------------------

class AgentFinding(TypedDict, total=False):
    """A single finding from a specialist agent."""

    agent: str  # "security", "performance", "architecture", "devops"
    severity: str  # "critical", "high", "medium", "low", "info"
    title: str
    description: str
    file_path: str
    line_start: int
    line_end: int
    code_snippet: str
    recommendation: str
    confidence: float  # 0.0 - 1.0


# ---------------------------------------------------------------------------
# Tool Call Log
# ---------------------------------------------------------------------------

class ToolCallLog(TypedDict, total=False):
    """Record of a tool invocation."""

    tool_name: str
    args: dict[str, Any]
    result_summary: str
    elapsed_ms: float
    success: bool
    error: Optional[str]


# ---------------------------------------------------------------------------
# Debate Round
# ---------------------------------------------------------------------------

class DebateRound(TypedDict, total=False):
    """One round of cross-review debate between agents."""

    round_number: int
    challenger: str  # agent name
    target_agent: str  # agent being challenged
    target_finding_index: int
    challenge: str
    rebuttal: str
    resolution: str  # "upheld", "dismissed", "modified"


# ---------------------------------------------------------------------------
# Main Conversation State
# ---------------------------------------------------------------------------

class ConversationState(TypedDict, total=False):
    """
    The full state graph for a ForgeAI conversation session.

    Messages accumulate via LangGraph's `add_messages` reducer so the full
    chat history is preserved across turns.
    """

    # --- Chat history (auto-reduced by add_messages) ---
    messages: Annotated[list, add_messages]

    # --- Repository context ---
    repo_path: str  # absolute path to the ingested repository
    repo_name: str  # display name
    repo_indexed: bool  # whether RAG index is built
    active_files: list[str]  # files currently in focus

    # --- RAG context ---
    retrieved_snippets: list[dict[str, Any]]  # top-k RAG results for current query

    # --- Agent findings ---
    security_findings: list[AgentFinding]
    performance_findings: list[AgentFinding]
    architecture_findings: list[AgentFinding]
    devops_findings: list[AgentFinding]

    # --- Cross-review debate ---
    debate_rounds: list[DebateRound]
    debate_active: bool
    debate_round_count: int

    # --- Consensus ---
    consensus_verdict: str  # final summary after debate
    consensus_score: float  # 0.0 - 1.0 overall quality score
    action_items: list[str]  # prioritized fix list

    # --- Tool logs ---
    tool_logs: list[ToolCallLog]

    # --- Orchestration ---
    current_phase: str  # "planning", "analysis", "debate", "consensus", "done"
    turn_count: int
    error: Optional[str]

    # --- Benchmarks ---
    inference_times: list[dict[str, Any]]  # per-call timing data
