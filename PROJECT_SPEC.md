# 🔥 Kutaar — Project Specification Document

**AMD AI DevMaster Hackathon — Track 2: Development & Local Deployment of Private AI Agents**

**Team:** Script-Kitty01  
**Date:** August 6, 2026

---

## 1. Application Scenarios

Kutaar is a **conversational multi-agent AI engineering assistant** that brings the power of a full engineering review team to any developer's local machine. It runs entirely on AMD Radeon GPUs via ROCm, ensuring complete data privacy — no code ever leaves the user's machine.

### Target Users

| User | Scenario |
|------|----------|
| **Solo Developers** | Get instant code review feedback without waiting for teammates |
| **Small Teams** | Automated first-pass review before human PR review |
| **Security-Conscious Orgs** | Private vulnerability scanning without sending code to cloud APIs |
| **Open Source Maintainers** | Triage incoming PRs with automated quality checks |
| **Students & Learners** | Learn best practices through AI-guided code analysis |

### Key Use Cases

1. **Security Audit** — "Find all security vulnerabilities in this codebase" → detects hardcoded secrets, SQL injection, command injection, weak hashing, insecure deserialization
2. **Performance Review** — "What's slowing down my app?" → identifies O(n²) loops, memory-heavy patterns, blocking I/O, unnecessary deep copies
3. **Architecture Assessment** — "Is this well-designed?" → evaluates SOLID principles, coupling/cohesion, god classes, circular dependencies
4. **DevOps Readiness** — "Is this ready for production?" → checks Dockerfile quality, hardcoded configs, localhost references, missing health checks
5. **Full Codebase Review** — "Give me a comprehensive review" → all 4 agents run, Consensus agent synthesizes findings with quality score

---

## 2. Agent Architecture

Kutaar uses a **6-agent collaborative system** orchestrated by LangGraph, with all inference running locally on AMD Radeon GPU via ROCm.

```
┌─────────────────────────────────────────────────────────┐
│                   Gradio Chat UI                         │
│         "Find security vulnerabilities in this repo"     │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              🧠 Planner Agent                            │
│  Decomposes query → selects agents → plans RAG queries   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│         LangGraph State (Shared Memory)                  │
│  Conversation history · Repo index · Agent findings      │
│  Cross-review feedback · Consensus decisions             │
└──┬────────┬──────────┬──────────┬───────────────────────┘
   │        │          │          │
┌──▼──┐ ┌──▼──┐ ┌────▼──┐ ┌────▼────┐
│🔒   │ │⚡   │ │🏗️    │ │🚀       │
│ Sec │ │Perf │ │ Arch  │ │ DevOps  │
│     │ │     │ │       │ │         │
│Bandit│ │Code │ │ Git   │ │Docker   │
│Semgrp│ │Srch │ │ Deps  │ │Validate │
└──┬──┘ └──┬──┘ └───┬───┘ └────┬────┘
   │       │        │           │
   └───────┴────────┴───────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│         ⚖️ Consensus Agent                           │
│  Cross-review debate · Conflict resolution           │
│  Confidence adjustment · Final verdict + score       │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│         📊 Final Report                              │
│  Quality Score · Prioritized Findings · Action Items │
└─────────────────────────────────────────────────────┘
```

### Agent Roles

| Agent | Role | Tools | Output |
|-------|------|-------|--------|
| 🧠 **Planner** | Orchestrates analysis, decomposes queries | — | Structured task plan (JSON) |
| 🔒 **Security** | Finds vulnerabilities (OWASP, CWE, secrets) | Bandit, Semgrep, Code Search | Severity-scored findings |
| ⚡ **Performance** | Spots bottlenecks & anti-patterns | Code Search, Pattern Matching | Performance findings |
| 🏗️ **Architecture** | Evaluates design & modularity | Git Analyzer, Code Search | Architecture findings |
| 🚀 **DevOps** | Checks deployment readiness | Dockerfile Validator, Code Search | DevOps findings |
| ⚖️ **Consensus** | Cross-review debate & final verdict | — | Unified report + quality score |

### Workflow (LangGraph StateGraph)

```
User Query → Planner → RAG Retrieval → [Security, Perf, Arch, DevOps] in parallel
                                         ↓
                                    Consensus (debate + synthesis)
                                         ↓
                                    Formatted Response → User
```

---

## 3. Core Capabilities

### 3.1 Multi-Agent Collaboration
- **6 specialized agents** with distinct system prompts and expertise domains
- **Cross-review debate**: Consensus agent identifies conflicting findings and facilitates resolution
- **Confidence scoring**: Each finding includes a 0.0-1.0 confidence score, adjusted during debate

### 3.2 Retrieval-Augmented Generation (RAG)
- **ChromaDB** vector store with persistent local storage
- **sentence-transformers** embeddings computed on ROCm GPU
- Code files chunked by function/class boundaries for semantic retrieval
- Top-k retrieval provides agents with relevant code context

### 3.3 Tool Invocation
- **Bandit** — Python static security analysis
- **Semgrep** — Multi-language pattern-based scanning
- **Git Analyzer** — Churn hotspots, commit history analysis
- **Dockerfile Validator** — Best practices checking
- **Code Search** — Regex-based pattern matching across codebase
- **File Reader** — Direct file access for deep analysis

### 3.4 Conversation Memory
- **LangGraph checkpointing** with `MemorySaver`
- Full conversation history preserved across turns
- Agents remember previous findings and user preferences
- Multi-turn drill-down: "Tell me more about that SQL injection"

### 3.5 Privacy-First Design
- **100% local inference** — no data sent to external APIs
- All models run on AMD Radeon GPU via ROCm
- ChromaDB stores embeddings locally
- No telemetry, no cloud dependency

---

## 4. Model Introduction & Local Deployment Plan

### 4.1 LLM: Llama 3.2 3B Instruct (Q4_K_M Quantized)

| Property | Value |
|----------|-------|
| **Base Model** | Meta Llama 3.2 3B Instruct |
| **Quantization** | Q4_K_M (4-bit with medium quality) |
| **Format** | GGUF |
| **Size on Disk** | ~2.0 GB |
| **VRAM Usage** | ~2.6 GB |
| **Context Window** | 2048 tokens |
| **Batch Size** | 512 tokens |
| **Inference Engine** | llama-cpp-python with HIP/ROCm backend |

**Why this model:**
- Small enough to run on consumer Radeon GPUs (fits in 4GB+ VRAM)
- Q4_K_M quantization balances quality and speed
- GGUF format enables efficient GPU offloading via llama.cpp
- Strong instruction-following for structured JSON output (agent findings)

### 4.2 Embedding Model: sentence-transformers

| Property | Value |
|----------|-------|
| **Model** | all-MiniLM-L6-v2 |
| **Dimension** | 384 |
| **GPU Backend** | ROCm via PyTorch |

### 4.3 Deployment Architecture

```
┌──────────────────────────────────────────┐
│           AMD Radeon GPU (gfx1100)        │
│  ┌─────────────┐  ┌────────────────────┐ │
│  │ llama.cpp    │  │ sentence-          │ │
│  │ (HIP/ROCm)   │  │ transformers       │ │
│  │              │  │ (ROCm PyTorch)     │ │
│  │ libggml-hip  │  │                    │ │
│  │ libllama     │  │ GPU embeddings     │ │
│  └─────────────┘  └────────────────────┘ │
│         ↕                  ↕              │
│  ┌─────────────────────────────────────┐ │
│  │        ROCm 7.2.1 Runtime            │ │
│  │   hipBLAS · rocBLAS · HIP compiler   │ │
│  └─────────────────────────────────────┘ │
└──────────────────────────────────────────┘
         ↕
┌──────────────────────────────────────────┐
│         Python Application Layer          │
│  ┌──────────┐ ┌────────┐ ┌────────────┐ │
│  │ LangGraph │ │ Gradio │ │ ChromaDB    │ │
│  │ Workflow  │ │ UI     │ │ RAG Store   │ │
│  └──────────┘ └────────┘ └────────────┘ │
└──────────────────────────────────────────┘
```

### 4.4 Quick Start

```bash
# 1. Clone and install
git clone https://github.com/Script-Kitty01/devMaster_amd.git
cd devMaster_amd
pip install -e .

# 2. Download model
# Place Llama-3.2-3B-Instruct-Q4_K_M.gguf in models/

# 3. Launch
python -m src.main
# Or: python src/ui/gradio_app.py
```

---

## 5. AMD Radeon GPU Optimization

### 5.1 HIP/ROCm Build Optimization

The llama.cpp backend was compiled from source with full HIP support for the target GPU:

```bash
cmake .. \
  -DGGML_HIP=ON \
  -DAMDGPU_TARGETS=gfx1100 \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DGGML_HIP_GRAPHS=ON \
  -DGGML_HIP_MMQ_MFMA=ON
```

**Key optimizations:**
- **GPU-specific compilation**: Targeting `gfx1100` (RDNA 3) enables architecture-specific optimizations
- **CUDA Graphs**: `GGML_HIP_GRAPHS=ON` reduces kernel launch overhead by reusing execution graphs
- **MFMA instructions**: `GGML_HIP_MMQ_MFMA=ON` uses Matrix Fused Multiply-Add for faster matrix operations
- **Release build**: Full compiler optimizations (`-O3 -DNDEBUG`)

### 5.2 Inference Optimizations

| Technique | Impact |
|-----------|--------|
| **Q4_K_M Quantization** | 4× memory reduction, faster memory bandwidth utilization |
| **GPU Layer Offloading** (`n_gpu_layers=-1`) | All 28 transformer layers on GPU |
| **Batch Processing** (`n_batch=512`) | Amortizes kernel launch overhead |
| **CUDA Graph Reuse** | 18 graph reuses observed — eliminates recompilation |
| **ROCm Compute Buffer** | 256.5 MiB pre-allocated — avoids runtime allocation stalls |

### 5.3 Performance Benchmarks

Measured on AMD Radeon Graphics (gfx1100, 96 CUs, 51 GB VRAM) with ROCm 7.2.1:

| Metric | Value |
|--------|-------|
| **Model Load Time** | 575 ms |
| **Prompt Eval** | 57.51 ms/token (17.39 tok/s) |
| **Token Generation** | 8.05 ms/token (124.25 tok/s) |
| **VRAM Usage** | 2.57 GB / 51 GB |
| **ROCm Compute Buffer** | 256.5 MiB |

### 5.4 Comparison: CPU vs GPU

| Metric | CPU Only | GPU (ROCm/HIP) | Speedup |
|--------|----------|----------------|---------|
| Token Generation | ~8 tok/s | 124 tok/s | **15.5×** |
| Model Load | ~2.5s | 0.58s | **4.3×** |
| Embedding Generation | ~50 docs/s | ~400 docs/s | **8×** |

---

## 6. Technical Stack

| Layer | Technology |
|-------|-----------|
| **GPU Runtime** | AMD ROCm 7.2.1, HIP 7.2.53211 |
| **Inference Engine** | llama-cpp-python 0.3.34 (custom HIP build) |
| **LLM** | Llama 3.2 3B Instruct Q4_K_M GGUF |
| **Embeddings** | sentence-transformers (all-MiniLM-L6-v2) on ROCm PyTorch |
| **Agent Framework** | LangGraph (StateGraph + checkpointing) |
| **RAG** | ChromaDB (persistent local vector store) |
| **UI** | Gradio 5 (HTTP polling, proxy-compatible) |
| **Tools** | Bandit, Semgrep, GitPython, Docker |
| **Language** | Python 3.12 |

---

## 7. Innovation Highlights

1. **6-Agent Collaborative System** — Not just a single-agent chatbot, but a full engineering team with specialized roles, cross-review debate, and consensus building
2. **100% Local on AMD GPU** — Complete privacy; all inference, embeddings, and analysis run on the user's Radeon GPU
3. **Custom HIP Build** — llama.cpp compiled from source with `GGML_HIP=ON`, targeting gfx1100 with CUDA graphs and MFMA optimizations
4. **Structured Multi-Turn Memory** — LangGraph checkpointing preserves full conversation context, enabling deep drill-down analysis
5. **Tool-Augmented Agents** — Agents don't just use LLM reasoning; they invoke real static analysis tools (Bandit, Semgrep) for evidence-based findings

---

*Built for AMD AI DevMaster Hackathon 2026 — Track 2*
