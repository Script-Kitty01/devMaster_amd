"""Kutaar Console TUI - PROTOS-style fullscreen dashboard.

Layout mirrors the screenshot you sent:
  left   : TOOLS - every registered agent tool (red > prefix)
  center : KUTAAR banner, quick start, action buttons, chat stream,
           ask-input + backend selector, key-hint footer
  right  : MODEL ROUTING, TASK PHASES, EVIDENCE CHAIN, SYSTEM bars
           (psutil CPU/MEM/NET/DSK + per-core + freq), AGENT STREAM

Run: .venv\\Scripts\\python.exe -m src.ui.console_tui [--repo PATH]
Keys: Ctrl+P palette, F1 help, F2 index, F3 mode, Ctrl+L clear, Ctrl+Q quit.
Type /help in the input for slash commands. Buttons run preset audits.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_REPO = str(PROJECT_ROOT / "demo_repos" / "fastapi_service")

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (Button, DataTable, Footer, Header, Input,
                             Label, ListItem, ListView, RichLog, Select,
                             Static)

logger = logging.getLogger("kutaar.console")

BANNER = (
    "[bold red]██╗  ██╗[/][bold orange1]██╗   ██╗[/][bold orange1]████████╗[/]"
    "[bold yellow] █████╗  [/][bold yellow] █████╗ [/][bold green]██████╗ [/]\n"
    "[bold red]██║ ██╔╝[/][bold orange1]██║   ██║[/][bold orange1]╚══██╔══╝[/]"
    "[bold yellow]██╔══██╗[/][bold yellow]██╔══██╗[/][bold green]██╔══██╗[/]\n"
    "[bold red]█████╔╝ [/][bold orange1]██║   ██║[/][bold orange1]   ██║   [/]"
    "[bold yellow]███████║[/][bold yellow]███████║[/][bold green]██████╔╝[/]\n"
    "[bold red]██╔═██╗ [/][bold orange1]██║   ██║[/][bold orange1]   ██║   [/]"
    "[bold yellow]██╔══██║[/][bold yellow]██╔══██║[/][bold green]██╔══██╗[/]\n"
    "[bold red]██║  ██╗[/][bold orange1]╚██████╔╝[/][bold orange1]   ██║   [/]"
    "[bold yellow]██║  ██║[/][bold yellow]██║  ██║[/][bold green]██║  ██║[/]\n"
    "[bold red]╚═╝  ╚═╝[/][bold orange1] ╚═════╝ [/][bold orange1]   ╚═╝   [/]"
    "[bold yellow]╚═╝  ╚═╝[/][bold yellow]╚═╝  ╚═╝[/][bold green]╚═╝  ╚═╝[/]"
)

SUBTITLE = ("[bold]Kutaar - Universal Engineering Agent[/]\n"
            "[dim]AMD Hackathon  -  Local Inference  -  Privacy-First[/]")

QUICK = ('[cyan]-- QUICK START --[/]\nTry: "[red]Scan this repo for '
         'security issues[/]"\n[red]Ctrl+P[/] command palette   '
         '[red]Ctrl+,[/] settings   [red]F1[/] help')

PHASES = ["intake", "recon", "team", "investigate", "plan", "approval",
          "implement", "verify", "review", "report"]
SEV = {"critical": "R", "high": "H", "medium": "M", "low": "L", "info": "I"}

PRESETS = {
    "SECURITY AUDIT": "Run a security audit: hardcoded secrets, injection, "
                      "weak crypto, insecure deserialization. Cite file:line.",
    "ANALYZE CODE": "Review this repo for bugs, smells and architecture "
                    "issues. Prioritize findings with evidence.",
    "SYSTEM INFO": "Describe the repository structure: languages, entry "
                   "points, tests, Docker/CI presence.",
    "DIAGNOSTICS": "Check repo health: failing patterns, missing configs, "
                   "readiness gaps. List concrete files.",
    "INDEX REPO": "__INDEX__",
}

TOOL_BLURBS = [
    ("bandit", "python security scan"),
    ("semgrep", "multi-lang pattern scan"),
    ("secret_scan", "hardcoded secret hunt"),
    ("dependency_audit", "vulnerable deps"),
    ("code_search", "regex search repo"),
    ("read_file", "read file:lines"),
    ("list_files", "repo tree walk"),
    ("repo_summary", "structure summary"),
    ("git_log", "history + churn"),
    ("git_diff", "unified diff"),
    ("python_ast_summary", "symbols per file"),
    ("find_definition", "jump to symbol"),
    ("find_references", "who calls it"),
    ("import_graph", "coupling map"),
    ("semantic_search", "RAG retrieval"),
    ("dockerfile_validator", "docker best practice"),
    ("discover_checks", "find tests/lint"),
    ("run_test", "pytest in worktree"),
    ("run_linter", "lint gate"),
    ("run_build", "build gate"),
    ("clipboard_handler", "copy report/diff"),
    ("pdf_ingest", "index *.pdf docs"),
]


@dataclass
class ConsoleState:
    repo_path: str = DEFAULT_REPO
    indexed_repo_path: str = ""
    repo_indexed: bool = False
    mode: str = "task"
    task_intent: str = "Review"
    profiles: list[str] = field(default_factory=lambda: [
        "investigator", "security_reviewer", "review"])
    constraints: list[str] = field(default_factory=list)
    auto_approve: bool = False
    llm: Any = None
    rag: Any = None
    tools: Any = None
    workflow: Any = None
    task_workflow: Any = None
    thread_id: str = field(default_factory=lambda: f"kutaar-{int(time.time())}")
    net_prev: Any = None
    net_t: float = 0.0

def sys_snapshot() -> dict:
    """CPU/MEM/DSK/NET + per-core + freq via psutil; zeros when missing."""
    snap: dict = {"cpu": 0.0, "mem": 0.0, "cores": [], "freq": 0.0,
                  "net_rate": 0.0, "disk_io": 0.0, "ok": False}
    try:
        import psutil  # type: ignore
    except Exception:
        return snap
    try:
        snap["cpu"] = float(psutil.cpu_percent(interval=None))
        snap["mem"] = float(psutil.virtual_memory().percent)
        try:
            snap["cores"] = [float(c) for c in
                             psutil.cpu_percent(interval=None, percpu=True)]
        except Exception:  # noqa: BLE001
            snap["cores"] = []
        try:
            freq = psutil.cpu_freq()
            snap["freq"] = float(freq.current / 1000) if freq else 0.0
        except Exception:  # noqa: BLE001
            snap["freq"] = 0.0
        try:
            disk = psutil.disk_usage(str(Path.cwd().anchor))
            snap["disk_pct"] = float(disk.percent)
            snap["disk_free"] = float(disk.free / 1e9)
        except Exception:  # noqa: BLE001
            snap["disk_pct"], snap["disk_free"] = 0.0, 0.0
        snap["ok"] = True
    except Exception:  # noqa: BLE001
        snap["ok"] = False
    return snap


def bar(pct: float, width: int = 22) -> str:
    pct = max(0.0, min(100.0, pct))
    fill = int(round(pct / 100 * width))
    return "[" + "#" * fill + "-" * (width - fill) + "]"


class KutaarConsole(App):
    """PROTOS-style 3-column fullscreen console for Kutaar."""

    TITLE = "KUTAAR // UNIVERSAL ENGINEERING AGENT - AMD Hackathon"
    CSS = """
    #top{height:1;}
    #body{height:1fr;}
    #tools{width:24;border-right:solid $primary;}
    #center{width:1fr;}
    #right{width:34;border-left:solid $primary;}
    #banner{height:9;padding:0 1;}
    #sub{height:4;padding:0 1;}
    #quick{height:5;padding:0 1;}
    #presets{height:3;padding:0 1;}
    #stream{height:1fr;border-top:solid $primary;border-bottom:solid $primary;}
    #askrow{height:3;padding:0 1;}
    #ask{width:3fr;}
    #backend{width:1fr;}
    #hints{height:1;}
    .panel{padding:0 1;}
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+p", "palette", "Commands"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("f1", "help", "Help"),
        Binding("f2", "index", "Index(F2)"),
        Binding("f3", "mode", "Mode(F3)"),
    ]

    def __init__(self, repo_path: str = DEFAULT_REPO,
                 mode: str = "task") -> None:
        super().__init__()
        self.S = ConsoleState(repo_path=repo_path, mode=mode)
        self._net_prev = (0, 0.0)

    # -- layout ------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static(" KUTAAR // UNIVERSAL ENGINEERING AGENT   "
                     "Local - Private - AMD ROCm", id="top")
        with Horizontal(id="body"):
            with Vertical(id="tools"):
                yield Static("[bold red]TOOLS[/]", classes="panel")
                yield ListView(id="toollist")
            with Vertical(id="center"):
                yield Static(BANNER, id="banner")
                yield Static(SUBTITLE, id="sub")
                yield Static(QUICK, id="quick")
                with Horizontal(id="presets"):
                    for i, name in enumerate(PRESETS):
                        yield Button(name, id=f"preset-{i}")
                yield RichLog(id="stream", wrap=True, highlight=True,
                              markup=True)
                with Horizontal(id="askrow"):
                    yield Input(placeholder="Ask Kutaar to do something... "
                                            "(Enter to send, /help cmds)",
                                id="ask")
                    yield Select([("TASK", "task"), ("CLASSIC", "classic")],
                                 value="task", id="backend")
                yield Static("[red]^p[/] Commands  [red]^,[/] Settings  "
                             "[red]^l[/] Clear  [red]^h[/] History  "
                             "[red]f1[/] Help  [red]<-[/] Send  "
                             "[red]f2[/] Mode", id="hints")
            with Vertical(id="right"):
                yield Static("MODEL ROUTING\nNo active model", id="model")
                yield Static("TASK PHASES\n--", id="phases")
                yield Static("EVIDENCE CHAIN\nNo receipts yet", id="chain")
                yield Static("SYSTEM\n...", id="sys")
                yield RichLog(id="agentstream", wrap=True, markup=False)
                yield DataTable(id="findings")
        yield Footer()


    # -- mount -------------------------------------------------------
    def on_mount(self) -> None:
        items = [ListItem(Label(f"[red]>[/] {name}\n[dim]{blurb}[/]"))
                 for name, blurb in TOOL_BLURBS]
        self.query_one("#toollist", ListView).extend(items)
        tbl = self.query_one("#findings", DataTable)
        tbl.add_columns("S", "Title", "File")
        self.set_interval(1.0, self._tick_sys)
        self._say("assistant", "Welcome. Press F2 (or /index) to index the "
                               "repo, then ask or hit a preset button.")
        self._backend_boot()
        self.query_one("#ask", Input).focus()

    # -- helpers -----------------------------------------------------
    def _say(self, who: str, text: str) -> None:
        tag = "[bold cyan]you[/]" if who == "user" else "[bold magenta]kutaar[/]"
        self.query_one("#stream", RichLog).write(f"{tag}: {text}\n")

    def _agent(self, line: str) -> None:
        self.query_one("#agentstream", RichLog).write(line[:220])

    def _status_model(self, text: str) -> None:
        self.query_one("#model", Static).update(f"MODEL ROUTING\n{text}")

    def _phases(self, current: str = "", detail: str = "") -> None:
        if not current:
            self.query_one("#phases", Static).update("TASK PHASES\n--")
            return
        try:
            idx = PHASES.index(current)
        except ValueError:
            idx = len(PHASES) - 1
        bits = []
        for i, p in enumerate(PHASES):
            if i < idx:
                bits.append(f"[green]{p}[/]")
            elif i == idx:
                bits.append(f"[bold reverse] {p} [/]")
            else:
                bits.append(f"[dim]{p}[/]")
        extra = f"\n{detail}" if detail else ""
        self.query_one("#phases", Static).update("TASK PHASES\n" +
                                                " ".join(bits) + extra)

    def _chain(self, n_ev: int = 0, n_find: int = 0,
               patch: str = "", verdict: str = "") -> None:
        rows = [f"evidence={n_ev} findings={n_find}"]
        if patch:
            rows.append(f"patch: {patch[:60]}")
        if verdict:
            rows.append(f"verdict: {verdict}")
        if not n_ev and not n_find:
            rows = ["No receipts yet"]
        self.query_one("#chain", Static).update("RECEIPT CHAIN\n" +
                                                "\n".join(rows))

    def _show_findings(self, findings: list[dict]) -> None:
        tbl = self.query_one("#findings", DataTable)
        tbl.clear()
        for f in findings[:30]:
            sev = str(f.get("severity", "info"))
            tbl.add_row(SEV.get(sev, "-"), str(f.get("title", ""))[:40],
                        str(f.get("file_path", ""))[:24])

    def _tick_sys(self) -> None:
        import time as _t
        snap = sys_snapshot()
        rate = 0.0
        try:
            import psutil  # type: ignore
            counters = psutil.net_io_counters()
            now = _t.time()
            total = counters.bytes_sent + counters.bytes_recv
            prev, pt = self._net_prev
            if prev and now > pt:
                rate = (total - prev) / (now - pt)
            self._net_prev = (total, now)
        except Exception:  # noqa: BLE001
            rate = 0.0
        cores = snap.get("cores", [])[:4]
        while len(cores) < 4:
            cores.append(0.0)
        unit, val = ("MB/s", rate / 1e6) if rate > 1e6 else ("KB/s", rate / 1e3)
        lines = [
            "SYSTEM",
            f"CPU {bar(snap['cpu'])} {snap['cpu']:.1f}%",
            f"MEM {bar(snap['mem'])} {snap['mem']:.1f}%",
            f"NET {bar(min(100.0, rate / 1e7 * 100))} {val:.1f}{unit}",
            f"DSK {bar(snap.get('disk_pct', 0.0))} "
            f"{snap.get('disk_free', 0.0):.1f}GB free",
            "",
            "CORES " + "  ".join(f"{i} {c:.0f}%" for i, c in enumerate(cores)),
            f"freq  {snap.get('freq', 0.0):.2f} GHz",
            "",
            "AGENT STREAM",
        ]
        self.query_one("#sys", Static).update("\n".join(lines))


    # -- backend -----------------------------------------------------
    def _backend_boot(self) -> None:
        self._status_model("booting local model on GPU...")
        try:
            from src.llm.rocm_service import ROCmLLM as _ROCmLLM

            _ROCmLLM.reset_instance()
            self.S.llm = _ROCmLLM.get_instance()
            self.S.llm.initialize()
            diag = self.S.llm.diagnostics()
            ok = "verified" if diag.get("backend_verified") else "UNVERIFIED"
            name = Path(str(diag.get("model"))).name
            gpu = diag.get("detected_gpu") or "GPU"
            self._status_model(f"{self.S.llm.backend.upper()} ({ok})\n{name}\n{gpu}")
            self._agent(f"llm boot: {self.S.llm.status_line()}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM boot failed")
            self._status_model(f"LLM boot failed\n{exc}")
            self._agent(f"llm boot failed: {exc}")

    def _ensure(self) -> None:
        from src.llm.rocm_service import ROCmLLM
        from src.rag.chroma_store import RAGStore
        from src.tools.tool_registry import ToolRegistry
        if self.S.llm is None:
            self.S.llm = ROCmLLM.get_instance()
            self.S.llm.initialize()
        if self.S.rag is None:
            self.S.rag = RAGStore(persist_dir="./chroma_db")
            self.S.rag.initialize()
        if self.S.tools is None:
            self.S.tools = ToolRegistry(self.S.repo_path)

    def _do_index(self, repo: str = "") -> None:
        repo = repo or self.S.repo_path
        if not repo or not Path(repo).exists():
            self._say("assistant", f"path not found: {repo}")
            return
        self._say("assistant", f"indexing {repo}...")
        self._agent(f"index start {repo}")
        try:
            self._ensure()
            assert self.S.llm is not None and self.S.rag is not None
            if self.S.indexed_repo_path != repo:
                self.S.tools = None
                self.S.workflow = None
                self.S.task_workflow = None
                self.S.thread_id = f"kutaar-{int(time.time())}"
                self._ensure()
            from src.ingestion.repo_indexer import RepoIndexer
            indexer = RepoIndexer(repo)
            chunks = list(indexer.chunk_all())
            if not chunks:
                self._say("assistant", "no code files found.")
                return
            model = getattr(self.S.llm.config, "embedding_model", "")
            self.S.rag.reset(embedding_model=model)
            n = self.S.rag.index_chunks(chunks, self.S.llm.embed,
                                        embedding_model=model)
            self.S.repo_indexed = True
            self.S.indexed_repo_path = repo
            self.S.repo_path = repo
            self._say("assistant",
                      f"indexed {n} chunks from {indexer.stats()['file_count']} files.")
            self._agent(f"index done chunks={n}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("index failed")
            self._say("assistant", f"indexing failed: {exc}")

    # -- actions / keys ----------------------------------------------
    def action_palette(self) -> None:
        self._say("assistant", "commands: /index /repo /mode /team "
                               "/status /clear /copy /help + F1/F2/F3")

    def action_clear(self) -> None:
        self.query_one("#stream", RichLog).clear()
        self.query_one("#agentstream", RichLog).clear()
        self.query_one("#findings", DataTable).clear()
        self.S.thread_id = f"kutaar-{int(time.time())}"
        self._say("assistant", "cleared.")

    def action_help(self) -> None:
        self._say("assistant",
                  "F2 index - F3 toggle task/classic - Ctrl+L clear - "
                  "Ctrl+Q quit. Preset buttons run audits. "
                  "Approval needed before any worktree patch.")

    def action_index(self) -> None:
        self._do_index(self.S.repo_path)

    def action_mode(self) -> None:
        self.S.mode = "classic" if self.S.mode == "task" else "task"
        self.query_one("#backend", Select).value = self.S.mode
        self._say("assistant", f"mode: {self.S.mode}")

    @on(Select.Changed, "#backend")
    def _backend_changed(self, event: Select.Changed) -> None:
        self.S.mode = str(event.value)
        self._say("assistant", f"backend: {self.S.mode}")

    @on(Button.Pressed)
    def _preset(self, event: Button.Pressed) -> None:
        raw = (event.button.id or "").replace("preset-", "")
        names = list(PRESETS)
        name = names[int(raw)] if raw.isdigit() and int(raw) < len(names) else ""
        prompt = PRESETS.get(name, "")
        if prompt == "__INDEX__":
            self._do_index(self.S.repo_path)
        elif prompt:
            self._ask(prompt)


    @on(Input.Submitted, "#ask")
    def _on_ask(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        event.input.value = ""
        if not prompt:
            return
        if prompt.startswith("/"):
            self._slash(prompt)
            return
        self._ask(prompt)

    def _slash(self, raw: str) -> None:
        parts = raw.split(None, 1)
        cmd, arg = parts[0].lower(), (parts[1] if len(parts) > 1 else "")
        if cmd in ("/quit", "/exit", "/q"):
            self.exit()
        elif cmd == "/index":
            self._do_index(arg or self.S.repo_path)
        elif cmd == "/repo":
            if arg and Path(arg).exists():
                self.S.repo_path = arg
                self._say("assistant", "repo set - run /index.")
            else:
                self._say("assistant", f"current repo: {self.S.repo_path}")
        elif cmd == "/mode":
            if arg.lower().startswith("classic"):
                self.S.mode = "classic"
            elif arg.lower().startswith("task"):
                self.S.mode = "task"
            self.query_one("#backend", Select).value = self.S.mode
            self._say("assistant", f"mode: {self.S.mode}")
        elif cmd == "/team":
            if arg:
                self.S.profiles = [p.strip() for p in arg.split(",")
                                   if p.strip()]
            self._say("assistant", f"team: {', '.join(self.S.profiles)}")
        elif cmd == "/status":
            line = self.S.llm.status_line() if self.S.llm else "LLM booting"
            self._say("assistant", f"{line} | repo={self.S.repo_path} | "
                                   f"indexed={self.S.indexed_repo_path or 'no'}"
                                   f" | mode={self.S.mode}"
                                   f" | constraints={', '.join(self.S.constraints) or 'none'}")
        elif cmd == "/constraints":
            if arg:
                self.S.constraints = [c.strip() for c in arg.split(",") if c.strip() in ("readonly", "no-install", "no-net", "no-service-start")]
            self._say("assistant", f"constraints: {', '.join(self.S.constraints) or 'none'}")
        elif cmd == "/clear":
            self.action_clear()
        elif cmd == "/copy":
            try:
                import pyperclip  # type: ignore
                pyperclip.copy(arg or "kutaar")
                self._say("assistant", "copied to clipboard.")
            except Exception as exc:  # noqa: BLE001
                self._say("assistant", f"copy unavailable: {exc}")
        elif cmd == "/help":
            self.action_help()
        else:
            self._say("assistant", f"unknown {cmd} - try /help.")

    @work(thread=True)
    def _ask(self, prompt: str) -> None:
        if not self.S.repo_indexed or \
                self.S.indexed_repo_path != self.S.repo_path:
            self._say("assistant", "press F2 (or /index) first.")
            return
        self._say("user", prompt)
        self._agent(f"task start: {prompt[:120]}")
        try:
            if self.S.mode == "task":
                text, findings, logs, res = self._run_task(prompt)
            else:
                text, findings, logs, res = self._run_classic(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.exception("workflow error")
            self._say("assistant", f"error: {exc}")
            return
        self._say("assistant", text)
        self._show_findings(findings)
        for t in logs:
            ok = "OK" if t.get("success") else "FAIL"
            self._agent(f"{ok} {t.get('tool_name', '?')} "
                        f"{t.get('elapsed_ms', 0):.0f}ms "
                        f"{str(t.get('summary', ''))[:140]}")
        self._chain(n_ev=len(res.get("evidence", [])),
                    n_find=len(findings),
                    patch=str((res.get("patch_proposal") or {}).get("summary", "")),
                    verdict=str(res.get("review_verdict", "")))
        self._agent("task done.")


    def _run_classic(self, prompt: str) -> tuple:
        from langchain_core.messages import HumanMessage
        from src.graph.workflow import KutaarWorkflow
        self._ensure()
        if self.S.workflow is None:
            self.S.workflow = KutaarWorkflow(
                self.S.llm, self.S.rag, self.S.tools).compile()
        assert self.S.workflow is not None
        res = self.S.workflow.invoke(
            {"messages": [HumanMessage(content=prompt)],
             "repo_path": self.S.repo_path, "task_text": prompt},
            config={"configurable": {"thread_id": self.S.thread_id}})
        msgs = res.get("messages", [])
        text = ""
        if msgs and hasattr(msgs[-1], "content"):
            text = msgs[-1].content
        elif msgs:
            text = str(msgs[-1])
        out: list[dict] = []
        for k in ("security", "performance", "architecture", "devops"):
            out += [dict(x) for x in res.get(f"{k}_findings", [])]
        self._phases("report", "classic review done")
        return (text.strip() or "Workflow done, no response.", out,
                [dict(t) for t in res.get("tool_logs", [])], dict(res))

    def _run_task(self, prompt: str) -> tuple:
        from src.graph.task_workflow import TaskWorkflow
        from src.state.task_state import initial_task_state
        self._ensure()
        if self.S.task_workflow is None:
            self.S.task_workflow = TaskWorkflow(
                self.S.llm, rag_store=self.S.rag,
                tool_registry=self.S.tools,
                auto_approve=self.S.auto_approve).compile()
        assert self.S.task_workflow is not None
        res = self.S.task_workflow.invoke(
            initial_task_state(repo_path=self.S.repo_path, task_text=prompt,
                               task_constraints=list(self.S.constraints))
            | {"selected_profiles": self.S.profiles})
        self._phases(str(res.get("phase", "report")),
                     str(res.get("phase_detail", "")))
        return (res.get("report", "No report."),
                [dict(x) for x in res.get("findings", [])],
                [dict(t) for t in res.get("tool_logs", [])], dict(res))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Kutaar PROTOS-style console TUI")
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument("--mode", default="task", choices=["task", "classic"])
    p.add_argument("--constraints", nargs="*", default=[],
                   choices=["readonly", "no-install", "no-net", "no-service-start"])
    p.add_argument("--log-level", default="WARNING",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main(argv: Optional[list[str]] = None) -> None:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING))
    app = KutaarConsole(repo_path=args.repo, mode=args.mode)
    app.S.constraints = list(args.constraints or [])
    app.run()


if __name__ == "__main__":
    main()

