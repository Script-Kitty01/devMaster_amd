"""
Streamlit Chat UI — conversational interface for Kutaar.

Features:
- Dual Modes: "Classic Review" (multi-agent code review) & "Task Mode" (evidence-driven autonomous repair)
- Task Mode: Phase timeline, profile selection, evidence links, diff preview, approval boundary, verification table
- Expandable finding cards with verification status & evidence citations
- Tool execution log panel
- Benchmark sidebar with ROCm metrics
- Repository upload & indexing
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_REPO_PATH = str(PROJECT_ROOT / "demo_repos" / "fastapi_service")

from src.agents.agent_registry import available_profiles
from src.state.task_state import initial_task_state
from src.graph.task_workflow import TaskWorkflow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Kutaar — AMD ROCm Engineering Assistant",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Session State Init
# ---------------------------------------------------------------------------

def init_session() -> None:
    """Initialize Streamlit session state."""
    defaults = {
        "messages": [],
        "repo_path": DEFAULT_REPO_PATH,
        "indexed_repo_path": "",
        "repo_indexed": False,
        "workflow": None,
        "task_workflow": None,
        "llm": None,
        "rag_store": None,
        "tool_registry": None,
        "thread_id": f"kutaar-{int(time.time())}",
        "benchmark_results": None,
        "show_tools": False,
        "show_benchmarks": False,
        "app_mode": "Task Mode (Autonomous)",
        "task_state": None,
        "selected_profiles": ["investigator", "security_reviewer", "review"],
        "task_intent": "Review",
        "pending_approval": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_session()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar() -> None:
    """Render the sidebar with config, repo upload, and benchmarks."""
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/artificial-intelligence.png", width=64)
        st.title("Kutaar 🔥")
        st.caption("Multi-Agent Engineering Assistant")
        st.caption("Powered by AMD ROCm + LangGraph")

        st.divider()

        # Repository section
        st.subheader("📂 Repository")
        repo_path = st.text_input(
            "Repository Path",
            key="repo_path",
            placeholder="e.g., C:\\Users\\Aamira\\my-project",
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔍 Index Repo", use_container_width=True):
                with st.spinner("Indexing repository..."):
                    _index_repository(st.session_state.repo_path)
        with col2:
            if st.button("🗑️ Clear Chat", use_container_width=True):
                st.session_state.messages = []
                st.session_state.thread_id = f"kutaar-{int(time.time())}"
                st.rerun()

        if (
            st.session_state.repo_indexed
            and st.session_state.indexed_repo_path == st.session_state.repo_path
        ):
            st.success(f"✅ Indexed: {Path(st.session_state.indexed_repo_path).name}")

        st.divider()

        st.subheader("Workspace Mode")
        st.session_state.app_mode = st.radio(
            "Workflow",
            ["Task Mode (Autonomous)", "Classic Review"],
            key="app_mode_selector",
        )
        if st.session_state.app_mode.startswith("Task"):
            st.session_state.task_intent = st.selectbox(
                "Task type", ["Review", "Diagnose", "Change"], key="task_intent_selector"
            )
            profiles = available_profiles()
            selected = st.multiselect(
                "Team profiles",
                options=list(profiles),
                default=[p for p in st.session_state.selected_profiles if p in profiles],
                format_func=lambda name: profiles[name].title,
            )
            st.session_state.selected_profiles = selected
            st.caption("Change tasks pause before worktree mutation for approval.")

        st.divider()

        # Model info
        st.subheader("🧠 Model")
        if st.session_state.llm and st.session_state.llm.is_ready:
            backend = st.session_state.llm.backend.upper()
            st.info(f"LLM backend — {backend}")
        elif st.session_state.llm:
            reason = getattr(st.session_state.llm, "fallback_reason", "") or "model not loaded"
            st.warning(f"LLM unavailable — {reason}")
        else:
            st.warning("LLM not initialized")

        st.divider()

        # Toggles
        st.subheader("⚙️ Options")
        st.session_state.show_tools = st.toggle("Show Tool Logs", value=False)
        st.session_state.show_benchmarks = st.toggle("Show Benchmarks", value=False)

        st.divider()

        # About
        with st.expander("ℹ️ About"):
            st.markdown("""
            **Kutaar** is a conversational multi-agent AI assistant for
            code review and engineering analysis.

            **Agents:**
            - 🧠 Planner — orchestrates analysis
            - 🔒 Security — finds vulnerabilities
            - ⚡ Performance — spots bottlenecks
            - 🏗️ Architecture — evaluates design
            - 🚀 DevOps — checks deployments
            - ⚖️ Consensus — cross-review & verdict

            **Built for:** AMD AI DevMaster Hackathon Track 2
            """)


# ---------------------------------------------------------------------------
# Repository Indexing
# ---------------------------------------------------------------------------

def _index_repository(repo_path: str) -> None:
    """Index a repository into the RAG store."""
    if not repo_path or not Path(repo_path).exists():
        st.error(f"Path not found: {repo_path}")
        return

    try:
        from src.ingestion.repo_indexer import RepoIndexer
        from src.rag.chroma_store import RAGStore
        from src.llm.rocm_service import ROCmLLM

        # Initialize if needed
        if st.session_state.llm is None:
            st.session_state.llm = ROCmLLM.get_instance()
            st.session_state.llm.initialize()

        # A different repository must not reuse tools or a checkpointed graph
        # that still points at the previous repository.
        if st.session_state.indexed_repo_path != repo_path:
            st.session_state.tool_registry = None
            st.session_state.workflow = None
            st.session_state.thread_id = f"kutaar-{int(time.time())}"

        if st.session_state.rag_store is None:
            st.session_state.rag_store = RAGStore(persist_dir="./chroma_db")
            st.session_state.rag_store.initialize()

        indexer = RepoIndexer(repo_path)
        chunks = indexer.chunk_all()

        if not chunks:
            st.warning("No code files found in repository.")
            return

        st.session_state.rag_store.reset()
        count = st.session_state.rag_store.index_chunks(
            chunks,
            st.session_state.llm.embed,
        )

        st.session_state.repo_indexed = True
        st.session_state.indexed_repo_path = repo_path
        st.session_state.repo_path = repo_path
        st.success(f"Indexed {count} code chunks from {indexer.stats()['file_count']} files.")

    except Exception as exc:
        st.error(f"Indexing failed: {exc}")
        logger.exception("Repository indexing error")


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def render_chat() -> None:
    """Render the main chat interface."""
    st.title("🔥 Kutaar")
    st.caption("Ask me anything about your codebase — I'll analyze it with my team of AI agents.")

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # Show findings if present
            if msg.get("findings"):
                _render_findings(msg["findings"])

            # Show tool logs if toggled
            if st.session_state.show_tools and msg.get("tool_logs"):
                _render_tool_logs(msg["tool_logs"])

    # Chat input
    active_repo_indexed = (
        st.session_state.repo_indexed
        and st.session_state.indexed_repo_path == st.session_state.repo_path
    )
    if prompt := st.chat_input("Ask about your codebase...", disabled=not active_repo_indexed):
        _handle_user_message(prompt)


def _handle_user_message(prompt: str) -> None:
    """Process a user message through the workflow."""
    from langchain_core.messages import HumanMessage, AIMessage

    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # Run workflow (spinner only wraps computation, not rendering)
    with st.chat_message("assistant"):
        try:
            with st.spinner("🧠 Planning analysis..."):
                response_text, findings, tool_logs = _run_workflow(prompt)
            # Render outside spinner so it properly exits
            st.markdown(response_text)
            if findings:
                _render_findings(findings)
            if st.session_state.show_tools and tool_logs:
                _render_tool_logs(tool_logs)

            st.session_state.messages.append({
                "role": "assistant",
                "content": response_text,
                "findings": findings,
                "tool_logs": tool_logs,
            })
        except Exception as exc:
            error_msg = f"❌ Error: {exc}"
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
            logger.exception("Workflow error")


def _run_workflow(prompt: str) -> tuple[str, list[dict], list[dict]]:
    """Execute the LangGraph workflow and return results."""
    from langchain_core.messages import HumanMessage
    from src.llm.rocm_service import ROCmLLM
    from src.rag.chroma_store import RAGStore
    from src.tools.tool_registry import ToolRegistry
    from src.graph.workflow import KutaarWorkflow

    if st.session_state.indexed_repo_path != st.session_state.repo_path:
        raise ValueError("Index the selected repository before starting a chat.")

    # Lazy-init components
    if st.session_state.llm is None:
        st.session_state.llm = ROCmLLM.get_instance()
        st.session_state.llm.initialize()

    if st.session_state.rag_store is None:
        st.session_state.rag_store = RAGStore(persist_dir="./chroma_db")
        st.session_state.rag_store.initialize()

    if st.session_state.tool_registry is None:
        st.session_state.tool_registry = ToolRegistry(st.session_state.repo_path)

    if st.session_state.app_mode.startswith("Task"):
        return _run_task_workflow(prompt)

    if st.session_state.workflow is None:
        wf = KutaarWorkflow(
            st.session_state.llm,
            st.session_state.rag_store,
            st.session_state.tool_registry,
        )
        st.session_state.workflow = wf.compile()

    # Invoke
    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    result = st.session_state.workflow.invoke(
        {
            "messages": [HumanMessage(content=prompt)],
            "repo_path": st.session_state.repo_path,
            "repo_name": Path(st.session_state.repo_path).name,
            "repo_indexed": st.session_state.repo_indexed,
            "current_phase": "planning",
            "turn_count": 0,
        },
        config=config,
    )

    # Extract response
    messages = result.get("messages", [])
    response_text = ""
    if messages:
        last_msg = messages[-1]
        response_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    if not response_text.strip():
        response_text = "The workflow completed without a response. Check the LLM service logs and try again."

    # Collect findings
    findings = []
    for agent_key in ["security", "performance", "architecture", "devops"]:
        for f in result.get(f"{agent_key}_findings", []):
            findings.append(dict(f))

    # Collect tool logs
    tool_logs = [dict(t) for t in result.get("tool_logs", [])]

    return response_text, findings, tool_logs


def _run_task_workflow(prompt: str) -> tuple[str, list[dict], list[dict]]:
    """Run the evidence-driven task graph and render its state as chat output."""
    if st.session_state.task_workflow is None:
        st.session_state.task_workflow = TaskWorkflow(
            st.session_state.llm,
            rag_store=st.session_state.rag_store,
            tool_registry=st.session_state.tool_registry,
        ).compile()

    result = st.session_state.task_workflow.invoke(
        initial_task_state(
            repo_path=st.session_state.repo_path,
            task_text=prompt,
        ) | {"selected_profiles": st.session_state.selected_profiles},
    )
    st.session_state.task_state = result

    response_text = result.get("report", "Task workflow did not produce a report.")
    findings = [dict(f) for f in result.get("findings", [])]
    tool_logs = [dict(t) for t in result.get("tool_logs", [])]

    with st.expander("Task timeline", expanded=True):
        phases = ["intake", "recon", "team", "investigate", "plan", "approval", "implement", "verify", "review", "report"]
        current = result.get("phase", "report")
        st.write(" → ".join(("✅ " if p == current or phases.index(p) < phases.index(current) else "○ ") + p.title() for p in phases))
        st.caption(result.get("phase_detail", ""))
        st.caption(f"Worktree: {result.get('worktree_path') or 'not created'} | Branch: {result.get('worktree_branch') or 'none'}")

    if result.get("patch_proposal"):
        proposal = result["patch_proposal"]
        with st.expander("Patch proposal", expanded=True):
            st.write(proposal.get("summary", ""))
            st.caption(f"Risk: {proposal.get('risk_level', 'unknown')} | Files: {', '.join(proposal.get('files_changed', []))}")
            if proposal.get("unified_diff"):
                st.code(proposal["unified_diff"], language="diff")
            st.caption(f"Evidence: {', '.join(proposal.get('linked_evidence_ids', [])) or 'none'}")

        if result.get("approval_required") and not result.get("approved"):
            if st.button("Approve and run in isolated worktree", type="primary"):
                approved_state = dict(result)
                approved_state["approved"] = True
                approved_state["phase"] = "approval"
                result = st.session_state.task_workflow.invoke(approved_state)
                st.session_state.task_state = result

    if result.get("verification_results"):
        with st.expander("Verification", expanded=True):
            st.dataframe([
                {"check": v.get("name"), "status": v.get("status"), "exit": v.get("exit_code"), "summary": v.get("summary", "")}
                for v in result["verification_results"]
            ], use_container_width=True, hide_index=True)

    return response_text, findings, tool_logs


# ---------------------------------------------------------------------------
# Finding Cards
# ---------------------------------------------------------------------------

def _render_findings(findings: list[dict]) -> None:
    """Render expandable finding cards with severity badges."""
    if not findings:
        return

    severity_colors = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
        "info": "🔵",
    }

    st.markdown("---")
    st.markdown(f"### 📋 Findings ({len(findings)})")

    for i, f in enumerate(findings[:20]):
        sev = f.get("severity", "info")
        emoji = severity_colors.get(sev, "⚪")
        agent = f.get("agent", "unknown")

        with st.expander(f"{emoji} [{sev.upper()}] {f.get('title', 'Finding')} — {agent}"):
            col1, col2 = st.columns([2, 1])
            with col1:
                if f.get("description"):
                    st.markdown(f"**Description:** {f['description']}")
                if f.get("recommendation"):
                    st.markdown(f"**💡 Fix:** {f['recommendation']}")
            with col2:
                if f.get("file_path"):
                    st.caption(f"📄 `{f['file_path']}`")
                if f.get("line_start"):
                    st.caption(f"📍 Line {f['line_start']}")
                if f.get("confidence"):
                    st.progress(f["confidence"], text=f"Confidence: {f['confidence']:.0%}")

            if f.get("code_snippet"):
                lang = f.get("language", "")
                st.code(f["code_snippet"], language=lang if lang else None)


# ---------------------------------------------------------------------------
# Tool Logs
# ---------------------------------------------------------------------------

def _render_tool_logs(tool_logs: list[dict]) -> None:
    """Render tool execution logs."""
    if not tool_logs:
        return

    st.markdown("---")
    st.markdown("### 🔧 Tool Execution Logs")

    for log in tool_logs:
        status = "✅" if log.get("success") else "❌"
        st.caption(
            f"{status} **{log.get('tool_name', 'unknown')}** "
            f"— {log.get('elapsed_ms', 0):.0f}ms"
        )
        if log.get("summary"):
            st.caption(f"  {log['summary'][:200]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point for the Streamlit app."""
    render_sidebar()
    render_chat()


if __name__ == "__main__":
    main()
