"""Kutaar Terminal Menu - Rich-only CLI wizard mirroring Streamlit sidebar.

Streamlit sidebar -> Terminal menu: Repo+Index->1, Mode/Intent->2,
Team profiles->3, Toggles->4, Model info->5, About->6, Chat->7 Ask.

Usage: python -m src.ui.menu_cli [--repo PATH] [--mode task|classic]
       python -m src.ui.menu_cli --once "Review this repo" [--auto-approve]
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

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

logger = logging.getLogger("kutaar.menu")
console = Console()

PHASES = ["intake", "recon", "team", "investigate", "plan", "approval",
          "implement", "verify", "review", "report"]
SEV_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡",
             "low": "🟢", "info": "🔵"}
AGENT_BLURBS = [
    ("Planner/Task Manager", "orchestrates analysis, scopes intent"),
    ("Investigator", "explores repo, collects evidence"),
    ("Security", "Bandit / Semgrep / secret scan"),
    ("Performance", "hotspots, complexity, blocking I/O"),
    ("Architecture", "structure, coupling, patterns"),
    ("DevOps/Verification", "Docker, config + tests/lint/build"),
    ("Review/Consensus", "debate, verdict, quality score"),
]


@dataclass
class MenuState:
    """Mirrors Streamlit session_state defaults in chat_app.init_session."""

    repo_path: str = DEFAULT_REPO
    indexed_repo_path: str = ""
    repo_indexed: bool = False
    indexed_chunks: int = 0
    indexed_files: int = 0
    app_mode: str = "task"
    task_intent: str = "Review"
    selected_profiles: list[str] = field(
        default_factory=lambda: ["investigator", "security_reviewer",
                                 "review"])
    show_tools: bool = True
    show_diff: bool = True
    auto_approve: bool = False
    include_pdfs: bool = False
    constraints: list[str] = field(default_factory=list)
    thread_id: str = field(default_factory=lambda: f"kutaar-{int(time.time())}")
    llm: Any = None
    rag_store: Any = None
    tool_registry: Any = None
    workflow: Any = None
    task_workflow: Any = None
    last_result: Optional[dict] = None
    history: list[dict] = field(default_factory=list)


def system_line() -> str:
    """CPU/RAM/disk via psutil, or install hint when absent."""
    try:
        import psutil  # type: ignore
    except Exception:
        return "psutil not installed - pip install psutil for system stats"
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path.cwd().anchor))
        return (f"CPU {cpu:.0f}% | RAM {mem.percent:.0f}% "
                f"({mem.used / 1e9:.1f}/{mem.total / 1e9:.1f} GB) | "
                f"Disk {disk.percent:.0f}% free {disk.free / 1e9:.1f} GB")
    except Exception as exc:  # noqa: BLE001
        return f"system stats unavailable: {exc}"


def copy_to_clipboard(text: str) -> str:
    """Copy via pyperclip; never crash when missing."""
    try:
        import pyperclip  # type: ignore
    except Exception:
        return "pyperclip missing - pip install pyperclip for copy support"
    try:
        pyperclip.copy(text)
        return f"Copied {len(text)} chars to clipboard."
    except Exception as exc:  # noqa: BLE001
        return f"Copy failed ({exc}). Select the text manually."


def has_pypdf() -> bool:
    try:
        import pypdf  # noqa: F401  # type: ignore
        return True
    except Exception:
        return False


def banner() -> None:
    console.print(Panel.fit(
        "[bold magenta]Kutaar[/] - Multi-Agent Engineering Assistant\n"
        "[dim]AMD ROCm + LangGraph - 100% local - terminal menu[/]",
        title="kutaar", border_style="magenta"))


def pause() -> None:
    Prompt.ask("[dim]Press Enter to continue[/]", default="")


def choose(title: str, options: list[str], default: int = 1) -> int:
    console.print(f"\n[bold]{title}[/]")
    for i, opt in enumerate(options, 1):
        console.print(f"  [cyan]{i}[/]. {opt}")
    while True:
        raw = Prompt.ask("Select", default=str(default)).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)
        console.print("[red]Enter a number from the list.[/]")

def ensure_backend(state: MenuState) -> None:
    from src.llm.rocm_service import ROCmLLM
    from src.rag.chroma_store import RAGStore
    from src.tools.tool_registry import ToolRegistry
    if state.llm is None:
        state.llm = ROCmLLM.get_instance()
        state.llm.initialize()
    if state.rag_store is None:
        state.rag_store = RAGStore(persist_dir="./chroma_db")
        state.rag_store.initialize()
    if state.tool_registry is None:
        state.tool_registry = ToolRegistry(state.repo_path)


def pdf_chunks(repo: Path) -> list:
    from pypdf import PdfReader  # type: ignore
    from src.ingestion.repo_indexer import CodeChunk
    out: list = []
    for pdf in sorted(repo.rglob("*.pdf")):
        if ".git" in pdf.parts or ".venv" in pdf.parts:
            continue
        try:
            reader = PdfReader(str(pdf))
            for i, page in enumerate(reader.pages):
                text = (page.extract_text() or "").strip()
                if text:
                    out.append(CodeChunk(
                        file_path=f"{pdf.relative_to(repo)}#p{i + 1}",
                        language="text", start_line=i + 1,
                        end_line=i + 1, content=text[:8000],
                        metadata={"repo": repo.name, "ext": ".pdf"}))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skip PDF %s: %s", pdf, exc)
    return out


def do_index(state: MenuState, repo: str = "") -> bool:
    repo = repo or state.repo_path
    if not repo or not Path(repo).exists():
        console.print(f"[red]Path not found: {repo}[/]")
        return False
    ensure_backend(state)
    assert state.llm is not None and state.rag_store is not None
    if state.indexed_repo_path != repo:
        state.tool_registry = None
        state.workflow = None
        state.task_workflow = None
        state.thread_id = f"kutaar-{int(time.time())}"
    from src.ingestion.repo_indexer import RepoIndexer
    with Progress(SpinnerColumn(),
                  TextColumn("[progress.description]{task.description}"),
                  console=console, transient=True) as prog:
        prog.add_task("Indexing repository...", total=None)
        indexer = RepoIndexer(repo)
        chunks = list(indexer.chunk_all())
        if state.include_pdfs:
            if not has_pypdf():
                console.print("[yellow]pypdf missing - skip PDFs.[/]")
            else:
                chunks += pdf_chunks(Path(repo))
        if not chunks:
            console.print("[yellow]No code files found.[/]")
            return False
        model = getattr(state.llm.config, "embedding_model", "")
        state.rag_store.reset(embedding_model=model)
        count = state.rag_store.index_chunks(
            chunks, state.llm.embed, embedding_model=model)
    stats = indexer.stats()
    state.repo_indexed = True
    state.indexed_repo_path = repo
    state.repo_path = repo
    state.indexed_chunks = count
    state.indexed_files = stats["file_count"]
    ensure_backend(state)
    console.print(f"[green]Indexed {count} chunks from "
                  f"{stats['file_count']} files.[/]")
    return True



def menu_repo(state: MenuState) -> None:
    console.print(Panel(
        f"Current: [cyan]{state.repo_path}[/]\n"
        f"Indexed: [green]{state.indexed_repo_path or 'no'}[/] "
        f"({state.indexed_chunks} chunks / {state.indexed_files} files)",
        title="1 - Repository"))
    path = Prompt.ask("Repo path (empty = keep)", default="").strip()
    if path:
        state.repo_path = path
    state.include_pdfs = Confirm.ask(
        f"Also ingest PDFs? (pypdf {'ready' if has_pypdf() else 'MISSING'})",
        default=state.include_pdfs)
    if Confirm.ask("Index now?", default=True):
        do_index(state)
    pause()


def menu_mode(state: MenuState) -> None:
    console.print(Panel(f"Mode: [cyan]{state.app_mode}[/] | "
                        f"Intent: [cyan]{state.task_intent}[/] | "
                        f"Auto-approve: {state.auto_approve}",
                        title="2 - Workspace mode"))
    m = choose("Workflow mode (sidebar radio)",
               ["Task Mode (Autonomous)", "Classic Review"],
               default=1 if state.app_mode == "task" else 2)
    state.app_mode = "task" if m == 1 else "classic"
    if state.app_mode == "task":
        i = choose("Task type (sidebar selectbox)",
                   ["Review", "Diagnose", "Change"],
                   default={"Review": 1, "Diagnose": 2,
                            "Change": 3}.get(state.task_intent, 1))
        state.task_intent = ["Review", "Diagnose", "Change"][i - 1]
        if state.task_intent == "Change":
            console.print("[yellow]Change pauses before worktree "
                          "mutation for approval.[/]")
            state.auto_approve = Confirm.ask(
                "Auto-approve worktree patch?",
                default=state.auto_approve)
    console.print(f"[green]Mode: {state.app_mode}/{state.task_intent}[/]")
    pause()


def menu_team(state: MenuState) -> None:
    from src.agents.agent_registry import available_profiles
    profiles = available_profiles()
    names = sorted(profiles)
    console.print(Panel("Numbers toggle profiles (sidebar multiselect). "
                        "Empty line = done.", title="3 - Team"))
    sel = set(state.selected_profiles)
    while True:
        for i, name in enumerate(names, 1):
            mark = "[green]x[/]" if name in sel else "[dim] [/]"
            console.print(f"  {mark} [cyan]{i}[/]. "
                          f"{profiles[name].title} ([dim]{name}[/])")
        raw = Prompt.ask("Toggle number (empty=done)",
                         default="").strip().lower()
        if raw in ("", "done", "q"):
            break
        if raw.isdigit() and 1 <= int(raw) <= len(names):
            sel.symmetric_difference_update({names[int(raw) - 1]})
        else:
            console.print("[red]Enter a number or empty to finish.[/]")
    state.selected_profiles = sorted(sel)
    console.print(f"[green]Team: {', '.join(state.selected_profiles)}[/]")
    pause()

def menu_settings(state: MenuState) -> None:
    console.print(Panel(f"show_tools={state.show_tools} | "
                        f"show_diff={state.show_diff} | "
                        f"constraints={', '.join(state.constraints) or 'none'}",
                        title="4 - Options (sidebar toggles)"))
    state.show_tools = Confirm.ask("Show tool logs?",
                                   default=state.show_tools)
    state.show_diff = Confirm.ask("Show patch diff?",
                                  default=state.show_diff)
    for label, key in [("Read-only repo?", "readonly"), ("No installs?", "no-install"), ("No network?", "no-net"), ("No service start?", "no-service-start")]:
        want = Confirm.ask(label, default=(key in state.constraints))
        if want and key not in state.constraints:
            state.constraints.append(key)
        if not want and key in state.constraints:
            state.constraints.remove(key)
    console.print("[green]Saved.[/]")
    pause()


def menu_model(state: MenuState) -> None:
    ensure_backend(state)
    assert state.llm is not None
    diag = state.llm.diagnostics()
    ok = "verified" if diag.get("backend_verified") else "UNVERIFIED"
    console.print(Panel(
        f"LLM backend: [cyan]{state.llm.backend.upper()}[/] ({ok})\n"
        f"{state.llm.status_line()}\n"
        f"Model file: {Path(str(diag.get('model'))).name}\n"
        f"System: {system_line()}",
        title="5 - Model"))
    if Confirm.ask("Re-initialize LLM?", default=False):
        state.llm.initialize()
        console.print("[green]Re-initialized.[/]")
    pause()


def menu_about() -> None:
    table = Table(title="6 - Agents (sidebar About)",
                  show_header=True, header_style="bold magenta")
    table.add_column("Agent")
    table.add_column("Role")
    for title, role in AGENT_BLURBS:
        table.add_row(title, role)
    console.print(table)
    console.print(Panel("Private multi-agent review for code, perf, "
                        "arch, DevOps. Built for AMD AI DevMaster "
                        "Hackathon Track 2.",
                        title="About"))
    pause()


def render_timeline(result: dict) -> None:
    cur = str(result.get("phase", "report"))
    try:
        idx = PHASES.index(cur)
    except ValueError:
        idx = len(PHASES) - 1
    bits = []
    for i, p in enumerate(PHASES):
        if i < idx:
            bits.append(f"[green]OK {p}[/]")
        elif i == idx:
            bits.append(f"[bold reverse] {p} [/]")
        else:
            bits.append(f"[dim]{p}[/]")
    console.print(Panel(" > ".join(bits) +
                        (f"\n{result.get('phase_detail', '')}" if result.get("phase_detail") else "") +
                        (f"\nWorktree: {result.get('worktree_path') or 'not created'} | "
                         f"Branch: {result.get('worktree_branch') or 'none'}"),
                        title="Task timeline"))


def render_findings(findings: list[dict]) -> None:
    if not findings:
        return
    table = Table(title=f"Findings ({len(findings)})",
                  show_header=True, header_style="bold magenta")
    table.add_column("Sev")
    table.add_column("Title")
    table.add_column("File")
    table.add_column("Status")
    table.add_column("Agent")
    for f in findings[:20]:
        sev = str(f.get("severity", "info"))
        table.add_row(f"{SEV_EMOJI.get(sev, '-')} {sev}",
                      str(f.get("title", ""))[:60],
                      str(f.get("file_path", ""))[:40],
                      str(f.get("verification_status", "hypothesis"))[:12],
                      str(f.get("agent", ""))[:14])
    console.print(table)
    det = choose("Open finding detail?", ["No"] +
                 [f"{i + 1}. {str(f.get('title', ''))[:50]}"
                  for i, f in enumerate(findings[:20])], default=1)
    if det > 1:
        f = findings[det - 2]
        console.print(Panel(
            f"[bold]{f.get('title', '')}[/]\n"
            f"Severity: {f.get('severity', '')} | Agent: {f.get('agent', '')}\n"
            + (f"File: {f.get('file_path', '')}:{f.get('line_start', '')}\n" if f.get("file_path") else "")
            + (f"\n{f.get('description', '')}\n" if f.get("description") else "")
            + (f"\nFix: {f.get('recommendation', '')}" if f.get("recommendation") else ""),
            title="Finding detail"))
        if f.get("code_snippet"):
            console.print(Syntax(str(f["code_snippet"])[:4000],
                                 str(f.get("language", "python") or "python"),
                                 line_numbers=False))
        if Confirm.ask("Copy finding to clipboard?", default=False):
            console.print(copy_to_clipboard(
                f"{f.get('title', '')}\n{f.get('description', '')}\n"
                f"{f.get('file_path', '')}:{f.get('line_start', '')}"))


def render_tools(logs: list[dict], show: bool) -> None:
    if not show or not logs:
        return
    table = Table(title="Tool execution logs", show_header=True)
    table.add_column("OK")
    table.add_column("Tool")
    table.add_column("ms")
    table.add_column("Summary")
    for t in logs:
        table.add_row("OK" if t.get("success") else "FAIL",
                      str(t.get("tool_name", "?"))[:20],
                      f"{t.get('elapsed_ms', 0):.0f}",
                      str(t.get("summary", ""))[:90])
    console.print(table)


def render_results(state: MenuState, result: dict,
                   text: str, findings: list[dict],
                   logs: list[dict]) -> None:
    render_timeline(result)
    console.print(Panel(Markdown(text or "No report."),
                        title="Report"))
    render_findings(findings)
    render_tools(logs, state.show_tools)
    if result.get("patch_proposal"):
        p = result["patch_proposal"]
        console.print(Panel(
            f"{p.get('summary', '')}\n"
            f"Risk: {p.get('risk_level', '?')} | "
            f"Files: {', '.join(p.get('files_changed', []))}\n"
            f"Evidence: {', '.join(p.get('linked_evidence_ids', [])) or 'none'}\n"
            f"Verify: {' '.join(' '.join(str(c) for c in cmd) + '  ' for cmd in (p.get('verification_commands') or [])) or 'see Verification table'}",
            title="Patch proposal"))
        if state.show_diff and p.get("unified_diff"):
            console.print(Syntax(str(p["unified_diff"])[:8000], "diff"))
    if result.get("verification_results"):
        table = Table(title="Verification", show_header=True)
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Exit")
        table.add_column("Command")
        table.add_column("Summary")
        for v in result["verification_results"]:
            table.add_row(str(v.get("name", ""))[:24],
                          str(v.get("status", "")),
                          str(v.get("exit_code", "")),
                          " ".join(str(c) for c in (v.get("command") or []))[:40],
                          str(v.get("summary", ""))[:80])
        console.print(table)
    if result.get("approval_required") and not result.get("approved"):
        console.print("[yellow]Approval boundary: patch staged, "
                      "not applied yet.[/]")
    while True:
        c = choose("Actions",
                   ["Back to menu", "Copy report", "Copy diff",
                    "Copy findings"], default=1)
        if c == 1:
            break
        if c == 2:
            console.print(copy_to_clipboard(text))
        elif c == 3:
            diff = ""
            if result.get("patch_proposal"):
                diff = str(result["patch_proposal"].get("unified_diff", ""))
            console.print(copy_to_clipboard(diff or "no diff"))
        else:
            lines = [f"- [{f.get('severity', '')}] {f.get('title', '')} "
                     f"({f.get('file_path', '')})" for f in findings]
            console.print(copy_to_clipboard("\n".join(lines) or "none"))


def run_task(state: MenuState, prompt: str) -> tuple:
    from src.graph.task_workflow import TaskWorkflow
    from src.state.task_state import initial_task_state
    ensure_backend(state)
    if state.task_workflow is None:
        state.task_workflow = TaskWorkflow(
            state.llm, rag_store=state.rag_store,
            tool_registry=state.tool_registry,
            auto_approve=state.auto_approve).compile()
    with Progress(SpinnerColumn(),
                  TextColumn("[progress.description]{task.description}"),
                  console=console, transient=True) as prog:
        prog.add_task("Running task workflow...", total=None)
        res = state.task_workflow.invoke(
            initial_task_state(repo_path=state.repo_path,
                               task_text=prompt,
                               task_constraints=list(state.constraints))
            | {"selected_profiles": state.selected_profiles})
    return (res.get("report", "No report."),
            [dict(x) for x in res.get("findings", [])],
            [dict(t) for t in res.get("tool_logs", [])], dict(res))


def run_classic(state: MenuState, prompt: str) -> tuple:
    from langchain_core.messages import HumanMessage
    from src.graph.workflow import KutaarWorkflow
    ensure_backend(state)
    if state.workflow is None:
        state.workflow = KutaarWorkflow(
            state.llm, state.rag_store,
            state.tool_registry).compile()
    with Progress(SpinnerColumn(),
                  TextColumn("[progress.description]{task.description}"),
                  console=console, transient=True) as prog:
        prog.add_task("Running review workflow...", total=None)
        res = state.workflow.invoke(
            {"messages": [HumanMessage(content=prompt)],
             "repo_path": state.repo_path, "task_text": prompt},
            config={"configurable": {"thread_id": state.thread_id}})
    msgs = res.get("messages", [])
    text = ""
    if msgs and hasattr(msgs[-1], "content"):
        text = msgs[-1].content
    elif msgs:
        text = str(msgs[-1])
    out: list[dict] = []
    for k in ("security", "performance", "architecture", "devops"):
        out += [dict(x) for x in res.get(f"{k}_findings", [])]
    return (text.strip() or "Workflow done, no response.", out,
            [dict(t) for t in res.get("tool_logs", [])], dict(res))


def menu_ask(state: MenuState, preset: str = "") -> None:
    prompt = preset or Prompt.ask(
        "Ask about your codebase (/copy needs pyperclip, "
        "empty = back)").strip()
    if not prompt:
        return
    if not state.repo_indexed or \
            state.indexed_repo_path != state.repo_path:
        console.print("[yellow]Index the repo first (menu 1).[/]")
        if Confirm.ask("Index now?", default=True):
            if not do_index(state):
                return
        else:
            return
    try:
        if state.app_mode == "task":
            text, findings, logs, res = run_task(state, prompt)
        else:
            text, findings, logs, res = run_classic(state, prompt)
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow error")
        console.print(f"[red]Error: {exc}[/]")
        return
    state.last_result = res
    state.history.append({"role": "user", "content": prompt})
    state.history.append({"role": "assistant", "content": text,
                          "findings": findings, "tool_logs": logs})
    render_results(state, res, text, findings, logs)
    if res.get("approval_required") and not res.get("approved") \
            and res.get("patch_proposal"):
        if Confirm.ask("Approve and run in isolated worktree?",
                       default=False):
            approved = dict(res)
            approved["approved"] = True
            approved["phase"] = "approval"
            with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                           console=console, transient=True) as prog:
                prog.add_task("Applying approved patch...", total=None)
                res2 = state.task_workflow.invoke(approved)
            text2 = res2.get("report", "")
            f2 = [dict(x) for x in res2.get("findings", [])]
            l2 = [dict(t) for t in res2.get("tool_logs", [])]
            state.last_result = dict(res2)
            render_results(state, dict(res2), text2, f2, l2)
    if Confirm.ask("Copy report to clipboard?", default=False):
        console.print(copy_to_clipboard(text))
    pause()


def menu_history(state: MenuState) -> None:
    if not state.history:
        console.print("[dim]No conversation yet - use menu 7.[/]")
        pause()
        return
    for m in state.history[-20:]:
        who = "[cyan]you[/]" if m["role"] == "user" else "[magenta]kutaar[/]"
        console.print(Panel(Markdown(str(m["content"])[:3000]), title=who))
        if m.get("findings"):
            render_findings(m["findings"])
    pause()


def menu_status(state: MenuState) -> None:
    llm_line = "LLM not init"
    if state.llm is not None:
        try:
            llm_line = state.llm.status_line()
        except Exception:  # noqa: BLE001
            llm_line = "LLM status unavailable"
    console.print(Panel(
        f"Repo: {state.repo_path}\n"
        f"Indexed: {state.indexed_repo_path or 'no'} "
        f"({state.indexed_chunks} chunks)\n"
        f"Mode: {state.app_mode} / {state.task_intent}\n"
        f"Team: {', '.join(state.selected_profiles)}\n"
        f"{llm_line}\nSystem: {system_line()}",
        title="Status (/status in TUI)"))
    pause()


def main_menu(state: MenuState) -> int:
    console.print("\n[bold]Main menu[/] [dim](mirrors Streamlit sidebar)[/]")
    console.print(f"  Repo: [cyan]{Path(state.repo_path).name}[/] "
                  f"{'[green]indexed[/]' if state.repo_indexed else '[yellow]not indexed[/]'} | "
                  f"Mode: [cyan]{state.app_mode}/{state.task_intent}[/] | "
                  f"Team: [dim]{len(state.selected_profiles)} profiles[/]")
    return choose("Go to",
                  ["1 - Repository (path + index + PDFs)",
                   "2 - Workspace mode (task/classic + intent)",
                   "3 - Team profiles",
                   "4 - Options (tool logs / diff)",
                   "5 - Model + system (psutil)",
                   "6 - About agents",
                   "7 - Ask / run task",
                   "8 - History",
                   "9 - Status",
                   "0 - Quit"], default=7)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Kutaar terminal menu (Rich-only)")
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument("--mode", default="task", choices=["task", "classic"])
    p.add_argument("--once", default="",
                   help="Run one prompt non-interactively, then exit")
    p.add_argument("--auto-approve", action="store_true")
    p.add_argument("--include-pdfs", action="store_true",
                   help="Also ingest *.pdf docs (needs pypdf)")
    p.add_argument("--constraints", nargs="*", default=[],
                   choices=["readonly", "no-install", "no-net", "no-service-start"],
                   help="Intake constraints honoured by the task workflow")
    p.add_argument("--log-level", default="WARNING",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING))
    state = MenuState(repo_path=args.repo, app_mode=args.mode,
                      auto_approve=args.auto_approve,
                      include_pdfs=args.include_pdfs,
                      constraints=list(args.constraints or []))
    banner()
    console.print(f"[dim]System: {system_line()}[/]")
    if args.once:
        if not do_index(state):
            return 1
        menu_ask(state, preset=args.once)
        return 0
    while True:
        sel = main_menu(state)
        if sel == 1:
            menu_repo(state)
        elif sel == 2:
            menu_mode(state)
        elif sel == 3:
            menu_team(state)
        elif sel == 4:
            menu_settings(state)
        elif sel == 5:
            menu_model(state)
        elif sel == 6:
            menu_about()
        elif sel == 7:
            menu_ask(state)
        elif sel == 8:
            menu_history(state)
        elif sel == 9:
            menu_status(state)
        else:
            console.print("[dim]Bye.[/]")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())

