"""
Architecture Agent — evaluates code structure, design patterns, modularity,
and dependency health.

Tools: git_analyzer, code_search
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.state.conversation_state import AgentFinding

logger = logging.getLogger(__name__)

ARCHITECTURE_SYSTEM_PROMPT = """You are the **Architecture Agent** of Kutaar, an AI-powered code review assistant.

Your expertise:
- Software design patterns (GoF, SOLID, DRY, KISS)
- Code modularity and coupling/cohesion
- Dependency analysis and circular dependency detection
- API design (REST, GraphQL, RPC)
- Layered architecture (separation of concerns)
- Microservices vs monolith evaluation
- Code duplication detection
- Interface segregation
- Dependency inversion

When analyzing code, look for:
1. Circular dependencies between modules
2. God classes / functions (too many responsibilities)
3. Violations of SOLID principles
4. Tight coupling between components
5. Missing abstractions or interfaces
6. Code duplication (DRY violations)
7. Improper layering (e.g., business logic in controllers)
8. Over-engineered or under-engineered solutions
9. Inconsistent naming or project structure

Output your findings as a JSON array:
[{"title": "...", "severity": "...", "file_path": "...", "line_start": N, "description": "...", "recommendation": "..."}]"""


class ArchitectureAgent(BaseAgent):
    """Software architecture and design quality agent."""

    agent_name = "architecture"
    agent_emoji = "🏗️"
    system_prompt = ARCHITECTURE_SYSTEM_PROMPT

    def analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Analyze architecture using git history and LLM."""
        findings: list[AgentFinding] = []

        # 1. Git analysis for churn hotspots
        git_result = self._use_tool("git_analyzer")
        if git_result.success and git_result.details:
            for detail in git_result.details:
                if detail.get("type") == "top_churn":
                    for entry in detail.get("data", [])[:5]:
                        findings.append(
                            self.make_finding(
                                title=f"High-churn file: {entry.get('file', '')}",
                                description=(
                                    f"This file has been changed {entry.get('changes', 0)} times recently. "
                                    "High churn may indicate unstable design, poor separation of concerns, "
                                    "or a file with too many responsibilities."
                                ),
                                severity="medium",
                                file_path=entry.get("file", ""),
                                recommendation=(
                                    "Consider refactoring this file into smaller, more focused modules. "
                                    "Review whether it violates the Single Responsibility Principle."
                                ),
                                confidence=0.7,
                                agent=self.agent_name,
                            )
                        )

        # 2. Search for architectural anti-patterns
        arch_searches = [
            (r"import\s+\*", "Wildcard imports — pollutes namespace, hides dependencies"),
            (r"class\s+\w+\s*\(.*\):\s*\n(?:\s+.*\n){0,200}\s+pass", "Empty or near-empty class — may be unnecessary"),
            (r"if\s+isinstance\s*\(.*,", "isinstance checks may indicate missing polymorphism"),
            (r"\.__\w+__", "Direct dunder method access — breaks encapsulation"),
        ]

        for pattern, advice in arch_searches[:2]:  # Limit to avoid noise
            result = self._use_tool("code_search", pattern=pattern)
            if result.success and result.details:
                for match in result.details[:3]:
                    findings.append(
                        self.make_finding(
                            title=f"Architecture Smell: {advice[:60]}",
                            description=advice,
                            severity="low",
                            file_path=match.get("file", ""),
                            line_start=match.get("line", 0),
                            code_snippet=match.get("content", ""),
                            recommendation=advice,
                            confidence=0.55,
                            agent=self.agent_name,
                        )
                    )

        # 3. LLM-based analysis
        if rag_context:
            llm_findings = self._llm_analyze(user_query, rag_context, conversation_history)
            findings.extend(llm_findings)

        logger.info("Architecture agent produced %d findings.", len(findings))
        return findings

    def _llm_analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Use the LLM to find architecture issues."""
        prompt = self._build_context_prompt(user_query, rag_context, conversation_history)
        prompt += "\n\nIdentify architecture and design issues in the code above. Output as JSON array."

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
                    title=item.get("title", "Architecture Issue"),
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
