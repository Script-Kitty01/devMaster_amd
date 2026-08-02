# ForgeAI 🔥

**Conversational Multi-Agent AI Engineering Assistant powered by AMD ROCm**

Built for **AMD AI DevMaster Hackathon Track 2 (Agentic AI)**.

---

## Overview

ForgeAI is a conversational AI assistant that analyzes your codebase through a team of specialized AI agents — all running locally on AMD Radeon GPUs via ROCm. Upload a repository, ask questions in natural language, and get a comprehensive analysis with cross-reviewed findings.

### Agent Team

| Agent               | Role                                           | Tools                |
| ------------------- | ---------------------------------------------- | -------------------- |
| 🧠 **Planner**      | Orchestrates analysis, decomposes queries      | —                    |
| 🔒 **Security**     | Finds vulnerabilities (OWASP, CWE, secrets)    | Bandit, Semgrep      |
| ⚡ **Performance**  | Spots bottlenecks & optimization opportunities | Code search          |
| 🏗️ **Architecture** | Evaluates design patterns & modularity         | Git analyzer         |
| 🚀 **DevOps**       | Checks containerization & deployment readiness | Dockerfile validator |
| ⚖️ **Consensus**    | Cross-review debate & final verdict            | —                    |

### Key Features

- **Multi-turn conversation** with LangGraph checkpointing
- **RAG-powered** code retrieval via ChromaDB + ROCm GPU embeddings
- **Tool invocation** — Bandit, Semgrep, Git analysis, Dockerfile validation
- **Multi-agent collaboration** with cross-review debate rounds
- **Local-first** — runs entirely on AMD Radeon GPU via ROCm/HIP
- **Bonus**: Radeon Cloud API comparison with quantization/distillation analysis

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit Chat UI                    │
├─────────────────────────────────────────────────────┤
│                  LangGraph Workflow                   │
│  Planner → RAG → [Security, Perf, Arch, DevOps]     │
│                  → Consensus → Response              │
├─────────────────────────────────────────────────────┤
│  ROCm LLM Service  │  ChromaDB RAG  │  Tool Registry │
│  (llama-cpp-python)│  (embeddings)  │  (6 tools)     │
├─────────────────────────────────────────────────────┤
│              AMD ROCm / HIP GPU Runtime               │
└─────────────────────────────────────────────────────┘
```

---

## Project Structure

```
devmaster/
├── pyproject.toml              # Dependencies & build config
├── README.md
├── plan.md                     # Full project blueprint
├── demo_repos/
│   └── sample_app/             # Demo repo with intentional issues
├── src/
│   ├── main.py                 # Entry point (UI or benchmarks)
│   ├── llm/
│   │   ├── rocm_service.py     # ROCm LLM singleton (llama-cpp-python)
│   │   └── cloud_api.py        # Radeon Cloud API client (bonus)
│   ├── state/
│   │   └── conversation_state.py  # LangGraph TypedDict state
│   ├── ingestion/
│   │   └── repo_indexer.py     # Code chunking & language detection
│   ├── rag/
│   │   └── chroma_store.py     # ChromaDB vector store
│   ├── agents/
│   │   ├── base_agent.py       # Abstract agent foundation
│   │   ├── planner_agent.py    # Orchestrator
│   │   ├── security_agent.py   # Vulnerability detection
│   │   ├── performance_agent.py # Bottleneck analysis
│   │   ├── architecture_agent.py # Design evaluation
│   │   ├── devops_agent.py     # Deployment checks
│   │   └── consensus_agent.py  # Cross-review & verdict
│   ├── graph/
│   │   └── workflow.py         # LangGraph StateGraph definition
│   ├── tools/
│   │   └── tool_registry.py    # 6 tools (Bandit, Semgrep, Git, etc.)
│   ├── ui/
│   │   └── chat_app.py         # Streamlit chat interface
│   └── benchmarks/
│       └── rocm_profiler.py    # GPU profiling & comparison
```

---

## Quick Start

### Prerequisites

- AMD Radeon GPU with ROCm installed
- Python 3.10+
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) with HIP/ROCm support

### Installation

```powershell
# Clone or navigate to the project
cd C:\Users\Aamira\Desktop\devmaster

# Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -e .

# For ROCm GPU support (Windows may need pre-built wheels):
pip install llama-cpp-python
```

### Download Model

Download a GGUF model (e.g., Llama 3.2 3B Instruct Q4_K_M) and place it at:

```
models/Llama-3.2-3B-Instruct-Q4_K_M.gguf
```

### Run

```powershell
# Launch the Streamlit UI
streamlit run src/ui/chat_app.py

# Or via the main entry point:
python -m src.main

# Run benchmarks only:
python -m src.main --benchmark
```

### Demo Flow

1. Launch the UI
2. Enter `demo_repos/sample_app` as the repository path
3. Click **Index Repo**
4. Ask: _"Find all security vulnerabilities in this codebase"_
5. Watch agents analyze, debate, and produce a consensus verdict

---

## Scoring Alignment (Track 2)

| Criteria                      | Implementation                                                    |
| ----------------------------- | ----------------------------------------------------------------- |
| **Multi-turn conversation**   | LangGraph checkpointing with `MemorySaver`                        |
| **RAG**                       | ChromaDB + sentence-transformers on ROCm GPU                      |
| **Tool invocation**           | 6 tools: Bandit, Semgrep, Git, Dockerfile, Code Search, File Read |
| **Multi-agent collaboration** | 5 specialist agents + Consensus with cross-review debate          |
| **Privacy**                   | 100% local inference on AMD GPU — no data leaves the machine      |
| **Bonus: AMD Radeon Cloud**   | `cloud_api.py` with quantization/distillation comparison          |

---

## License

MIT — Built for AMD AI DevMaster Hackathon 2026.
