"""Step 3 only - Pipeline warmup (Steps 1 & 2 already done)."""
import time, sys

sys.path.insert(0, "/workspace/template-repos/template-1005/repo")

repo_path = "/workspace/template-repos/template-1005/repo/demo_repos/sample_app"
chroma_path = "/workspace/template-repos/template-1005/repo/chroma_db"

print("=" * 60)
print("  STEP 3: Pre-warm Agent Pipeline (6 agents)")
print("=" * 60)

from src.graph.workflow import KutaarWorkflow
from src.llm.rocm_service import ROCmLLM
from src.rag.chroma_store import RAGStore
from src.tools.tool_registry import ToolRegistry
from langchain_core.messages import HumanMessage

print("Initializing ROCmLLM service...")
rocm_llm = ROCmLLM.get_instance()
rocm_llm.initialize()

print("Initializing RAG store...")
rag_store = RAGStore(persist_dir=chroma_path)
rag_store.initialize()

print("Initializing Tool registry...")
tool_registry = ToolRegistry(repo_path)

print("Compiling LangGraph workflow (6 agents: Planner -> Security/Perf/Arch/DevOps -> Consensus)...")
wf = KutaarWorkflow(rocm_llm, rag_store, tool_registry)
app = wf.compile()
print("Workflow compiled!")

print("\nRunning warmup query: 'Find security vulnerabilities in this codebase'")
print("(This runs Planner -> 4 specialists in parallel -> 2-round Consensus debate)\n")

t0 = time.time()
config = {"configurable": {"thread_id": "warmup_session"}}
result = app.invoke(
    {
        "messages": [HumanMessage(content="Find security vulnerabilities in this codebase")],
        "repo_path": repo_path,
        "repo_name": "sample_app",
        "repo_indexed": True,
        "current_phase": "planning",
        "turn_count": 0,
    },
    config=config,
)
elapsed = time.time() - t0

print(f"\n  Pipeline warmup complete in {elapsed:.1f}s!")
print(f"  Result keys: {list(result.keys())}")

# Extract response
messages = result.get("messages", [])
if messages:
    last_msg = messages[-1]
    response_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    print(f"\n  Response preview: {response_text[:300]}...")

print(f"""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   ALL WARMUP COMPLETE!                                   ║
║                                                          ║
║   GPU:      AMD Radeon gfx1100 @ 10.4 tok/s              ║
║   RAG:      30 chunks indexed                            ║
║   Pipeline: 6-agent workflow warmed up in {elapsed:.1f}s     ║
║                                                          ║
║   TO START GRADIO:                                       ║
║     /opt/venv/bin/python src/ui/gradio_app.py            ║
║                                                          ║
║   Then open http://localhost:7860 in browser             ║
║                                                          ║
║   START RECORDING NOW! (Win+Alt+R)                       ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
""")
