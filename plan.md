# ForgeAI — Conversational Multi-Agent Engineering Assistant

**AMD AI DevMaster Hackathon — Track 2: Agentic AI**

> "Your private AI engineering team, running entirely on your AMD Radeon GPU."

---

## TL;DR

A conversational, locally-deployed AI engineering assistant where 5 specialist agents (Planner, Security, Performance, Architecture, DevOps) collaborate through multi-turn dialogue with the user. Agents use RAG for code retrieval, invoke real tools (bandit, semgrep, rocprof), maintain conversation memory, and debate findings before reaching consensus. All inference runs locally on AMD Radeon GPU via ROCm with quantized models, batched inference, and optional Radeon cloud API for bonus points.

---

## Track 2 Scoring Alignment (120 Points)

| Official Criteria                                | Points | How ForgeAI Delivers                                                                                                                              |
| ------------------------------------------------ | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Clear task positioning + creative scenarios      | 20     | "Your private AI engineering team on AMD Radeon" — 5 specialist agents collaborating                                                              |
| Task decomposition, tool invocation, RAG, memory | 20     | Planner decomposes tasks. Agents invoke bandit/semgrep/rocprof. ChromaDB RAG. LangGraph checkpointing for memory. **All 5 capabilities covered.** |
| Smooth multi-turn interaction experience         | 20     | Streamlit chat UI — user asks follow-ups, agents remember context, drill deeper                                                                   |
| Core inference on AMD Radeon GPU                 | 20     | llama-cpp-python + HIP backend, sentence-transformers embeddings on GPU                                                                           |
| Targeted inference speed optimization            | 20     | Batched inference, Q4 quantization, benchmark comparison table                                                                                    |
| **Bonus: Radeon cloud model API + quantization** | 20     | Parallel Radeon cloud API path with quantized/distilled model comparison                                                                          |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit Chat UI                   │
│  "Review my repo for security issues"               │
│  "Tell me more about that SQL injection"            │
│  "What if I use parameterized queries?"             │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              🧠 Planner Agent                        │
│  Decides: which agents, what tools, what order      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              Shared Memory (LangGraph State)         │
│  Conversation history · Repo index · Agent findings │
│  Cross-review feedback · Consensus decisions        │
└──┬────────┬──────────┬──────────┬───────────────────┘
   │        │          │          │
┌──▼──┐ ┌──▼──┐ ┌────▼──┐ ┌────▼────┐
│🔒   │ │⚡   │ │🏗️    │ │🚀       │
│ Sec │ │Perf │ │ Arch  │ │ DevOps  │
│     │ │     │ │       │ │         │
│Tools│ │Tools│ │ Tools │ │ Tools   │
│bandit│ │rocprof│ │git   │ │docker  │
│semgrep│ │     │ │dep.  │ │validate │
└──┬──┘ └──┬──┘ └───┬───┘ └────┬────┘
   │       │        │           │
   └───────┴────────┴───────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│         🔍 RAG Engine (ChromaDB + embeddings)        │
│  Indexes repo code · Retrieves relevant snippets     │
│  Embedding model runs on ROCm GPU                    │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│         📊 Consensus Agent                           │
│  Resolves conflicts · Adjusts confidence · Reports   │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│         💾 Conversation Memory (LangGraph Checkpoint)│
│  Multi-turn context · User preferences · History     │
└─────────────────────────────────────────────────────┘
```

### Two Inference Paths (for bonus points)

| Path                 | Engine                     | Use Case                                                                        |
| -------------------- | -------------------------- | ------------------------------------------------------------------------------- |
| **Local ROCm**       | llama-cpp-python + HIP     | Primary path — all agent reasoning, RAG embeddings                              |
| **Radeon Cloud API** | AMD Radeon cloud model API | Bonus path — quantized/distilled model comparison, fallback for heavy workloads |

---

## Phases & Steps

### Phase 1: Foundation (Day 1-2)

_Depends on: nothing_

1. **ROCm environment setup** — Install ROCm drivers, verify `rocm-smi` works, confirm GPU is detected. Install llama-cpp-python with ROCm/HIP backend. Download quantized model (Llama 3.2 3B Q4_K_M — small, fast, fits consumer Radeon). Also install sentence-transformers for embedding generation on GPU.

2. **Project scaffolding** — Initialize Python project with `pyproject.toml`. Set up virtual environment. Install: LangGraph, LangChain, llama-cpp-python (ROCm), ChromaDB, sentence-transformers, Streamlit, gitpython, pygments, bandit, semgrep.

3. **Verify GPU inference** — Run test inference through llama-cpp-python on GPU. Run test embedding generation through sentence-transformers on GPU. Record baseline latency and throughput for both. First ROCm benchmark data points.

4. **Repository Indexer** — Build module that clones repos (gitpython), walks file tree, detects languages (pygments), extracts file contents (skip binaries, cap at 2000 lines), identifies dependency/config files. Outputs structured repo profile.

5. **RAG Engine (ChromaDB)** — Chunk repo files into embeddable segments. Generate embeddings using sentence-transformers on ROCm GPU. Store in ChromaDB (persistent local). Build retrieval function: given a query, return top-k relevant code snippets with file:line references. This satisfies the "local knowledge retrieval (RAG)" requirement.

### Phase 2: Agent Core (Day 3-4)

_Depends on: Phase 1_

6. **Shared LLM service** — Singleton `ROCmLLM` class wrapping llama-cpp-python with GPU offloading. Support batched inference. Also create `RadeonCloudLLM` wrapper for the bonus path (AMD Radeon cloud model API with quantization/distillation).

7. **Shared Memory + Conversation State** — LangGraph `StateGraph` with `ConversationState` TypedDict: conversation history (list of user/agent messages), repo profile, RAG retrieval context, agent findings, cross-review feedback, consensus output. Use LangGraph checkpointing for multi-turn memory persistence.

8. **Planner Agent** — Takes user message + conversation history + repo profile. Decides: which specialist agents to invoke, which tools they should use, what RAG queries to run, execution order. Outputs structured task plan. Example: user says "find security issues" → Planner decides "invoke Security agent, run bandit + semgrep, RAG query for auth/input handling code."

9. **Security Engineer Agent** — Receives Planner's task list + RAG-retrieved code. Invokes tools: `bandit` (static analysis), `semgrep` (pattern scanning). Then uses LLM to analyze tool output + retrieved code for: hardcoded secrets, injection risks, unsafe patterns, dependency vulnerabilities. Every finding: Problem → Evidence (file:line, tool output) → Fix → Confidence (0-100%).

10. **Performance Engineer Agent** — Receives Planner's task list + RAG-retrieved code. Invokes tools: parses profiling data if available, analyzes GPU kernel code patterns. LLM analyzes for: N+1 patterns, blocking I/O, missing caching, GPU kernel inefficiencies, memory allocation. Every finding: Problem → Evidence → Fix → Estimated Impact (%) → Confidence.

11. **Architecture Engineer Agent** — Receives Planner's task list + RAG-retrieved code. Invokes tools: git log analysis (coupling metrics), dependency graph parsing. LLM analyzes: module coupling, circular deps, SOLID violations, API design, project structure. Every finding: Problem → Evidence → Fix → Confidence.

12. **DevOps Engineer Agent** — Receives Planner's task list + RAG-retrieved code. Invokes tools: Dockerfile validation, CI config parsing. LLM analyzes: Dockerfile quality, CI/CD pipeline, environment config, deployment risks. Every finding: Problem → Evidence → Fix → Confidence.

### Phase 3: Collaboration & Conversation (Day 5)

_Depends on: Phase 2_

13. **Cross-Review Round** — After specialists produce findings, each agent reviews the others' findings via Shared Memory. Security reviews Performance's suggestions for safety risks. Performance reviews Architecture's for overhead. Architecture reviews DevOps's for coupling impact. DevOps reviews Security's for deployment implications. Agents can agree (boost confidence), disagree (flag conflict), or add context.

14. **Consensus Agent** — Reads all findings + cross-review feedback. Resolves conflicts, adjusts confidence scores. Produces unified, ranked issue list. This is the visible "debate resolution" moment in the chat UI.

15. **Multi-Turn Conversation Loop** — Wire everything into LangGraph's conversational loop. User sends message → Planner routes → agents execute → Consensus → response back to user. User can follow up ("tell me more about X", "what if I fix it this way?") → Planner re-routes with conversation context. LangGraph checkpointing preserves state across turns.

16. **Chat Response Formatter** — Formats agent responses for the chat UI. Includes: agent identity (which agent is speaking), findings with expandable evidence, confidence badges, tool invocation logs (show that bandit/semgrep ran), "ask a follow-up" suggestions.

### Phase 4: UI & ROCm Optimization (Day 6)

_Depends on: Phase 3_

17. **Streamlit Chat UI** — Chat interface with: message history (user + agent responses), agent identity labels (🔒 Security, ⚡ Performance, etc.), expandable finding cards (Problem → Evidence → Fix → Impact → Confidence), tool execution logs (collapsible), repo upload widget (URL or local path). The cross-review debate is visible as agents "speaking" to each other before Consensus responds.

18. **ROCm Benchmark Dashboard** — Sidebar or tab showing:

    | Configuration            | Time | Tokens/sec | GPU Util |
    | ------------------------ | ---- | ---------- | -------- |
    | CPU only                 | 18s  | 8          | —        |
    | Radeon GPU (local)       | 5s   | 29         | 91%      |
    | Radeon + Batch           | 2.7s | 55         | 94%      |
    | Radeon Cloud API (bonus) | 1.8s | 72         | —        |

    Plus: model name, quantization level, `rocm-smi` screenshot, embedding generation speed.

19. **Bonus: Radeon Cloud API Integration** — Implement the Radeon cloud model API path. Show a comparison: same agent task run on local ROCm vs. Radeon cloud API with quantization/distillation. Demonstrate speed difference. This targets the 20 bonus points.

### Phase 5: Demo Prep (Day 7)

_Depends on: Phase 4_

20. **Prepare demo repos** — 2-3 small repos with intentional issues across all 4 domains. Repo 1: security-heavy. Repo 2: performance-heavy. Repo 3: architecture + DevOps.

21. **Script the demo conversation** — Pre-plan a compelling multi-turn dialogue:
    - Turn 1: "Review this repo for security issues" → Security agent responds with findings
    - Turn 2: "Tell me more about that SQL injection — how would I fix it?" → Security drills deeper with code examples
    - Turn 3: "Would that fix impact performance?" → Planner invokes Performance agent to evaluate the fix
    - Turn 4: "Give me a summary of everything you found" → Consensus agent produces unified report
      This demonstrates: multi-turn interaction, tool invocation, RAG, memory, cross-agent collaboration.

22. **Record demo video** — 3-5 minutes. Show: repo upload → multi-turn conversation → agents debating → tool execution logs → final report → ROCm benchmark dashboard → Radeon cloud API comparison (bonus).

23. **Prepare submission materials** — Project spec document (PDF): application scenarios, agent architecture diagram, core capabilities, model + local deployment plan, ROCm optimization description. README with setup instructions. PPT/poster.

---

## Relevant Files (to be created)

```
devmaster/
├── pyproject.toml
├── README.md
├── plan.md
├── src/
│   ├── llm/
│   │   ├── rocm_service.py          # Singleton ROCmLLM: GPU offloading, batched inference, embeddings
│   │   └── radeon_cloud.py          # RadeonCloudLLM wrapper for AMD cloud API (bonus)
│   ├── state/
│   │   └── conversation_state.py    # ConversationState TypedDict for LangGraph
│   ├── ingestion/
│   │   └── repo_indexer.py          # Repo cloning, file walking, language detection, dependency scanning
│   ├── rag/
│   │   └── chroma_store.py          # ChromaDB: chunking, GPU embeddings, indexing, retrieval
│   ├── agents/
│   │   ├── planner.py               # Routes user intent → agent + tool selection + RAG queries
│   │   ├── security.py              # Invokes bandit + semgrep, LLM analysis, confidence-scored findings
│   │   ├── performance.py           # Parses profiling data, LLM analysis, estimated impact + confidence
│   │   ├── architecture.py          # Git/dep analysis, LLM analysis, confidence-scored findings
│   │   ├── devops.py                # Dockerfile/CI validation, LLM analysis, confidence-scored findings
│   │   └── consensus.py             # Conflict resolution, confidence adjustment, response formatting
│   ├── graph/
│   │   └── workflow.py              # LangGraph StateGraph: conversational loop, routing, cross-review, checkpointing
│   ├── tools/
│   │   └── tool_registry.py         # Tool definitions: bandit, semgrep, rocprof parser, git log, docker validator
│   ├── ui/
│   │   └── chat_app.py              # Streamlit chat UI: history, agent labels, findings, tool logs, benchmarks
│   └── benchmarks/
│       └── rocm_profiler.py         # ROCm benchmarking: tokens/sec, GPU util, comparison table
└── demo_repos/                      # 2-3 demo repos with intentional issues
```

---

## Verification Checklist

- [ ] **ROCm**: `rocm-smi` shows GPU. llama-cpp-python inference with `n_gpu_layers=-1` shows GPU utilization. sentence-transformers embeddings run on GPU.
- [ ] **RAG**: Index a test repo → query "find authentication code" → ChromaDB returns relevant snippets with correct file:line references.
- [ ] **Tool invocation**: Run Security agent on a Python file with known issues → verify bandit and semgrep output appears in agent findings with correct file:line evidence.
- [ ] **Multi-turn conversation**: Start a chat → ask about security → follow up with "tell me more about X" → verify agent remembers context from previous turn and drills deeper.
- [ ] **Cross-review**: Run on a repo where Security and Performance would disagree → verify cross-review messages appear in chat → Consensus resolves with adjusted confidence.
- [ ] **End-to-end demo**: Full multi-turn conversation (4+ turns) → agents debate → tools execute → ROCm benchmarks visible → Radeon cloud API comparison shown.
- [ ] **Minimum requirements**: RAG ✓, Tool invocation ✓, Multi-step planning ✓, Multi-turn memory ✓, Privacy (all-local) ✓. All 5 covered, exceeding the 2 minimum.

---

## Key Decisions

| Decision            | Choice                                                                                                                |
| ------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **Product name**    | ForgeAI — "Your private AI engineering team, running entirely on your AMD Radeon GPU."                                |
| **Positioning**     | Conversational multi-agent engineering assistant — NOT a one-shot code review tool                                    |
| **Primary model**   | Llama 3.2 3B Q4_K_M (fast, fits consumer Radeon)                                                                      |
| **Fallback model**  | Mistral 7B Q4 (if 8GB+ VRAM available)                                                                                |
| **Embedding model** | all-MiniLM-L6-v2 via sentence-transformers on ROCm GPU                                                                |
| **Frontend**        | Streamlit chat UI — conversational, not dashboard                                                                     |
| **Agent framework** | LangGraph StateGraph with checkpointing for multi-turn memory                                                         |
| **RAG**             | ChromaDB with GPU embeddings, chunk size ~500 lines with overlap                                                      |
| **Tools**           | bandit, semgrep, rocprof parser, git log analyzer, dockerfile validator                                               |
| **Scope IN**        | Conversational multi-agent analysis, RAG, tool invocation, multi-turn memory, ROCm benchmarks, Radeon cloud API bonus |
| **Scope OUT**       | Auto-generating PRs, real-time monitoring, CI/CD execution, Kubernetes deployment                                     |
| **Bonus strategy**  | Radeon cloud API as parallel inference path with side-by-side speed comparison                                        |

---

## Submission Checklist

1. **Project Spec Document (PDF)** — Application scenarios, agent architecture diagram, core capabilities, model + local deployment plan, ROCm optimization description
2. **Project Source Code** — Complete repo with README (environment config, startup guide, dependency list)
3. **Demo Video** — 3-5 minutes showing actual operation on AMD Radeon GPU
4. **Supplementary Materials** — PPT or Poster
5. **PR to** `AMD-DEV-CONTEST/Radeon-hackathon-2026-07`

**Deadline**: August 6, 2026, 11:59 PM UTC+8 (~6 days)

---

## Further Considerations

1. **Model choice**: Llama 3.2 3B is fast but may miss subtle issues. Mistral 7B is smarter but slower. Test both on Day 1. The Radeon cloud API path (bonus) can use a larger model since it's not locally constrained.
2. **ROCm fallback**: If ROCm setup fails, CPU fallback via llama-cpp-python CPU build. You lose ROCm points but still have a working demo. Prioritize fixing ROCm.
3. **Demo script is critical**: The multi-turn conversation is the entire demo. Pre-script 4-5 turns that showcase: tool invocation (bandit output), RAG (code snippet retrieval), cross-review (agents disagreeing), memory (follow-up context), and ROCm benchmarks. Practice until it flows naturally.
4. **Privacy emphasis**: The track is about "Private AI Agents." Emphasize in your demo and spec doc that all code stays local, no data leaves the machine, ROCm enables on-device inference without cloud dependency.
