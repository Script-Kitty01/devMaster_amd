"""
DevOps Agent — evaluates CI/CD, containerization, infrastructure-as-code,
and deployment readiness.

Tools: dockerfile_validator, code_search
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.state.conversation_state import AgentFinding

logger = logging.getLogger(__name__)

DEVOPS_SYSTEM_PROMPT = """You are the **DevOps Agent** of Kutaar, an AI-powered code review assistant.

Your expertise:
- Docker and containerization best practices
- Kubernetes manifests and Helm charts
- CI/CD pipeline configuration (GitHub Actions, GitLab CI, Jenkins)
- Infrastructure-as-Code (Terraform, Bicep, Pulumi)
- Cloud deployment patterns (Azure, AWS, GCP)
- Environment configuration management
- Secrets management
- Monitoring and observability setup
- Build optimization (caching, layer ordering)

When analyzing code, look for:
1. Dockerfiles without pinned base image versions
2. Containers running as root
3. Hardcoded secrets in config files
4. Missing health checks
5. Inefficient Docker layer caching
6. Missing resource limits in K8s manifests
7. CI/CD pipelines without security scanning steps
8. Environment-specific configs not externalized
9. Missing .dockerignore or .gitignore
10. Outdated base images with known CVEs

Output your findings as a JSON array:
[{"title": "...", "severity": "...", "file_path": "...", "line_start": N, "description": "...", "recommendation": "..."}]"""


class DevOpsAgent(BaseAgent):
    """DevOps and infrastructure quality agent."""

    agent_name = "devops"
    agent_emoji = "🚀"
    system_prompt = DEVOPS_SYSTEM_PROMPT

    def analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Analyze DevOps practices using dockerfile validator and LLM."""
        findings: list[AgentFinding] = []

        # 1. Dockerfile validation
        docker_result = self._use_tool("dockerfile_validator")
        if docker_result.success and docker_result.details:
            for df_detail in docker_result.details:
                for check in df_detail.get("checks", []):
                    if check.get("status") == "warning":
                        findings.append(
                            self.make_finding(
                                title=f"Docker: {check.get('check', 'Best Practice')}",
                                description=check.get("advice", ""),
                                severity="medium",
                                file_path=df_detail.get("file", ""),
                                recommendation=check.get("advice", ""),
                                confidence=0.8,
                                agent=self.agent_name,
                            )
                        )

        # 2. Search for hardcoded config issues
        config_searches = [
            (r"(password|passwd|secret|token|api_key|apikey)\s*[:=]\s*['\"]\S+['\"]", "Potential hardcoded secret"),
            (r"localhost:(\d+)", "Hardcoded localhost reference — may not work in containers"),
            (r"\.\./\.\./", "Deep relative path — fragile in containerized environments"),
        ]

        for pattern, advice in config_searches:
            result = self._use_tool("code_search", pattern=pattern)
            if result.success and result.details:
                for match in result.details[:3]:
                    findings.append(
                        self.make_finding(
                            title=f"DevOps Issue: {advice}",
                            description=f"Found pattern: {match.get('content', '')[:100]}",
                            severity="high" if "secret" in advice.lower() else "medium",
                            file_path=match.get("file", ""),
                            line_start=match.get("line", 0),
                            code_snippet=match.get("content", ""),
                            recommendation=advice,
                            confidence=0.7,
                            agent=self.agent_name,
                        )
                    )

        # 3. LLM-based analysis
        if rag_context:
            llm_findings = self._llm_analyze(user_query, rag_context, conversation_history)
            findings.extend(llm_findings)

        logger.info("DevOps agent produced %d findings.", len(findings))
        return findings

    def _llm_analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Use the LLM to find DevOps issues."""
        prompt = self._build_context_prompt(user_query, rag_context, conversation_history)
        prompt += "\n\nIdentify DevOps, containerization, and deployment issues in the code above. Output as JSON array."

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
                    title=item.get("title", "DevOps Issue"),
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
