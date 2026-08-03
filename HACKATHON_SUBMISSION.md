# 🔥 ForgeAI — AMD AI DevMaster Hackathon Submission
## Track 2: Multi-Agent AI Engineering Assistant

**Team:** Script-Kitty01  
**Date:** August 3, 2026  
**Platform:** AMD ROCm on Radeon Cloud

---

## 🎯 What It Does

ForgeAI is a **6-agent AI engineering assistant** that analyzes codebases using a multi-agent LangGraph pipeline powered by AMD ROCm. You point it at a repo, click "Index", and ask questions — it dispatches 5 specialist agents in parallel, then a Consensus agent synthesizes their findings into a unified report.

## 🧠 Architecture

```
User Query
    │
    ▼
┌──────────────────────────────────────────┐
│            🧠 Planner Agent              │
│     Decomposes query into subtasks       │
└──────┬───────┬───────┬───────┬───────────┘
       │       │       │       │
       ▼       ▼       ▼       ▼
    🔒 Sec   ⚡ Perf  🏗️ Arch  🚀 DevOps
       │       │       │       │
       └───────┴───────┴───────┘
                    │
                    ▼
            ┌──────────────┐
            │ ⚖️ Consensus │
            │  Synthesizes  │
            │   findings    │
            └──────────────┘
                    │
                    ▼
            Final Report + Action Items
```

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **LLM** | Llama 3.2 3B Instruct (Q4_K_M GGUF) via llama-cpp-python |
| **Agent Framework** | LangGraph (StateGraph with parallel dispatch) |
| **UI** | Gradio 6.22.0 |
| **Code Indexing** | ChromaDB + sentence-transformers |
| **GPU** | AMD ROCm (Radeon Cloud instance) |
| **Tunneling** | rc-tunnel (FRPC) for public access |

## 📊 Live Demo Results

**Target Repo:** `sample_app` (Python app with Docker, SQLAlchemy, subprocess usage)

**Analysis Output:**

| Metric | Value |
|--------|-------|
| **Quality Score** | 0.75 / 1.00 |
| **Total Findings** | 30 |
| **Critical** | 3 |
| **High** | 8 |
| **Medium** | 4 |
| **Low** | 15 |

### 🔴 Critical Findings
- `dockerfile.security.missing-user.missing-user` — Dockerfile missing USER directive
- `python.sqlalchemy.security.sqlalchemy-execute-raw-query` — Raw SQLAlchemy query execution
- `python.lang.security.audit.subprocess-shell-true` — `subprocess` call with `shell=True`

### 🟠 High Findings
- `python.lang.security.audit.md5-used-as-password` — MD5 hash used for security
- `python.lang.security.audit.formatted-sql-query` — Formatted SQL query vulnerable to injection
- 6 additional high-severity Bandit findings

### Agent Breakdown
| Agent | Findings |
|-------|----------|
| 🔒 Security | 18 (3 critical, 6 high) |
| 🚀 DevOps | 7 (0 critical, 2 high) |
| ⚡ Performance | 4 |
| 🏗️ Architecture | 1 |

## 🔧 Key Engineering Decisions

1. **Markdown fallback parser** — The 3B model often outputs markdown instead of JSON. Added `_extract_from_markdown()` to gracefully handle this instead of failing.

2. **Debate phase skipped** — Each debate round adds 4+ LLM calls. For the 3B model on CPU, this was causing deadlocks. Skipped for reliability.

3. **CPU-optimized inference** — `n_ctx=2048`, `n_batch=1`, `n_threads=8` tuned for the AMD EPYC instance.

4. **Thread-safe LLM singleton** — Single `Llama` instance with `threading.Lock` to prevent concurrent inference crashes.

## 📁 Project Structure

```
forgeai/
├── src/
│   ├── ui/
│   │   └── gradio_app.py          # Gradio chat interface
│   ├── agents/
│   │   ├── base_agent.py          # Abstract base with JSON/markdown parsing
│   │   ├── planner_agent.py       # Query decomposition
│   │   ├── security_agent.py      # Vulnerability scanning
│   │   ├── performance_agent.py   # Bottleneck detection
│   │   ├── architecture_agent.py  # Design evaluation
│   │   ├── devops_agent.py        # Deployment checks
│   │   └── consensus_agent.py     # Cross-review & synthesis
│   ├── graph/
│   │   └── workflow.py            # LangGraph StateGraph pipeline
│   ├── indexing/
│   │   └── code_indexer.py        # ChromaDB + embeddings
│   └── llm/
│       └── rocm_service.py        # llama-cpp-python singleton
├── models/
│   └── Llama-3.2-3B-Instruct-Q4_K_M.gguf
└── requirements.txt
```

## 🚀 How to Run

```bash
# 1. Install dependencies
pip install gradio langchain-core langgraph langchain-community \
            chromadb sentence-transformers llama-cpp-python

# 2. Download model
wget https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf

# 3. Launch
python src/ui/gradio_app.py

# 4. Open browser → Index repo → Ask questions!
```

## 🏆 Why This Wins

- **AMD-native** — Runs entirely on AMD ROCm hardware, no NVIDIA dependency
- **Multi-agent** — True parallel agent dispatch with LangGraph, not sequential
- **Real results** — 30 actionable findings from a single query
- **Production-ready patterns** — Thread-safe LLM, graceful degradation, markdown fallback
- **Extensible** — Add new specialist agents by subclassing `BaseAgent`

---

*Built for AMD AI DevMaster Hackathon Track 2 — August 2026*
