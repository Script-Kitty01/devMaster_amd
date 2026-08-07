"""
Consensus Agent — synthesizes findings from all specialist agents, resolves
conflicts through cross-review debate, and produces a final verdict.

This is the "meta-agent" that ensures quality through multi-agent collaboration.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.state.conversation_state import AgentFinding, DebateRound

logger = logging.getLogger(__name__)

CONSENSUS_SYSTEM_PROMPT = """You are the **Consensus Agent** of Kutaar, an AI-powered code review assistant.

Your role:
1. Collect findings from all specialist agents (Security, Performance, Architecture, DevOps)
2. Identify conflicting or overlapping findings
3. Facilitate cross-review debate between agents
4. Produce a final, unified verdict with prioritized action items

You are the final arbiter. Your output should be:
- Comprehensive but not redundant
- Prioritized by severity and impact
- Actionable with clear next steps
- Include a quality score (0.0-1.0) for the codebase

Output your consensus as JSON:
{
  "verdict": "overall assessment summary",
  "score": 0.75,
  "top_findings": [...],
  "action_items": ["item 1", "item 2", ...],
  "debate_summary": "summary of any disagreements resolved"
}"""


class ConsensusAgent(BaseAgent):
    """Final arbiter that synthesizes and debates findings."""

    agent_name = "consensus"
    agent_emoji = "⚖️"
    system_prompt = CONSENSUS_SYSTEM_PROMPT

    def analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """Consensus doesn't produce findings directly — use synthesize() instead."""
        return []

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def synthesize(
        self,
        all_findings: dict[str, list[AgentFinding]],
        user_query: str,
    ) -> dict[str, Any]:
        """
        Synthesize findings from all agents into a unified verdict.

        Args:
            all_findings: Dict mapping agent_name -> list of findings.
            user_query: The original user query.

        Returns:
            Dict with verdict, score, action_items, top_findings.
        """
        # Build a summary of all findings
        findings_summary = self._summarize_findings(all_findings)

        prompt = f"""## User Query
{user_query}

## Findings from All Agents
{findings_summary}

Synthesize these findings into a final consensus. Remove duplicates, resolve conflicts,
prioritize by severity, and produce a unified verdict with a quality score (0.0-1.0).

Output as JSON with: verdict, score, action_items (list of strings), top_findings (most important 5)."""

        response = self._call_llm(prompt, max_tokens=1536)
        consensus = self._parse_json_response(response)

        logger.info(
            "Consensus: score=%.2f, action_items=%d",
            consensus.get("score", 0),
            len(consensus.get("action_items", [])),
        )

        return consensus

    # ------------------------------------------------------------------
    # Cross-Review Debate
    # ------------------------------------------------------------------

    def run_debate(
        self,
        agents: dict[str, BaseAgent],
        all_findings: dict[str, list[AgentFinding]],
        max_rounds: int = 2,
    ) -> list[DebateRound]:
        """
        Run cross-review debate rounds between agents.

        Each round: one agent challenges another agent's finding.
        The challenged agent provides a rebuttal.
        Consensus agent resolves.

        Returns list of DebateRound records.
        """
        debate_rounds: list[DebateRound] = []

        # Flatten findings with agent attribution
        flat_findings: list[tuple[str, int, AgentFinding]] = []
        for agent_name, findings in all_findings.items():
            for i, f in enumerate(findings):
                if f.get("severity") in ("critical", "high"):
                    flat_findings.append((agent_name, i, f))

        if len(flat_findings) < 2:
            logger.info("Not enough high-severity findings for debate.")
            return debate_rounds

        agent_names = list(agents.keys())
        round_num = 0

        for challenger_name in agent_names:
            if round_num >= max_rounds:
                break
            challenger = agents.get(challenger_name)
            if challenger is None or challenger_name == "consensus":
                continue

            # Pick a finding from a different agent to challenge
            for target_agent, target_idx, finding in flat_findings:
                if target_agent == challenger_name:
                    continue

                # Challenger reviews the finding
                review = challenger.review_finding(
                    finding,
                    context=f"Original query was about code review.",
                )

                verdict = review.get("verdict", "agree")
                if verdict == "agree":
                    continue  # No debate needed

                # Target agent rebuts
                target = agents.get(target_agent)
                rebuttal_text = ""
                if target:
                    rebuttal_prompt = f"""Another agent ({challenger_name}) disagrees with your finding:

**Your Finding:** {finding.get('title')}
**Challenge:** {review.get('reasoning', '')}

Defend or modify your finding. Output JSON: {{"rebuttal": "...", "modified": true/false, "modified_finding": {{...}}}}"""
                    rebuttal_response = target._call_llm(rebuttal_prompt, max_tokens=512)
                    rebuttal_parsed = target._parse_json_response(rebuttal_response)
                    rebuttal_text = rebuttal_parsed.get("rebuttal", "")

                # Consensus resolves
                resolution = "dismissed" if verdict == "disagree" else "modified"

                debate_rounds.append(
                    DebateRound(
                        round_number=round_num + 1,
                        challenger=challenger_name,
                        target_agent=target_agent,
                        target_finding_index=target_idx,
                        challenge=review.get("reasoning", ""),
                        rebuttal=rebuttal_text,
                        resolution=resolution,
                    )
                )

                round_num += 1
                break  # One challenge per challenger per round

        logger.info("Debate completed: %d rounds.", len(debate_rounds))
        return debate_rounds

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _summarize_findings(self, all_findings: dict[str, list[AgentFinding]]) -> str:
        """Create a text summary of all findings for the LLM."""
        parts = []
        total = 0

        for agent_name, findings in all_findings.items():
            parts.append(f"\n### {agent_name.upper()} ({len(findings)} findings)")
            for f in findings[:10]:  # Limit per agent
                parts.append(
                    f"- [{f.get('severity', '?').upper()}] {f.get('title', '')} "
                    f"({f.get('file_path', '')}:{f.get('line_start', '')})"
                )
                if f.get("description"):
                    parts.append(f"  {f.get('description', '')[:150]}")
            total += len(findings)

        parts.insert(0, f"Total findings across all agents: {total}")
        return "\n".join(parts)
