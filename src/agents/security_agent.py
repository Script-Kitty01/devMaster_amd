"""
Security Agent — identifies vulnerabilities, insecure patterns, and CVEs.

Tools: Bandit, Semgrep, code_search (for dangerous patterns)
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.state.conversation_state import AgentFinding

logger = logging.getLogger(__name__)

SECURITY_SYSTEM_PROMPT = """You are the **Security Agent** of ForgeAI, an AI-powered code review assistant.

Your expertise:
- OWASP Top 10 vulnerabilities (injection, broken auth, XSS, misconfigurations, etc.)
- CWE detection in source code
- Secret/hardcoded credential detection
- Input validation and sanitization
- Authentication and authorization flaws
- Dependency security (known CVEs)

When analyzing code, look for:
1. SQL/command injection (unsanitized input in queries/commands)
2. Hardcoded secrets (API keys, passwords, tokens)
3. Weak cryptography (MD5, SHA1, DES, hardcoded IVs)
4. Insecure deserialization (pickle, yaml.load, eval)
5. Missing input validation
6. Path traversal vulnerabilities
7. Insecure file permissions
8. Missing HTTPS/TLS enforcement

For each finding, provide:
- Severity (critical/high/medium/low)
- The exact file and line
- A clear description of the risk
- A concrete fix recommendation

Output your findings as a JSON array:
[{"title": "...", "severity": "...", "file_path": "...", "line_start": N, "description": "...", "recommendation": "..."}]"""


class SecurityAgent(BaseAgent):
    """Security vulnerability detection agent."""

    agent_name = "security"
    agent_emoji = "🔒"
    system_prompt = SECURITY_SYSTEM_PROMPT

    def analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Run security tools and analyze code for vulnerabilities."""
        findings: list[AgentFinding] = []

        # 1. Run Bandit if available
        bandit_result = self._use_tool("bandit")
        if bandit_result.success and bandit_result.details:
            for issue in bandit_result.details[:15]:
                findings.append(
                    self.make_finding(
                        title=f"[Bandit] {issue.get('test', 'Security Issue')}",
                        description=issue.get("message", ""),
                        severity=self._map_bandit_severity(issue.get("severity", "low")),
                        file_path=issue.get("file", ""),
                        line_start=issue.get("line", 0),
                        code_snippet=issue.get("code", ""),
                        recommendation=f"Review and fix per Bandit rule: {issue.get('test', '')}",
                        confidence=float(issue.get("confidence", "medium") == "high" and 0.9 or 0.6),
                        agent=self.agent_name,
                    )
                )

        # 2. Run Semgrep if available
        semgrep_result = self._use_tool("semgrep")
        if semgrep_result.success and semgrep_result.details:
            for issue in semgrep_result.details[:15]:
                findings.append(
                    self.make_finding(
                        title=f"[Semgrep] {issue.get('check_id', 'Pattern Match')}",
                        description=issue.get("message", ""),
                        severity=self._map_semgrep_severity(issue.get("severity", "medium")),
                        file_path=issue.get("file", ""),
                        line_start=issue.get("line", 0),
                        recommendation=f"Address Semgrep finding: {issue.get('check_id', '')}",
                        confidence=0.75,
                        agent=self.agent_name,
                    )
                )

        # 3. LLM-based analysis of RAG context
        if rag_context:
            llm_findings = self._llm_analyze(user_query, rag_context, conversation_history)
            findings.extend(llm_findings)

        logger.info("Security agent produced %d findings.", len(findings))
        return findings

    def _llm_analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Use the LLM to find security issues in RAG-retrieved code."""
        prompt = self._build_context_prompt(user_query, rag_context, conversation_history)
        prompt += "\n\nIdentify security vulnerabilities in the code above. Output as JSON array."

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
                    title=item.get("title", "Security Issue"),
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

    @staticmethod
    def _map_bandit_severity(sev: str) -> str:
        mapping = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
        return mapping.get(sev.upper(), "medium")

    @staticmethod
    def _map_semgrep_severity(sev: str) -> str:
        mapping = {"ERROR": "critical", "WARNING": "high", "INFO": "medium"}
        return mapping.get(sev.upper(), "medium")
