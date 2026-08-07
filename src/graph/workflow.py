"""
LangGraph Workflow — defines the multi-agent conversation graph.

Flow:
  User Input → Planner → [Security, Performance, Architecture, DevOps] (parallel)
  → Consensus (debate) → Response

Supports:
- Multi-turn conversation with checkpointing
- Parallel agent execution
- Cross-review debate rounds
- Tool invocation logging
- RAG context injection
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.state.conversation_state import ConversationState, AgentFinding, ToolCallLog
from src.llm.rocm_service import ROCmLLM
from src.rag.chroma_store import RAGStore
from src.tools.tool_registry import ToolRegistry
from src.agents.base_agent import BaseAgent
from src.agents.planner_agent import PlannerAgent
from src.agents.security_agent import SecurityAgent
from src.agents.performance_agent import PerformanceAgent
from src.agents.architecture_agent import ArchitectureAgent
from src.agents.devops_agent import DevOpsAgent
from src.agents.consensus_agent import ConsensusAgent

logger = logging.getLogger(__name__)


class KutaarWorkflow:
    """
    The main LangGraph workflow for Kutaar.

    Usage:
        wf = KutaarWorkflow(llm, rag_store, tool_registry)
        app = wf.compile()
        result = app.invoke({"messages": [HumanMessage("Review my code")], ...})
    """

    def __init__(
        self,
        llm: ROCmLLM,
        rag_store: RAGStore,
        tool_registry: ToolRegistry,
    ) -> None:
        self.llm = llm
        self.rag_store = rag_store
        self.tool_registry = tool_registry

        # Initialize agents
        self.planner = PlannerAgent(llm, tool_registry, rag_store)
        self.security = SecurityAgent(llm, tool_registry, rag_store)
        self.performance = PerformanceAgent(llm, tool_registry, rag_store)
        self.architecture = ArchitectureAgent(llm, tool_registry, rag_store)
        self.devops = DevOpsAgent(llm, tool_registry, rag_store)
        self.consensus = ConsensusAgent(llm, tool_registry, rag_store)

        self._specialists: dict[str, BaseAgent] = {
            "security": self.security,
            "performance": self.performance,
            "architecture": self.architecture,
            "devops": self.devops,
        }

    # ------------------------------------------------------------------
    # Graph Nodes
    # ------------------------------------------------------------------

    def _node_plan(self, state: ConversationState) -> dict:
        """Planner node: decompose query, decide which agents to run."""
        logger.info("[Workflow] Planning phase...")
        t0 = time.perf_counter()

        user_query = self._get_last_user_message(state)
        rag_context = state.get("retrieved_snippets", [])
        history = self._format_history(state)

        plan_findings = self.planner.analyze(user_query, rag_context, history)

        elapsed = (time.perf_counter() - t0) * 1000
        self._log_inference(state, "planner", elapsed)

        return {
            "current_phase": "analysis",
            "turn_count": state.get("turn_count", 0) + 1,
        }

    def _node_rag_retrieve(self, state: ConversationState) -> dict:
        """RAG node: retrieve relevant code snippets for the query."""
        if not self.rag_store.is_ready:
            return {"retrieved_snippets": []}

        user_query = self._get_last_user_message(state)
        snippets = self.rag_store.query(
            user_query,
            self.llm.embed,
            k=5,
        )
        logger.info("[Workflow] RAG retrieved %d snippets.", len(snippets))
        return {"retrieved_snippets": snippets}

    def _node_security(self, state: ConversationState) -> dict:
        return self._run_specialist(state, "security", self.security)

    def _node_performance(self, state: ConversationState) -> dict:
        return self._run_specialist(state, "performance", self.performance)

    def _node_architecture(self, state: ConversationState) -> dict:
        return self._run_specialist(state, "architecture", self.architecture)

    def _node_devops(self, state: ConversationState) -> dict:
        return self._run_specialist(state, "devops", self.devops)

    def _node_consensus(self, state: ConversationState) -> dict:
        """Consensus node: synthesize findings and run debate."""
        logger.info("[Workflow] Consensus phase...")
        t0 = time.perf_counter()

        all_findings = {
            "security": state.get("security_findings", []),
            "performance": state.get("performance_findings", []),
            "architecture": state.get("architecture_findings", []),
            "devops": state.get("devops_findings", []),
        }

        user_query = self._get_last_user_message(state)

        # Run cross-review debate
        debate_rounds = self.consensus.run_debate(
            self._specialists,
            all_findings,
            max_rounds=2,
        )

        # Synthesize final verdict
        consensus = self.consensus.synthesize(all_findings, user_query)

        elapsed = (time.perf_counter() - t0) * 1000
        self._log_inference(state, "consensus", elapsed)

        return {
            "current_phase": "done",
            "debate_rounds": debate_rounds,
            "debate_active": False,
            "debate_round_count": len(debate_rounds),
            "consensus_verdict": consensus.get("verdict", ""),
            "consensus_score": consensus.get("score", 0.0),
            "action_items": consensus.get("action_items", []),
        }

    def _node_format_response(self, state: ConversationState) -> dict:
        """Format the final response message."""
        from langchain_core.messages import AIMessage

        verdict = state.get("consensus_verdict", "")
        score = state.get("consensus_score", 0.0)
        action_items = state.get("action_items", [])

        # Count findings
        total_findings = (
            len(state.get("security_findings", []))
            + len(state.get("performance_findings", []))
            + len(state.get("architecture_findings", []))
            + len(state.get("devops_findings", []))
        )

        debate_count = len(state.get("debate_rounds", []))

        response_parts = [
            f"## Kutaar Analysis Complete\n",
            f"**Quality Score:** {score:.2f}/1.00 | **Findings:** {total_findings} | **Debate Rounds:** {debate_count}",
        ]

        if verdict:
            response_parts.append(f"\n### Verdict\n{verdict}")

        if action_items:
            response_parts.append("\n### Top Action Items")
            for i, item in enumerate(action_items[:5], 1):
                response_parts.append(f"{i}. {item}")

        # Summarize findings by agent
        for agent_key, label in [
            ("security", "🔒 Security"),
            ("performance", "⚡ Performance"),
            ("architecture", "🏗️ Architecture"),
            ("devops", "🚀 DevOps"),
        ]:
            findings = state.get(f"{agent_key}_findings", [])
            if findings:
                critical = sum(1 for f in findings if f.get("severity") == "critical")
                high = sum(1 for f in findings if f.get("severity") == "high")
                response_parts.append(
                    f"\n**{label}:** {len(findings)} findings"
                    + (f" ({critical} critical, {high} high)" if critical + high > 0 else "")
                )

        response_text = "\n".join(response_parts)

        return {
            "messages": [AIMessage(content=response_text)],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_specialist(
        self,
        state: ConversationState,
        agent_key: str,
        agent: BaseAgent,
    ) -> dict:
        """Run a specialist agent and store its findings."""
        logger.info("[Workflow] Running %s agent...", agent_key)
        t0 = time.perf_counter()

        user_query = self._get_last_user_message(state)
        rag_context = state.get("retrieved_snippets", [])
        history = self._format_history(state)

        findings = agent.analyze(user_query, rag_context, history)

        elapsed = (time.perf_counter() - t0) * 1000
        self._log_inference(state, agent_key, elapsed)

        return {f"{agent_key}_findings": findings}

    def _get_last_user_message(self, state: ConversationState) -> str:
        """Extract the last user message from the conversation."""
        messages = state.get("messages", [])
        for msg in reversed(messages):
            # Check for HumanMessage
            if hasattr(msg, "type") and msg.type == "human":
                return msg.content
            if hasattr(msg, "__class__") and "Human" in msg.__class__.__name__:
                return msg.content
        return "Analyze this codebase."

    def _format_history(self, state: ConversationState) -> str:
        """Format recent conversation history for agent context."""
        messages = state.get("messages", [])
        if not messages:
            return ""

        recent = messages[-6:]  # Last 3 turns
        lines = []
        for msg in recent:
            role = "User" if hasattr(msg, "type") and msg.type == "human" else "Assistant"
            content = msg.content if hasattr(msg, "content") else str(msg)
            lines.append(f"{role}: {content[:300]}")
        return "\n".join(lines)

    def _log_inference(self, state: ConversationState, agent: str, elapsed_ms: float) -> None:
        """Record inference timing for benchmarks."""
        times = state.get("inference_times", [])
        times.append({"agent": agent, "elapsed_ms": elapsed_ms, "backend": self.llm.backend})
        state["inference_times"] = times

    # ------------------------------------------------------------------
    # Graph Compilation
    # ------------------------------------------------------------------

    def compile(self) -> StateGraph:
        """
        Build and compile the LangGraph StateGraph.

        Returns a compiled graph ready for .invoke() or .stream().
        """
        builder = StateGraph(ConversationState)

        # Add nodes
        builder.add_node("plan", self._node_plan)
        builder.add_node("rag_retrieve", self._node_rag_retrieve)
        builder.add_node("security", self._node_security)
        builder.add_node("performance", self._node_performance)
        builder.add_node("architecture", self._node_architecture)
        builder.add_node("devops", self._node_devops)
        builder.add_node("consensus", self._node_consensus)
        builder.add_node("format_response", self._node_format_response)

        # Define edges
        builder.set_entry_point("plan")

        # Plan → RAG retrieve → parallel specialists
        builder.add_edge("plan", "rag_retrieve")

        # RAG → all specialists in parallel
        builder.add_edge("rag_retrieve", "security")
        builder.add_edge("rag_retrieve", "performance")
        builder.add_edge("rag_retrieve", "architecture")
        builder.add_edge("rag_retrieve", "devops")

        # All specialists → consensus
        builder.add_edge("security", "consensus")
        builder.add_edge("performance", "consensus")
        builder.add_edge("architecture", "consensus")
        builder.add_edge("devops", "consensus")

        # Consensus → format → END
        builder.add_edge("consensus", "format_response")
        builder.add_edge("format_response", END)

        # Compile with memory checkpointing for multi-turn
        memory = MemorySaver()
        app = builder.compile(checkpointer=memory)

        logger.info("LangGraph workflow compiled successfully.")
        return app
