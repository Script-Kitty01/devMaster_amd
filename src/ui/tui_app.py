"""Kutaar Textual TUI — full-screen local terminal UI (no browser/ports).

Usage: python -m src.ui.tui_app [--repo PATH] [--mode task|classic]
Keys: F2 index · F5 clear · F6 tools · Ctrl+Q quit. Slash cmds: /index /repo /mode /status /clear /help
"""
from __future__ import annotations
import argparse, logging, sys, time
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static

logger = logging.getLogger("kutaar.tui")
DEFAULT_REPO = str(PROJECT_ROOT / "demo_repos" / "fastapi_service")
PHASES = ["intake", "recon", "team", "investigate", "plan", "approval",
          "implement", "verify", "review", "report"]
SEV = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "🔵"}


class KutaarTUI(App):
    TITLE = "Kutaar 🔥 — AMD ROCm Engineering Assistant"
    CSS = (
        "#statusbar{height:3;border-bottom:solid $primary;padding:0 1;}"
        "#timeline{height:3;border-bottom:solid $primary;padding:0 1;}"
        "#main{height:1fr;}#chat{width:3fr;border-right:solid $primary;}"
        "#side{width:2fr;}#findings{height:1fr;min-height:6;}"
        "#tools{height:1fr;min-height:4;}#inputbar{height:3;padding:0 1;}"
    )
    BINDINGS = [Binding("ctrl+q", "quit", "Quit"),
                Binding("f2", "index_repo", "Index(F2)"),
                Binding("f5", "clear_chat", "Clear(F5)"),
                Binding("f6", "toggle_tools", "Tools(F6)")]

    def __init__(self, repo_path: str = DEFAULT_REPO, mode: str = "task") -> None:
        super().__init__()
        self.repo_path = repo_path
        self.mode = mode
        self.indexed_repo_path = ""
        self.repo_indexed = False
        self.llm: Any = None
        self.rag_store: Any = None
        self.tool_registry: Any = None
        self.workflow: Any = None
        self.task_workflow: Any = None
        self.thread_id = f"kutaar-{int(time.time())}"
        self.show_tools = True

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("starting…", id="statusbar")
        yield Static("timeline: —", id="timeline")
        with Horizontal(id="main"):
            with Vertical(id="chat"):
                yield RichLog(id="chatlog", wrap=True, highlight=True, markup=True)
            with Vertical(id="side"):
                yield Static("Findings (F6 hides tool log)", id="ftitle")
                yield DataTable(id="findings")
                yield RichLog(id="toollog", wrap=True, markup=False)
        with Horizontal(id="inputbar"):
            yield Input(placeholder="Ask about your codebase… (F2 indexes repo first)", id="input")
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one("#findings", DataTable)
        t.add_columns("Sev", "Title", "File", "Agent")
        self._status("initializing LLM…")
        try:
            from src.llm.rocm_service import ROCmLLM
            self.llm = ROCmLLM.get_instance()
            self.llm.initialize()
            d = self.llm.diagnostics()
            v = "verified" if d.get("backend_verified") else "UNVERIFIED"
            self._status(f"LLM {self.llm.backend.upper()} ({v}) · "
                         f"model={Path(str(d.get('model'))).name} · F2 to index repo")
        except Exception as exc:
            logger.exception("LLM init failed")
            self._status(f"LLM init failed: {exc}")
        self.query_one("#input", Input).focus()

    def _status(self, text: str) -> None:
        self.query_one("#statusbar", Static).update(f"[bold]Kutaar[/] · {text}")

    def _timeline(self, current: str = "", detail: str = "") -> None:
        if not current:
            self.query_one("#timeline", Static).update("timeline: —")
            return
        try:
            idx = PHASES.index(current)
        except ValueError:
            idx = len(PHASES) - 1
        bits = [(f"[green]● {p}[/]" if i < idx else f"[bold]● {p}[/]" if i == idx
                 else f"[dim]○ {p}[/]") for i, p in enumerate(PHASES)]
        self.query_one("#timeline", Static).update(" → ".join(bits) + (f" — {detail}" if detail else ""))

    def _chat(self, role: str, text: str) -> None:
        who = "[bold cyan]you[/]" if role == "user" else "[bold magenta]kutaar[/]"
        self.query_one("#chatlog", RichLog).write(f"{who}: {text}\n")

    def _tools(self, logs: list[dict]) -> None:
        if not self.show_tools:
            return
        log = self.query_one("#toollog", RichLog)
        for t in logs:
            ok = "OK" if t.get("success") else "FAIL"
            log.write(f"{ok} {t.get('tool_name', '?')} {t.get('elapsed_ms', 0):.0f}ms — {str(t.get('summary', ''))[:150]}")

    def _show_findings(self, findings: list[dict]) -> None:
        t = self.query_one("#findings", DataTable)
        t.clear()
        for f in findings[:50]:
            s = str(f.get("severity", "info"))
            t.add_row(f"{SEV.get(s, '○')} {s}", str(f.get("title", ""))[:60],
                      str(f.get("file_path", ""))[:30], str(f.get("agent", ""))[:12])

    def action_index_repo(self) -> None:
        self._index(self.repo_path)

    def action_clear_chat(self) -> None:
        self.query_one("#chatlog", RichLog).clear()
        self.query_one("#toollog", RichLog).clear()
        self.query_one("#findings", DataTable).clear()
        self.thread_id = f"kutaar-{int(time.time())}"
        self._chat("assistant", "chat cleared.")

    def action_toggle_tools(self) -> None:
        self.show_tools = not self.show_tools
        self._status(f"tool log {'shown' if self.show_tools else 'hidden'}")
    def _index(self, repo_path: str) -> None:
        if not repo_path or not Path(repo_path).exists():
            self._chat("assistant", f"path not found: {repo_path}")
            return
        self._chat("assistant", f"indexing {repo_path}...")
        try:
            from src.ingestion.repo_indexer import RepoIndexer
            from src.llm.rocm_service import ROCmLLM
            from src.rag.chroma_store import RAGStore
            if self.llm is None:
                self.llm = ROCmLLM.get_instance()
                self.llm.initialize()
            if self.indexed_repo_path != repo_path:
                self.tool_registry = None
                self.workflow = None
                self.thread_id = f"kutaar-{int(time.time())}"
            if self.rag_store is None:
                self.rag_store = RAGStore(persist_dir="./chroma_db")
                self.rag_store.initialize()
            idx = RepoIndexer(repo_path)
            chunks = idx.chunk_all()
            if not chunks:
                self._chat("assistant", "no code files found.")
                return
            m = getattr(self.llm.config, "embedding_model", "")
            n = self.rag_store.index_chunks(chunks, self.llm.embed, embedding_model=m)
            self.repo_indexed = True
            self.indexed_repo_path = repo_path
            self._chat("assistant", f"indexed {n} chunks from {idx.stats()['file_count']} files.")
            self._status(f"indexed {Path(repo_path).name} ({n} chunks)")
        except Exception as exc:
            logger.exception("index failed")
            self._chat("assistant", f"indexing failed: {exc}")

    @on(Input.Submitted, "#input")
    def _on_submit(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        event.input.value = ""
        if not prompt:
            return
        if prompt.startswith("/"):
            self._cmd(prompt)
            return
        self._ask(prompt)

    def _cmd(self, raw: str) -> None:
        p = raw.split(None, 1)
        cmd, arg = p[0].lower(), (p[1] if len(p) > 1 else "")
        if cmd in ("/quit", "/exit", "/q"):
            self.exit()
        elif cmd == "/index":
            self._index(arg or self.repo_path)
        elif cmd == "/repo":
            if arg and Path(arg).exists():
                self.repo_path = arg
                self._chat("assistant", "repo set - run /index.")
            else:
                self._chat("assistant", f"current repo: {self.repo_path}")
        elif cmd == "/mode":
            if arg.lower().startswith("classic"):
                self.mode = "classic"
            elif arg.lower().startswith("task"):
                self.mode = "task"
            self._chat("assistant", f"mode: {self.mode}")
        elif cmd == "/status":
            line = self.llm.status_line() if self.llm else "LLM not init"
            self._chat("assistant", f"{line} | repo={self.repo_path} | indexed={self.indexed_repo_path or 'no'} | mode={self.mode}")
        elif cmd == "/clear":
            self.action_clear_chat()
        elif cmd == "/help":
            self._chat("assistant", "/index [p] /repo [p] /mode task|classic /status /clear /quit + F2/F5/F6/Ctrl+Q")
        else:
            self._chat("assistant", f"unknown {cmd} - try /help.")

    def _ask(self, prompt: str) -> None:
        if not self.repo_indexed or self.indexed_repo_path != self.repo_path:
            self._chat("assistant", "press F2 (or /index) to index the repo first.")
            return
        self._chat("user", prompt)
        self._status("planning...")
        try:
            if self.mode == "task":
                text, findings, logs = self._run_task(prompt)
            else:
                text, findings, logs = self._run_classic(prompt)
            self._chat("assistant", text)
            if findings:
                self._show_findings(findings)
            self._tools(logs)
            self._status("ready.")
        except Exception as exc:
            logger.exception("workflow error")
            self._chat("assistant", f"error: {exc}")

    def _common(self) -> None:
        from src.llm.rocm_service import ROCmLLM
        from src.rag.chroma_store import RAGStore
        from src.tools.tool_registry import ToolRegistry
        if self.llm is None:
            self.llm = ROCmLLM.get_instance()
            self.llm.initialize()
        if self.rag_store is None:
            self.rag_store = RAGStore(persist_dir="./chroma_db")
            self.rag_store.initialize()
        if self.tool_registry is None:
            self.tool_registry = ToolRegistry(self.repo_path)

    def _run_classic(self, prompt: str):
        from langchain_core.messages import HumanMessage
        from src.graph.workflow import KutaarWorkflow
        self._common()
        if self.workflow is None:
            self.workflow = KutaarWorkflow(self.llm, self.rag_store, self.tool_registry).compile()
        res = self.workflow.invoke({"messages": [HumanMessage(content=prompt)], "repo_path": self.repo_path, "task_text": prompt}, config={"configurable": {"thread_id": self.thread_id}})
        msgs = res.get("messages", [])
        if msgs and hasattr(msgs[-1], "content"):
            text = msgs[-1].content
        elif msgs:
            text = str(msgs[-1])
        else:
            text = "Workflow done, no response."
        f: list[dict] = []
        for k in ("security", "performance", "architecture", "devops"):
            f += [dict(x) for x in res.get(f"{k}_findings", [])]
        return (text or "").strip() or "Workflow done, no response.", f, [dict(t) for t in res.get("tool_logs", [])]

    def _run_task(self, prompt: str):
        from src.graph.task_workflow import TaskWorkflow
        from src.state.task_state import initial_task_state
        self._common()
        if self.task_workflow is None:
            self.task_workflow = TaskWorkflow(self.llm, rag_store=self.rag_store, tool_registry=self.tool_registry).compile()
        res = self.task_workflow.invoke(initial_task_state(repo_path=self.repo_path, task_text=prompt))
        self._timeline(str(res.get("phase", "report")), str(res.get("phase_detail", "")))
        return res.get("report", "No report."), [dict(x) for x in res.get("findings", [])], [dict(t) for t in res.get("tool_logs", [])]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Kutaar Textual TUI - local terminal UI")
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument("--mode", default="task", choices=["task", "classic"])
    p.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main(argv: Optional[list[str]] = None) -> None:
    a = _parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, a.log_level.upper(), logging.WARNING))
    KutaarTUI(repo_path=a.repo, mode=a.mode).run()


if __name__ == "__main__":
    main()

