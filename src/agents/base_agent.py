"""
Base Agent — abstract foundation for all ForgeAI specialist agents.

Each agent:
- Has a system prompt defining its role and expertise
- Can call tools via the ToolRegistry
- Can query the RAG store for code context
- Produces structured AgentFinding outputs
- Participates in cross-review debates
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from src.llm.rocm_service import ROCmLLM, InferenceResult
from src.state.conversation_state import AgentFinding
from src.tools.tool_registry import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for all specialist agents."""

    # Override in subclasses
    agent_name: str = "base"
    agent_emoji: str = "🤖"
    system_prompt: str = "You are a helpful code analysis agent."

    def __init__(
        self,
        llm: ROCmLLM,
        tool_registry: Optional[ToolRegistry] = None,
        rag_store: Any = None,  # RAGStore
    ) -> None:
        self.llm = llm
        self.tools = tool_registry
        self.rag = rag_store

    # ------------------------------------------------------------------
    # Core Analysis
    # ------------------------------------------------------------------

    @abstractmethod
    def analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """
        Analyze the user query with RAG context and produce findings.

        Args:
            user_query: The user's original question.
            rag_context: Top-k RAG results for context.
            conversation_history: Summary of prior turns.

        Returns:
            List of structured findings.
        """
        ...

    # ------------------------------------------------------------------
    # LLM Helpers
    # ------------------------------------------------------------------

    def _build_context_prompt(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> str:
        """Build a prompt combining user query, RAG context, and history."""
        parts = [f"## User Query\n{user_query}"]

        if rag_context:
            parts.append("\n## Relevant Code Snippets (RAG)")
            for i, snippet in enumerate(rag_context[:5], 1):
                parts.append(
                    f"\n### Snippet {i}: {snippet.get('file_path', 'unknown')} "
                    f"(lines {snippet.get('start_line', '?')}-{snippet.get('end_line', '?')}) "
                    f"[score: {snippet.get('score', 0):.2f}]"
                )
                parts.append(f"```{snippet.get('language', '')}\n{snippet.get('content', '')}\n```")

        if conversation_history:
            parts.append(f"\n## Conversation History\n{conversation_history}")

        return "\n".join(parts)

    def _call_llm(self, prompt: str, *, max_tokens: int = 1024) -> str:
        """Call the LLM with the agent's system prompt."""
        result = self.llm.generate(
            prompt,
            system_prompt=self.system_prompt,
            max_tokens=max_tokens,
        )
        return result.text

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Extract JSON from an LLM response (may be wrapped in markdown)."""
        # Try to find JSON block
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            text = json_match.group(1)

        # Try to find bare JSON object
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            text = json_match.group(0)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Attempt to repair truncated JSON by closing unclosed braces/brackets
            repaired = self._repair_truncated_json(text)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON from LLM response: %s", text[:200])
                return {"error": "JSON parse failed", "raw": text[:500]}

    @staticmethod
    def _repair_truncated_json(text: str) -> str:
        """Attempt to repair truncated JSON by balancing braces, brackets, and quotes."""
        # Check if we're inside an unclosed string (count unescaped quotes)
        quote_count = 0
        i = 0
        while i < len(text):
            if text[i] == '\\' and i + 1 < len(text):
                i += 2  # skip escaped character
                continue
            if text[i] == '"':
                quote_count += 1
            i += 1
        in_string = (quote_count % 2 == 1)

        # Close any unclosed string
        if in_string:
            text += '"'

        # Strip trailing incomplete element: `, "key`, `, "key": val`, `, {"b": 2`, etc.
        text = re.sub(r',\s*(?:"[^"]*"?\s*:?\s*[^\s,}\]]*|\{[^}]*)$', '', text)

        # Recompute after stripping
        open_braces = text.count("{") - text.count("}")
        open_brackets = text.count("[") - text.count("]")

        # Close unclosed braces and brackets
        text += "]" * open_brackets
        text += "}" * open_braces

        return text

    # ------------------------------------------------------------------
    # Tool Helpers
    # ------------------------------------------------------------------

    def _use_tool(self, tool_name: str, **kwargs: Any) -> ToolResult:
        """Invoke a tool and return the result."""
        if self.tools is None:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                summary="Tool registry not available.",
                error="no tool registry",
            )
        return self.tools.invoke(tool_name, **kwargs)

    def _format_tool_result(self, result: ToolResult) -> str:
        """Format a tool result for inclusion in an LLM prompt."""
        if not result.success:
            return f"Tool '{result.tool_name}' failed: {result.error or result.summary}"

        lines = [f"### Tool: {result.tool_name}", f"Summary: {result.summary}"]
        if result.details:
            lines.append(f"Details ({len(result.details)} items):")
            for d in result.details[:10]:
                lines.append(f"  - {json.dumps(d, default=str)[:300]}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Debate
    # ------------------------------------------------------------------

    def review_finding(
        self,
        finding: AgentFinding,
        context: str,
    ) -> dict[str, Any]:
        """
        Review another agent's finding during cross-review debate.

        Returns a dict with keys: verdict ('agree', 'disagree', 'modify'),
        reasoning, and optional modified_finding.
        """
        prompt = f"""Review this finding from the {finding.get('agent', 'unknown')} agent:

**Finding:** {finding.get('title', '')}
**Severity:** {finding.get('severity', '')}
**File:** {finding.get('file_path', '')}
**Description:** {finding.get('description', '')}
**Recommendation:** {finding.get('recommendation', '')}

Context: {context}

Respond with JSON:
{{"verdict": "agree|disagree|modify", "reasoning": "...", "modified_severity": "..."}}"""

        response = self._call_llm(prompt, max_tokens=512)
        return self._parse_json_response(response)

    # ------------------------------------------------------------------
    # Finding Factory
    # ------------------------------------------------------------------

    @staticmethod
    def make_finding(
        title: str,
        description: str,
        *,
        severity: str = "medium",
        file_path: str = "",
        line_start: int = 0,
        line_end: int = 0,
        code_snippet: str = "",
        recommendation: str = "",
        confidence: float = 0.7,
        agent: str = "",
    ) -> AgentFinding:
        """Create a standardized AgentFinding."""
        return AgentFinding(
            agent=agent,
            severity=severity,
            title=title,
            description=description,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            code_snippet=code_snippet,
            recommendation=recommendation,
            confidence=confidence,
        )
