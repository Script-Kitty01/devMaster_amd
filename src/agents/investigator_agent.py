"""
Investigator Agent — tool-observation loop with bounded budget.

Explores the repository, traces code paths, and records Evidence and
Diagnosis artifacts (plan §5, §7).  The investigator is the primary
"eyes on the ground" role: it reads files, searches code, traces
definitions and references, and builds an evidence chain that downstream
agents (implementation, review) can cite.

Key design constraints:
- Bounded observation budget: max_tool_calls from the profile limits.
- Every finding must cite at least one Evidence record.
- High/critical claims without evidence are downgraded to hypothesis.
- No mutation: the investigator only reads, never writes.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.agents.profiles import AgentProfile, get_profile
from src.models.artifacts import (
    Diagnosis,
    Evidence,
    evidence_from_tool_result,
    new_id,
    now_iso,
    validate_evidence,
    downgrade_finding_without_evidence,
)
from src.state.conversation_state import AgentFinding
from src.tools.tool_registry import ToolResult

logger = logging.getLogger(__name__)

INVESTIGATOR_SYSTEM_PROMPT = """You are the **Investigator Agent** of Kutaar, an evidence-driven engineering assistant.

Your mission:
- Explore the repository to understand the codebase structure and trace code paths.
- Record concrete observations as Evidence (tool name, file, line, excerpt).
- Formulate diagnoses that cite the evidence you collected.
- Never make high/critical claims without evidence — unsupported claims are downgraded.

Investigation strategy:
1. Start broad: repo_summary, list_files, import_graph to understand the landscape.
2. Narrow down: find_definition, find_references to trace specific code paths.
3. Deep read: read_file for the files most relevant to the user's question.
4. Cross-reference: semantic_search for related patterns.

For each observation, record:
- The tool that produced it
- The file and line range
- A short excerpt (≤2000 chars)
- Your confidence in the observation

Output your diagnoses as a JSON array:
[{"summary": "...", "root_cause_file": "...", "root_cause_lines": [N], "confidence": 0.8, "proposed_change": "..."}]

Remember: quality over quantity. A few well-supported diagnoses beat many unsupported claims."""


class InvestigatorAgent(BaseAgent):
    """Repository investigator with bounded tool-observation loop."""

    agent_name = "investigator"
    agent_emoji = "🔍"
    system_prompt = INVESTIGATOR_SYSTEM_PROMPT

    def __init__(
        self,
        llm: Any,
        tool_registry: Any = None,
        rag_store: Any = None,
        *,
        profile: Optional[AgentProfile] = None,
    ) -> None:
        super().__init__(llm, tool_registry, rag_store)
        self.profile = profile or get_profile("investigator")
        self._tool_calls = 0
        self._evidence: list[Evidence] = []

    @property
    def budget_remaining(self) -> int:
        return max(0, self.profile.limits.max_tool_calls - self._tool_calls)

    @property
    def evidence_collected(self) -> list[Evidence]:
        return list(self._evidence)

    # ------------------------------------------------------------------
    # Core Analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
        conversation_history: str,
    ) -> list[AgentFinding]:
        """
        Run the tool-observation loop and produce evidence-backed findings.

        The loop:
        1. Recon: repo_summary + list_files (2 tool calls)
        2. Targeted: find_definition / find_references / search_code (up to budget)
        3. Deep read: read_file for top candidates (remaining budget)
        4. LLM synthesis: produce diagnoses from collected evidence
        """
        self._tool_calls = 0
        self._evidence = []
        findings: list[AgentFinding] = []

        # Phase 1: Reconnaissance
        self._recon(user_query)

        # Phase 2: Targeted investigation based on user query
        self._targeted_search(user_query, rag_context)

        # Phase 3: Deep reads on most relevant files
        self._deep_reads()

        # Phase 4: LLM synthesis of evidence into diagnoses
        diagnoses = self._synthesize_diagnoses(user_query, conversation_history)

        # Phase 5: Convert diagnoses + evidence into AgentFindings
        for diag in diagnoses:
            finding = self._diagnosis_to_finding(diag)
            findings.append(finding)

        # Also produce findings from raw evidence that didn't make it into
        # a diagnosis (e.g., obvious issues spotted during recon).
        for ev in self._evidence:
            if not any(ev["id"] in d.get("linked_evidence_ids", []) for d in diagnoses):
                finding = self._evidence_to_finding(ev, user_query)
                if finding:
                    findings.append(finding)

        # Downgrade findings without evidence
        findings = [downgrade_finding_without_evidence(f) for f in findings]

        logger.info(
            "[Investigator] %d tool calls, %d evidence, %d findings",
            self._tool_calls,
            len(self._evidence),
            len(findings),
        )
        return findings

    # ------------------------------------------------------------------
    # Investigation Phases
    # ------------------------------------------------------------------

    def _recon(self, user_query: str) -> None:
        """Phase 1: Broad repository reconnaissance."""
        if self.budget_remaining < 1:
            return

        # Repo summary
        result = self._use_tool("repo_summary")
        self._tool_calls += 1
        if result.success:
            ev = evidence_from_tool_result(
                "repo_summary", result, excerpt=result.summary[:2000]
            )
            self._evidence.append(ev)

        if self.budget_remaining < 1:
            return

        # List files (top-level structure)
        result = self._use_tool("list_files", max_depth=2)
        self._tool_calls += 1
        if result.success:
            ev = evidence_from_tool_result(
                "list_files", result, excerpt=result.summary[:2000]
            )
            self._evidence.append(ev)

    def _targeted_search(
        self,
        user_query: str,
        rag_context: list[dict[str, Any]],
    ) -> None:
        """Phase 2: Targeted search based on the user query and RAG context."""
        # Use RAG context as starting points
        for snippet in rag_context[:3]:
            if self.budget_remaining < 1:
                break
            file_path = snippet.get("file_path", "")
            if file_path:
                result = self._use_tool("find_definition", symbol=file_path.split("/")[-1].replace(".py", ""))
                self._tool_calls += 1
                if result.success and result.details:
                    for d in result.details[:3]:
                        ev = evidence_from_tool_result(
                            "find_definition", result,
                            file_path=d.get("file", file_path),
                            line_start=d.get("line", 0),
                            excerpt=str(d.get("code", ""))[:2000],
                        )
                        self._evidence.append(ev)

        # Semantic search for the user's query
        if self.budget_remaining >= 1:
            result = self._use_tool("semantic_search", query=user_query, k=5)
            self._tool_calls += 1
            if result.success and result.details:
                for d in result.details[:5]:
                    ev = evidence_from_tool_result(
                        "semantic_search", result,
                        file_path=d.get("file_path", ""),
                        line_start=d.get("start_line", 0),
                        line_end=d.get("end_line", 0),
                        excerpt=str(d.get("content", ""))[:2000],
                    )
                    self._evidence.append(ev)

        # Import graph for structural understanding
        if self.budget_remaining >= 1:
            result = self._use_tool("import_graph")
            self._tool_calls += 1
            if result.success:
                ev = evidence_from_tool_result(
                    "import_graph", result, excerpt=result.summary[:2000]
                )
                self._evidence.append(ev)

    def _deep_reads(self) -> None:
        """Phase 3: Read the most-referenced files in evidence."""
        # Count file references in evidence
        file_counts: dict[str, int] = {}
        for ev in self._evidence:
            fp = ev.get("file_path", "")
            if fp:
                file_counts[fp] = file_counts.get(fp, 0) + 1

        # Read top files by reference count
        top_files = sorted(file_counts, key=file_counts.get, reverse=True)[:3]
        for fp in top_files:
            if self.budget_remaining < 1:
                break
            result = self._use_tool("read_file", file_path=fp)
            self._tool_calls += 1
            if result.success:
                ev = evidence_from_tool_result(
                    "read_file", result,
                    file_path=fp,
                    excerpt=result.raw_output[:2000],
                )
                self._evidence.append(ev)

    def _synthesize_diagnoses(
        self,
        user_query: str,
        conversation_history: str,
    ) -> list[Diagnosis]:
        """Phase 4: Ask the LLM to synthesize evidence into diagnoses."""
        if not self._evidence:
            return []

        evidence_summary = self._format_evidence()
        prompt = f"""## User Query
{user_query}

## Collected Evidence
{evidence_summary}

## Conversation History
{conversation_history or "None"}

Based on the evidence above, formulate diagnoses. Each diagnosis must:
1. Cite specific evidence IDs (from the "id" field)
2. Identify the root cause file and lines
3. State your confidence (0.0-1.0)
4. Propose a change direction (not a full patch)

Output as a JSON array:
[{{"summary": "...", "root_cause_file": "...", "root_cause_lines": [N], "linked_evidence_ids": ["ev-..."], "confidence": 0.8, "proposed_change": "..."}}]"""

        response = self._call_llm(prompt, max_tokens=1536)
        parsed = self._parse_json_response(response)

        diagnoses: list[Diagnosis] = []
        items = parsed if isinstance(parsed, list) else parsed.get("diagnoses", [parsed])
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            diag = Diagnosis(
                id=new_id("diag"),
                summary=item.get("summary", ""),
                root_cause_file=item.get("root_cause_file", ""),
                root_cause_lines=item.get("root_cause_lines", []),
                linked_evidence_ids=item.get("linked_evidence_ids", []),
                confidence=float(item.get("confidence", 0.5)),
                proposed_change=item.get("proposed_change", ""),
            )
            diagnoses.append(diag)

        return diagnoses

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _diagnosis_to_finding(self, diag: Diagnosis) -> AgentFinding:
        """Convert a Diagnosis into an AgentFinding with evidence linkage."""
        severity = "high" if diag.get("confidence", 0) >= 0.8 else "medium"
        return AgentFinding(
            agent=self.agent_name,
            severity=severity,
            title=diag.get("summary", "Diagnosis")[:120],
            description=diag.get("summary", ""),
            file_path=diag.get("root_cause_file", ""),
            line_start=diag.get("root_cause_lines", [0])[0] if diag.get("root_cause_lines") else 0,
            line_end=diag.get("root_cause_lines", [0])[-1] if diag.get("root_cause_lines") else 0,
            code_snippet="",
            recommendation=diag.get("proposed_change", ""),
            confidence=diag.get("confidence", 0.5),
            evidence_ids=diag.get("linked_evidence_ids", []),
            verification_status="verified" if diag.get("linked_evidence_ids") else "hypothesis",
            requires_fix=bool(diag.get("proposed_change")),
        )

    def _evidence_to_finding(
        self, ev: Evidence, user_query: str
    ) -> Optional[AgentFinding]:
        """Convert a standalone Evidence into a finding if it looks significant."""
        excerpt = ev.get("excerpt", "")
        # Only promote evidence that contains obvious issue markers
        issue_markers = ["TODO", "FIXME", "HACK", "BUG", "XXX", "deprecated"]
        if not any(m.lower() in excerpt.lower() for m in issue_markers):
            return None

        return AgentFinding(
            agent=self.agent_name,
            severity="low",
            title=f"Observation: {excerpt[:80]}",
            description=excerpt[:500],
            file_path=ev.get("file_path", ""),
            line_start=ev.get("line_start", 0),
            line_end=ev.get("line_end", 0),
            code_snippet=excerpt[:500],
            recommendation="Review this marker for potential issues.",
            confidence=0.4,
            evidence_ids=[ev.get("id", "")],
            verification_status="hypothesis",
            requires_fix=False,
        )

    def _format_evidence(self) -> str:
        """Format collected evidence for LLM consumption."""
        lines: list[str] = []
        for i, ev in enumerate(self._evidence[:20], 1):
            lines.append(
                f"### Evidence {i} [{ev.get('id', '?')}]\n"
                f"- Source: {ev.get('source', '?')}\n"
                f"- File: {ev.get('file_path', 'N/A')} "
                f"lines {ev.get('line_start', '?')}-{ev.get('line_end', '?')}\n"
                f"- Confidence: {ev.get('confidence', 0):.2f}\n"
                f"- Excerpt: {ev.get('excerpt', '')[:500]}\n"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Task-workflow entry point (used by TaskWorkflow, not ConversationState)
    # ------------------------------------------------------------------

    def investigate(
        self,
        *,
        task_text: str,
        repo_path: str,
        rag_context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Task-workflow entry point: returns evidence + diagnoses directly
        instead of AgentFindings.

        Returns:
            {"evidence": list[Evidence], "diagnoses": list[Diagnosis],
             "findings": list[AgentFinding], "tool_calls": int}
        """
        rag_context = rag_context or []
        findings = self.analyze(task_text, rag_context, "")
        return {
            "evidence": self._evidence,
            "diagnoses": [
                d for d in self._synthesize_diagnoses(task_text, "")
            ],
            "findings": findings,
            "tool_calls": self._tool_calls,
        }
