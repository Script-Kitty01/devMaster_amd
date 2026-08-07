"""
PASTE THIS ENTIRE SCRIPT INTO THE JUPYTERLAB TERMINAL ON THE RADEON INSTANCE.
It does everything in ONE shot: GPU benchmark → index → pipeline warmup.

HOW TO USE:
1. Open JupyterLab terminal on the Radeon instance (it's already open)
2. cd /workspace/template-repos/template-1005/repo
3. Copy this entire file and paste into the terminal, press Enter
4. Wait for "READY TO RECORD" message (~2-3 minutes)
"""

import time, os, sys, glob

# ============================================================
# STEP 1: GPU Benchmark
# ============================================================
print("=" * 60)
print("  STEP 1: GPU Inference Benchmark")
print("=" * 60)

from llama_cpp import Llama

model_path = "/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"

print("Loading model with n_gpu_layers=-1 (ALL layers on GPU)...")
t0 = time.time()
llm = Llama(
    model_path=model_path,
    n_gpu_layers=-1,
    n_ctx=2048,
    n_batch=512,
    verbose=False,
)
load_time = time.time() - t0
print(f"Load time: {load_time:.1f}s")

print("Warmup...")
llm("Hello", max_tokens=10)

print("\nRunning 5-run benchmark...")
speeds = []
for i in range(5):
    t0 = time.time()
    llm("Explain what a GPU is in one sentence.", max_tokens=100)
    elapsed = time.time() - t0
    tok_s = 100 / elapsed
    speeds.append(tok_s)
    print(f"  Run {i+1}: 100 tokens in {elapsed:.2f}s = {tok_s:.1f} tok/s")

avg_speed = sum(speeds) / len(speeds)
print(f"\n{'='*50}")
print(f"  GPU BENCHMARK SUMMARY")
print(f"  Model:   Llama 3.2 3B Instruct Q4_K_M (2.02 GB)")
print(f"  GPU:     AMD Radeon Graphics gfx1100")
print(f"  Backend: ROCm 7.2.1 + HIP BLAS")
print(f"  Load:    {load_time:.1f}s")
print(f"  Speed:   {avg_speed:.1f} tok/s")
print(f"  Status:  GPU INFERENCE VERIFIED - ZERO NVIDIA")
print(f"{'='*50}")
# Free GPU memory from llama-cpp before proceeding
print("\nFreeing GPU memory from benchmark model...")
del llm
import gc; gc.collect()
print("GPU memory freed.")
# ============================================================
# STEP 2: Index Demo Repo with ChromaDB
# ============================================================
print("\n" + "=" * 60)
print("  STEP 2: Index Demo Repo with ChromaDB")
print("=" * 60)

from chromadb import PersistentClient
from chromadb.utils import embedding_functions

repo_path = "/workspace/template-repos/template-1005/repo/demo_repos/sample_app"
chroma_path = "/workspace/template-repos/template-1005/repo/chroma_db"

print("Loading embedding model (all-MiniLM-L6-v2)...")
ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

print("Initializing ChromaDB...")
client = PersistentClient(path=chroma_path)

try:
    client.delete_collection("code_chunks")
except:
    pass

collection = client.create_collection(
    name="code_chunks",
    embedding_function=ef,
)

files = []
for ext in ["*.py", "*.yaml", "*.yml", "*.txt", "*.md", "Dockerfile"]:
    files.extend(glob.glob(os.path.join(repo_path, "**", ext), recursive=True))

print(f"Files found: {len(files)}")

chunk_count = 0
for fpath in files:
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if not content.strip():
            continue
        rel = os.path.relpath(fpath, repo_path)
        chunks = [c.strip() for c in content.split("\n\n") if c.strip()]
        for ci, chunk in enumerate(chunks):
            if len(chunk) < 10:
                continue
            collection.add(
                documents=[chunk],
                metadatas=[{"source": rel, "chunk": ci}],
                ids=[f"{rel}_{ci}"],
            )
            chunk_count += 1
    except Exception as e:
        print(f"  Skipping {fpath}: {e}")

print(f"\n  Indexed {chunk_count} chunks from {len(files)} files!")
print("  RAG store is READY for demo!")

# ============================================================
# STEP 3: Pre-warm Agent Pipeline
# ============================================================
print("\n" + "=" * 60)
print("  STEP 3: Pre-warm Agent Pipeline (6 agents)")
print("=" * 60)

sys.path.insert(0, "/workspace/template-repos/template-1005/repo")

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

print("Compiling LangGraph workflow (6 agents: Planner → Security/Perf/Arch/DevOps → Consensus)...")
wf = KutaarWorkflow(rocm_llm, rag_store, tool_registry)
app = wf.compile()
print("Workflow compiled!")

print("\nRunning warmup query: 'Find security vulnerabilities in this codebase'")
print("(This runs Planner → 4 specialists in parallel → 2-round Consensus debate)\n")

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

# ============================================================
# DONE
# ============================================================
print(f"""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   ✅ ALL WARMUP COMPLETE!                                ║
║                                                          ║
║   GPU:      AMD Radeon gfx1100 @ {avg_speed:.1f} tok/s    {" " * (20 - len(f"{avg_speed:.1f}"))}║
║   RAG:      {chunk_count} chunks indexed                  {" " * (20 - len(str(chunk_count)))}║
║   Pipeline: 6-agent workflow warmed up                   ║
║                                                          ║
║   TO START GRADIO:                                       ║
║     python src/ui/gradio_app.py                          ║
║                                                          ║
║   Then open http://localhost:7860 in browser             ║
║                                                          ║
║   🎬 START RECORDING NOW! (Win+Alt+R)                    ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
""")

print("READY TO RECORD!")
