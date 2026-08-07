"""
Streamlit Chat UI — conversational interface for Kutaar.

Features:
- Chat interface with agent identity labels
- Expandable finding cards with severity badges
- Tool execution log panel
- Benchmark sidebar with ROCm metrics
- Repository upload & indexing
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

import streamlit as st

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
        "repo_path": "",
        "repo_indexed": False,
        "workflow": None,
        "llm": None,
        "rag_store": None,
        "tool_registry": None,
        "thread_id": f"kutaar-{int(time.time())}",
        "benchmark_results": None,
        "show_tools": False,
        "show_benchmarks": False,
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

        if st.session_state.repo_indexed:
            st.success(f"✅ Indexed: {Path(st.session_state.repo_path).name}")

        st.divider()

        # Model info
        st.subheader("🧠 Model")
        if st.session_state.llm and st.session_state.llm.is_ready:
            st.info(f"ROCm GPU — {st.session_state.llm.backend.upper()}")
        elif st.session_state.llm:
            st.warning(f"CPU Fallback — model not loaded")
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
    if prompt := st.chat_input("Ask about your codebase...", disabled=not st.session_state.repo_indexed):
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

    # Lazy-init components
    if st.session_state.llm is None:
        st.session_state.llm = ROCmLLM.get_instance()
        st.session_state.llm.initialize()

    if st.session_state.rag_store is None:
        st.session_state.rag_store = RAGStore(persist_dir="./chroma_db")
        st.session_state.rag_store.initialize()

    if st.session_state.tool_registry is None:
        st.session_state.tool_registry = ToolRegistry(st.session_state.repo_path)

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

    # Collect findings
    findings = []
    for agent_key in ["security", "performance", "architecture", "devops"]:
        for f in result.get(f"{agent_key}_findings", []):
            findings.append(dict(f))

    # Collect tool logs
    tool_logs = [dict(t) for t in result.get("tool_logs", [])]

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
