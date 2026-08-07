# Kutaar 🔥

**Conversational Multi-Agent AI Engineering Assistant powered by AMD ROCm**

Built for **AMD AI DevMaster Hackathon — Track 2 (Agentic AI)**.

---

## What is Kutaar?

Kutaar is a conversational assistant that analyzes your codebase through a team of 6 specialized AI agents — all running **locally on AMD Radeon GPUs** via ROCm/HIP. Upload a repository, ask questions in natural language, and get a comprehensive analysis with cross-reviewed findings. No data ever leaves your machine.

### Agent Team

| Agent | Role | Tools |
|---|---|---|
| 🧠 **Planner** | Orchestrates analysis, decomposes queries | — |
| 🔒 **Security** | Finds vulnerabilities (OWASP, CWE, secrets) | Bandit, Semgrep |
| ⚡ **Performance** | Spots bottlenecks & optimization opportunities | Code search |
| 🏗️ **Architecture** | Evaluates design patterns & modularity | Git analyzer |
| 🚀 **DevOps** | Checks containerization & deployment readiness | Dockerfile validator |
| ⚖️ **Consensus** | Cross-review debate & final verdict | — |

### Key Features

- **Multi-turn conversation** — LangGraph checkpointing remembers context across turns
- **RAG-powered retrieval** — ChromaDB + sentence-transformers embeddings on ROCm GPU
- **Tool invocation** — Bandit, Semgrep, Git analysis, Dockerfile validation, code search
- **Multi-agent collaboration** — 5 specialist agents + Consensus with cross-review debate
- **100% local** — all inference runs on your AMD Radeon GPU, no cloud required
- **Bonus** — Radeon Cloud API comparison with quantization/distillation benchmarks

---

## Architecture

```
┌───────────────────────────────────────────────────────┐
│                   Streamlit Chat UI                     │
├───────────────────────────────────────────────────────┤
│                   LangGraph Workflow                    │
│   Planner → RAG → [Security, Perf, Arch, DevOps]      │
│                   → Consensus → Response               │
├───────────────────────────────────────────────────────┤
│  ROCm LLM Service  │  ChromaDB RAG  │  Tool Registry   │
│  (llama-cpp-python)│  (embeddings)  │  (7 tools)       │
├───────────────────────────────────────────────────────┤
│               AMD ROCm / HIP GPU Runtime                │
│          libggml-hip.so · hipBLAS · rocBLAS            │
└───────────────────────────────────────────────────────┘
```

### GPU Performance (AMD Radeon gfx1100 · ROCm 7.2.1)

| Metric | Value |
|---|---|
| **Token Generation** | **124 tok/s** |
| **Prompt Evaluation** | 17.4 tok/s |
| **Model Load Time** | 575 ms |
| **VRAM Usage** | 2.57 GB / 51 GB |
| **ROCm Compute Buffer** | 256.5 MiB |

**Optimizations:** Q4_K_M quantization · Full GPU offloading (28 layers) · CUDA Graphs · MFMA instructions · Batched inference (n_batch=512)

### Demo Video

[▶️ Watch the Kutaar demo](https://drive.google.com/drive/folders/1PHfQT8CkQi6C3Jq6fY6C_3cnXVxyGfLl)

---

## Prerequisites

| Requirement | Details |
|---|---|
| **GPU** | AMD Radeon GPU with ROCm installed (tested on gfx1100 / ROCm 7.2.1) |
| **Python** | 3.10 or newer |
| **llama-cpp-python** | Built with HIP/ROCm backend (`GGML_HIP=ON`) |
| **GGUF Model** | A quantized GGUF model (e.g. Llama 3.2 3B Instruct Q4_K_M) |
| **Disk** | ~5 GB for model + dependencies |

---

## Execution Steps

### Step 1 — Clone & enter the project

```bash
git clone <repo-url> devmaster
cd devmaster
```

### Step 2 — Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3 — Install dependencies

```bash
pip install -e .
```

This installs all core dependencies: LangGraph, LangChain, ChromaDB, Streamlit, sentence-transformers, Bandit, Semgrep, GitPython, and more.

### Step 4 — Install llama-cpp-python with ROCm support

> **Important:** llama-cpp-python must be compiled with `GGML_HIP=ON` for GPU acceleration. See the [HIP build guide](#appendix-a-llama-cpp-python-hiprocm-build) below.

```bash
pip install llama-cpp-python
```

If the pre-built wheel doesn't include HIP support, build from source (see Appendix A).

### Step 5 — Download a GGUF model

Download a quantized GGUF model and place it in the `models/` directory:

```bash
mkdir -p models
# Example: Llama 3.2 3B Instruct Q4_K_M
# Place the .gguf file at: models/Llama-3.2-3B-Instruct-Q4_K_M.gguf
```

You can use any GGUF model. Update the path via `--model-path` if using a different model.

### Step 6 — Launch the UI

```bash
streamlit run src/ui/chat_app.py
```

Or use the main entry point:

```bash
python -m src.main
```

The Streamlit UI opens at `http://localhost:8501`.

### Step 7 — Analyze a repository

1. In the sidebar, enter a repository path (e.g. `demo_repos/sample_app`)
2. Click **Index Repo** to chunk and embed the codebase
3. Type a question in the chat, for example:
   - *"Find all security vulnerabilities in this codebase"*
   - *"What performance bottlenecks exist?"*
   - *"Evaluate the architecture and suggest improvements"*
4. Watch the agents analyze, debate, and produce a consensus verdict

### Step 8 (Optional) — Run benchmarks

```bash
python -m src.main --benchmark
```

This runs a 5-prompt benchmark suite comparing local ROCm vs CPU vs Radeon Cloud API, measuring tokens/sec, GPU utilization, and VRAM usage. Results are saved to `benchmark_report.json`.

---

## Project Structure

```
devmaster/
├── pyproject.toml                 # Dependencies & build config
├── README.md                      # This file
├── plan.md                        # Full project blueprint
├── demo_repos/
│   ├── sample_app/                # Demo repo with intentional issues
│   ├── express_api/               # Node.js demo repo
│   └── fastapi_service/           # Python FastAPI demo repo
├── src/
│   ├── main.py                    # Entry point (UI or benchmarks)
│   ├── llm/
│   │   ├── rocm_service.py        # ROCm LLM singleton (llama-cpp-python)
│   │   └── cloud_api.py           # Radeon Cloud API client (bonus)
│   ├── state/
│   │   └── conversation_state.py  # LangGraph TypedDict state
│   ├── ingestion/
│   │   └── repo_indexer.py        # Code chunking & language detection
│   ├── rag/
│   │   └── chroma_store.py        # ChromaDB vector store
│   ├── agents/
│   │   ├── base_agent.py          # Abstract agent foundation
│   │   ├── planner_agent.py       # Orchestrator
│   │   ├── security_agent.py      # Vulnerability detection
│   │   ├── performance_agent.py   # Bottleneck analysis
│   │   ├── architecture_agent.py  # Design evaluation
│   │   ├── devops_agent.py        # Deployment checks
│   │   └── consensus_agent.py     # Cross-review & verdict
│   ├── graph/
│   │   └── workflow.py            # LangGraph StateGraph definition
│   ├── tools/
│   │   └── tool_registry.py       # 7 tools (Bandit, Semgrep, Git, etc.)
│   ├── ui/
│   │   └── chat_app.py            # Streamlit chat interface
│   └── benchmarks/
│       └── rocm_profiler.py       # GPU profiling & comparison
```

---

## CLI Reference

| Command | Description |
|---|---|
| `streamlit run src/ui/chat_app.py` | Launch the chat UI |
| `python -m src.main` | Launch via main entry point |
| `python -m src.main --benchmark` | Run GPU benchmark suite |
| `python -m src.main --model-path <path>` | Use a custom GGUF model |
| `python -m src.main --cloud-api-url <url> --cloud-api-key <key>` | Enable cloud comparison |
| `python -m src.main --log-level DEBUG` | Enable verbose logging |

---

## Scoring Alignment (Track 2)

| Criteria | Points | Implementation |
|---|---|---|
| Task positioning + creative scenarios | 20 | "Your private AI engineering team on AMD Radeon" — 5 specialist agents |
| Task decomposition, tools, RAG, memory | 20 | Planner decomposes; Bandit/Semgrep/Git tools; ChromaDB RAG; LangGraph memory |
| Smooth multi-turn interaction | 20 | Streamlit chat UI with context-aware follow-ups |
| Core inference on AMD Radeon GPU | 20 | llama-cpp-python + HIP backend; sentence-transformers on GPU |
| Inference speed optimization | 20 | Batched inference, Q4 quantization, benchmark comparison table |
| **Bonus:** Radeon cloud API + quantization | 20 | Cloud API client with quantized/distilled model comparison |

---

## Appendix A — llama-cpp-python HIP/ROCm Build

If the pip wheel doesn't include HIP support, build from source:

```bash
# Set ROCm path
export ROCM_PATH=/opt/rocm

# Clone and build llama.cpp with HIP
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
mkdir build_hip && cd build_hip

cmake .. \
  -DGGML_HIP=ON \
  -DAMDGPU_TARGETS=gfx1100 \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_SERVER=OFF

cmake --build . --config Release --target ggml llama -j$(nproc)

# Copy .so files to llama-cpp-python lib directory
cp bin/*.so* /path/to/venv/lib/python3.12/site-packages/llama_cpp/lib/

# Verify HIP symbols are present
strings /path/to/venv/lib/python3.12/site-packages/llama_cpp/lib/libggml-hip.so | grep hipblas
```

Then install llama-cpp-python without its bundled llama.cpp:

```bash
CMAKE_ARGS="-DGGML_HIP=ON" pip install llama-cpp-python --no-cache-dir --force-reinstall
```

---

## License

MIT — Built for AMD AI DevMaster Hackathon 2026.
