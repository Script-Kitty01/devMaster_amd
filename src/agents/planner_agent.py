"""
Planner Agent — orchestrates the analysis by decomposing user queries into
sub-tasks and dispatching to specialist agents.

Role: Understand user intent, plan the analysis strategy, and synthesize results.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.state.conversation_state import AgentFinding

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the **Planner Agent** of ForgeAI, an AI-powered code review assistant running on AMD ROCm.

Your role:
1. Understand the user's question about their codebase
2. Break it down into specific analysis tasks
3. Identify which specialist agents (Security, Performance, Architecture, DevOps) should contribute
4. Synthesize findings into a coherent response

You do NOT perform deep technical analysis yourself — you plan and coordinate.

Output your plan as JSON:
{
  "intent": "brief summary of what the user wants",
  "sub_tasks": [
    {"task": "...", "agent": "security|performance|architecture|devops", "priority": "high|medium|low"}
  ],
  "tools_to_run": ["bandit", "semgrep", ...],
  "rag_queries": ["query 1", "query 2"],
  "response_style": "detailed|concise|actionable"
}"""


class PlannerAgent(BaseAgent):
    """Orchestrator agent that plans and coordinates analysis."""

    agent_name = "planner"
    agent_emoji = "🧠"
    system_prompt = PLANNER_SYSTEM_PROMPT

    def analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Produce a plan, not findings. The plan is returned as a single 'info' finding."""
        prompt = self._build_context_prompt(user_query, rag_context, conversation_history)
        prompt += "\n\nProduce your analysis plan as JSON."

        response = self._call_llm(prompt, max_tokens=512)
        plan = self._parse_json_response(response)

        logger.info("Planner produced plan: %s", json.dumps(plan, default=str)[:300])

        return [
            self.make_finding(
                title=f"Analysis Plan: {plan.get('intent', user_query[:80])}",
                description=json.dumps(plan, indent=2),
                severity="info",
                confidence=0.9,
                agent=self.agent_name,
            )
        ]

    def parse_plan(self, response_text: str) -> dict[str, Any]:
        """Parse the LLM response into a structured plan dict."""
        return self._parse_json_response(response_text)
