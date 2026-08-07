# 🎬 Kutaar Hackathon Recording Guide

## ⚡ QUICK START — When You're Ready to Record

### 1. Start the Gradio App (in JupyterLab terminal)

```bash
cd /workspace/template-repos/template-1005/repo
python src/ui/gradio_app.py
```

The app will be at: `http://localhost:7860`

### 2. Open the UI in your browser

Navigate to the Gradio app. The repo is already pre-indexed and the model is loaded.

### 3. Start Recording

- **Windows Game Bar**: Press `Win + Alt + R` (easiest, no setup)
- **OBS Studio**: Better quality, allows webcam overlay

### 4. Follow the script below ⬇️

---

## 🎯 DEMO SCRIPT (5 minutes)

### SCENE 1: INTRO (30 seconds)

> **Say:** "Hi, I'm [name] from Team Script-Kitty01. This is Kutaar — a 6-agent AI engineering assistant that analyzes code for security vulnerabilities, performance issues, and architecture problems. It runs entirely on AMD ROCm — zero NVIDIA dependency."

**Show on screen:** The Gradio UI with the title "Kutaar — AMD ROCm Engineering Assistant"

---

### SCENE 2: GPU BENCHMARK PROOF (30 seconds)

> **Say:** "First, let me prove this is running on AMD hardware. We benchmarked Llama 3.2 3B on this Radeon instance and got 10.0 tokens per second — all layers on GPU via HIP BLAS. No CUDA, no NVIDIA."

**Show on screen:** The benchmark results:

```
GPU: AMD Radeon Graphics gfx1100
Backend: ROCm 7.2.1 + HIP BLAS
Speed: 10.0 tok/s
Load: 1.6s
Status: ZERO NVIDIA DEPENDENCY
```

---

### SCENE 3: LIVE DEMO — The Query (1 minute)

> **Say:** "Let me show you it working. I've pre-loaded a sample app with intentional vulnerabilities — hardcoded passwords, SQL injection, command injection, path traversal. Let's ask Kutaar to find them."

**Action:** Type into the chat box:

```
Find security vulnerabilities in this codebase
```

Press Enter.

> **Say (while it runs):** "Behind the scenes, 6 agents are running. The Planner decomposes my question. Then 4 specialist agents — Security, Performance, Architecture, and DevOps — run in parallel. Finally, a Consensus agent runs a 2-round debate to reduce false positives."

---

### SCENE 4: LIVE DEMO — The Results (1.5 minutes)

> **Say:** "Here are the results. Kutaar found [X] findings across all agents."

**Action:** Scroll through the results. Point out:

1. **Critical findings** — hardcoded passwords, SQL injection
2. **High findings** — command injection, path traversal
3. **The agent breakdown** — Security found X, DevOps found Y, etc.
4. **The debate rounds** — "2 rounds of cross-review debate"
5. **The consensus score** — quality metric

> **Say:** "Each finding includes the file path, line number, severity, a description, and a fix recommendation. The debate system means agents cross-check each other's work — reducing false positives from the small 3B model."

---

### SCENE 5: ARCHITECTURE WALKTHROUGH (1 minute)

> **Say:** "Here's how it works under the hood."

**Show:** The architecture diagram or explain:

```
User Query
    ↓
  Planner (decomposes question)
    ↓
  ┌─────┬─────┬─────┬─────┐  (parallel)
  │ Sec │ Perf│ Arch│ Dev │
  └─────┴─────┴─────┴─────┘
    ↓         ↓
  Consensus (2-round debate)
    ↓
  Final Verdict + Action Items
```

> **Say:** "Built with LangGraph for the agent orchestration, ChromaDB for code indexing, and llama-cpp-python with HIP BLAS for GPU inference. All running on AMD ROCm."

---

### SCENE 6: WHY THIS WINS (1 minute)

> **Say:** "Here's why Kutaar stands out for the AMD AI DevMaster Hackathon:"

| Point                | What to Say                                                                  |
| -------------------- | ---------------------------------------------------------------------------- |
| **AMD-Native**       | "100% AMD stack — ROCm, HIP BLAS, Radeon GPU. Zero lines of CUDA."           |
| **Multi-Agent**      | "6 specialized agents with parallel execution and debate-based consensus."   |
| **Real Results**     | "Found [X] findings including critical vulnerabilities from a single query." |
| **Production-Ready** | "Thread-safe, graceful degradation, works on any AMD GPU."                   |
| **Open Source**      | "Everything is on GitHub at Script-Kitty01/devMaster_amd"                    |

---

### SCENE 7: OUTRO (15 seconds)

> **Say:** "Thank you for watching. Kutaar — making AI-powered code review accessible on AMD hardware. Repo link is in the description."

---

## 🎥 RECORDING SETUP

### Option A: Windows Game Bar (Easiest)

1. Press `Win + G` to open Game Bar
2. Click the record button (or `Win + Alt + R`)
3. Record your screen
4. Press `Win + Alt + R` again to stop
5. File saved to: `Videos/Captures/`

### Option B: OBS Studio (Best Quality)

1. Download from https://obsproject.com/
2. Add "Display Capture" as source
3. Optional: Add "Video Capture Device" for webcam
4. Click "Start Recording"

### Option C: Loom (Browser-based, webcam bubble)

1. Go to https://loom.com
2. Install Chrome extension
3. Select "Screen + Cam"
4. Record (free tier: 5 min)

---

## ✅ PRE-FLIGHT CHECKLIST

Before hitting record:

- [ ] Gradio app is running at `http://localhost:7860`
- [ ] Model is loaded (the warmup script did this)
- [ ] Demo repo is indexed (8 chunks from 6 files)
- [ ] Pipeline is warm (sample query already ran)
- [ ] Close unnecessary tabs and apps
- [ ] Turn off notifications (Focus Assist → Alarms Only)
- [ ] Have water nearby
- [ ] Test microphone (if using voiceover)

---

## 🏆 KEY TALKING POINTS (Memorize These)

1. **"Zero NVIDIA dependency"** — This is THE differentiator for AMD hackathon
2. **"10.0 tok/s on ROCm"** — Concrete performance number
3. **"6 agents, 2-round debate"** — Shows sophistication
4. **"Found [X] findings from one query"** — Real results
5. **"AMD Radeon gfx1100 + ROCm 7.2.1"** — Specific hardware

---

## ⚠️ TROUBLESHOOTING

| Problem               | Fix                                                 |
| --------------------- | --------------------------------------------------- |
| Gradio not responding | Restart: `python src/ui/gradio_app.py`              |
| Model not loaded      | Run warmup script again                             |
| Slow inference        | Normal — 10 tok/s is expected for 3B model          |
| Error in chat         | Just retry — the pipeline handles errors gracefully |
