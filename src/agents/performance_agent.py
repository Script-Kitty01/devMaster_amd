"""
Performance Agent — identifies performance bottlenecks, inefficient patterns,
and optimization opportunities.

Focus: Algorithmic complexity, I/O patterns, memory usage, GPU utilization (ROCm).
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.state.conversation_state import AgentFinding

logger = logging.getLogger(__name__)

PERFORMANCE_SYSTEM_PROMPT = """You are the **Performance Agent** of Kutaar, an AI-powered code review assistant running on AMD ROCm.

Your expertise:
- Algorithmic complexity analysis (Big-O)
- Memory usage and leak detection
- I/O bottlenecks (disk, network, database)
- Concurrency and parallelism patterns
- GPU utilization (ROCm/HIP kernels, memory transfers)
- Caching strategies
- N+1 query detection
- Inefficient data structures

When analyzing code, look for:
1. O(n²) or worse algorithms on large datasets
2. Unnecessary copies of large objects
3. Blocking I/O in async contexts
4. Missing indexes or inefficient queries
5. Repeated computation that could be cached
6. Inefficient string concatenation in loops
7. Large memory allocations without cleanup
8. Synchronous operations that could be parallelized
9. GPU-specific: unnecessary host-device transfers, small kernel launches

Output your findings as a JSON array:
[{"title": "...", "severity": "...", "file_path": "...", "line_start": N, "description": "...", "recommendation": "..."}]"""


class PerformanceAgent(BaseAgent):
    """Performance analysis and optimization agent."""

    agent_name = "performance"
    agent_emoji = "⚡"
    system_prompt = PERFORMANCE_SYSTEM_PROMPT

    def analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Analyze code for performance issues using LLM + RAG context."""
        findings: list[AgentFinding] = []

        # 1. Search for common performance anti-patterns
        anti_patterns = [
            (r"for\s+\w+\s+in\s+range\s*\(.*\):\s*\n\s*.*\.append\(", "List append in loop — consider list comprehension"),
            (r"\+=\s*['\"]", "String concatenation in loop — use ''.join()"),
            (r"\.read\(\)|\.readlines\(\)", "Reading entire file into memory — consider streaming"),
            (r"time\.sleep\(", "time.sleep() blocks — consider asyncio.sleep() in async code"),
            (r"except\s*:\s*pass", "Bare except: pass — silently swallows errors"),
            (r"\.copy\(\)|deepcopy", "Potential unnecessary deep copy of large object"),
        ]

        for pattern, advice in anti_patterns:
            result = self._use_tool("code_search", pattern=pattern)
            if result.success and result.details:
                for match in result.details[:5]:
                    findings.append(
                        self.make_finding(
                            title=f"Performance Anti-pattern: {advice[:60]}",
                            description=f"Found pattern matching '{pattern}' — {advice}",
                            severity="medium",
                            file_path=match.get("file", ""),
                            line_start=match.get("line", 0),
                            code_snippet=match.get("content", ""),
                            recommendation=advice,
                            confidence=0.65,
                            agent=self.agent_name,
                        )
                    )

        # 2. LLM-based analysis of RAG context
        if rag_context:
            llm_findings = self._llm_analyze(user_query, rag_context, conversation_history)
            findings.extend(llm_findings)

        logger.info("Performance agent produced %d findings.", len(findings))
        return findings

    def _llm_analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Use the LLM to find performance issues in RAG-retrieved code."""
        prompt = self._build_context_prompt(user_query, rag_context, conversation_history)
        prompt += "\n\nIdentify performance bottlenecks and optimization opportunities in the code above. Output as JSON array."

        response = self._call_llm(prompt, max_tokens=1024)
        parsed = self._parse_json_response(response)

        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict) and "error" not in parsed:
            items = [parsed]
        else:
            return []

        findings: list[AgentFinding] = []
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            findings.append(
                self.make_finding(
                    title=item.get("title", "Performance Issue"),
                    description=item.get("description", ""),
                    severity=item.get("severity", "medium"),
                    file_path=item.get("file_path", ""),
                    line_start=item.get("line_start", 0),
                    code_snippet=item.get("code_snippet", ""),
                    recommendation=item.get("recommendation", ""),
                    confidence=0.7,
                    agent=self.agent_name,
                )
            )

        return findings
