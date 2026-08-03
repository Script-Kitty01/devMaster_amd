"""
Gradio Chat UI — conversational interface for ForgeAI.
Uses HTTP polling (not WebSockets) for proxy compatibility.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import gradio as gr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Globals (lazy init)
# ---------------------------------------------------------------------------
_llm = None
_rag_store = None
_tool_registry = None
_workflow = None
_repo_path = ""
_repo_indexed = False
_thread_id = f"forgeai-{int(time.time())}"

SEVERITY_COLORS = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🟢",
    "info": "🔵",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_components(repo_path: str):
    global _llm, _rag_store, _tool_registry, _workflow
    from src.llm.rocm_service import ROCmLLM
    from src.rag.chroma_store import RAGStore
    from src.tools.tool_registry import ToolRegistry

    if _llm is None:
        _llm = ROCmLLM.get_instance()
        _llm.initialize()
    if _rag_store is None:
        _rag_store = RAGStore(persist_dir="./chroma_db")
        _rag_store.initialize()
    if _tool_registry is None:
        _tool_registry = ToolRegistry(repo_path)


def _index_repo(repo_path: str) -> str:
    global _repo_indexed, _rag_store, _llm
    if not repo_path or not Path(repo_path).exists():
        return f"❌ Path not found: {repo_path}"

    try:
        from src.ingestion.repo_indexer import RepoIndexer
        _init_components(repo_path)

        indexer = RepoIndexer(repo_path)
        chunks = indexer.chunk_all()
        if not chunks:
            return "⚠️ No code files found."

        _rag_store.reset()
        count = _rag_store.index_chunks(chunks, _llm.embed)
        _repo_indexed = True
        stats = indexer.stats()
        return f"✅ Indexed {count} chunks from {stats['file_count']} files in `{Path(repo_path).name}`"
    except Exception as e:
        logger.exception("Index error")
        return f"❌ Indexing failed: {e}"


def _format_findings(findings: list[dict]) -> str:
    if not findings:
        return ""
    lines = ["\n---\n### 📋 Findings\n"]
    for f in findings[:15]:
        sev = f.get("severity", "info")
        emoji = SEVERITY_COLORS.get(sev, "⚪")
        agent = f.get("agent", "unknown")
        title = f.get("title", "Finding")
        desc = f.get("description", "")
        rec = f.get("recommendation", "")
        file_path = f.get("file_path", "")
        line = f.get("line_start", "")
        snippet = f.get("code_snippet", "")
        lang = f.get("language", "")

        lines.append(f"<details>")
        lines.append(f"<summary>{emoji} <b>[{sev.upper()}]</b> {title} — <i>{agent}</i></summary>")
        if desc:
            lines.append(f"<p><b>Description:</b> {desc}</p>")
        if rec:
            lines.append(f"<p><b>💡 Fix:</b> {rec}</p>")
        if file_path:
            lines.append(f"<p>📄 <code>{file_path}</code>{f' (line {line})' if line else ''}</p>")
        if snippet:
            lines.append(f"<pre><code class='language-{lang}'>{snippet}</code></pre>")
        lines.append(f"</details>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Chat handler
# ---------------------------------------------------------------------------

def chat_fn(message: str, history: list[dict], repo_path: str) -> tuple[str, list[dict]]:
    """Process a user message and return (empty_input, updated_history)."""
    global _repo_path, _repo_indexed, _thread_id, _workflow

    if not message.strip():
        return "", history

    _repo_path = repo_path
    if not _repo_indexed and repo_path:
        _index_repo(repo_path)

    try:
        from langchain_core.messages import HumanMessage
        from src.graph.workflow import ForgeAIWorkflow

        _init_components(repo_path)

        if _workflow is None:
            wf = ForgeAIWorkflow(_llm, _rag_store, _tool_registry)
            _workflow = wf.compile()

        config = {"configurable": {"thread_id": _thread_id}}
        result = _workflow.invoke(
            {
                "messages": [HumanMessage(content=message)],
                "repo_path": repo_path,
                "repo_name": Path(repo_path).name if repo_path else "",
                "repo_indexed": _repo_indexed,
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

        # Append findings
        if findings:
            response_text += _format_findings(findings)

        # Gradio 6.0 expects dict format: {"role": "...", "content": "..."}
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response_text})
        return "", history

    except Exception as e:
        logger.exception("Chat error")
        error_msg = f"❌ Error: {e}"
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": error_msg})
        return "", history


def index_handler(repo_path: str) -> str:
    return _index_repo(repo_path)


def clear_handler() -> tuple[list[dict], str]:
    global _thread_id
    _thread_id = f"forgeai-{int(time.time())}"
    return [], "Chat cleared."


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

CSS = """
.gradio-container { max-width: 900px !important; margin: auto !important; }
footer { display: none !important; }
"""

with gr.Blocks(title="ForgeAI — AMD ROCm Engineering Assistant") as demo:
    gr.Markdown(
        """# 🔥 ForgeAI
        **Multi-Agent AI Engineering Assistant** — Powered by AMD ROCm + LangGraph
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            repo_input = gr.Textbox(
                label="📂 Repository Path",
                placeholder="/workspace/demo_repos/sample_app",
                value="/workspace/demo_repos/sample_app",
            )
            with gr.Row():
                index_btn = gr.Button("🔍 Index Repo", size="sm")
                clear_btn = gr.Button("🗑️ Clear Chat", size="sm")
            index_status = gr.Markdown("")

            gr.Markdown("""---
            ### 🧠 Agents
            - 🧠 **Planner** — orchestrates analysis
            - 🔒 **Security** — finds vulnerabilities
            - ⚡ **Performance** — spots bottlenecks
            - 🏗️ **Architecture** — evaluates design
            - 🚀 **DevOps** — checks deployments
            - ⚖️ **Consensus** — cross-review & verdict

            Built for **AMD AI DevMaster Hackathon Track 2**
            """)

        with gr.Column(scale=3):
            chatbot = gr.Chatbot(label="Conversation", height=500)
            msg_input = gr.Textbox(
                label="Ask about your codebase...",
                placeholder="e.g., Find security vulnerabilities in this codebase",
                scale=4,
            )

    # Events
    msg_input.submit(chat_fn, [msg_input, chatbot, repo_input], [msg_input, chatbot])
    index_btn.click(index_handler, [repo_input], [index_status])
    clear_btn.click(clear_handler, [], [chatbot, index_status])

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        css=CSS,
    )
