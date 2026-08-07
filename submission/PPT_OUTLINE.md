# Kutaar — PPT/Poster Outline

## Slide 1: Title
- **Kutaar** 🔥 — Your Private AI Engineering Team
- AMD AI DevMaster Hackathon 2026 — Track 2
- Team: Script-Kitty01

## Slide 2: The Problem
- Code review is slow, expensive, and inconsistent
- Cloud AI tools leak your source code
- Solo devs & small teams lack review bandwidth
- **Solution**: A private AI engineering team running locally on AMD Radeon

## Slide 3: What is Kutaar?
- Conversational multi-agent AI assistant
- 6 specialized agents working together
- 100% local on AMD Radeon GPU via ROCm
- Upload a repo → ask questions → get comprehensive review

## Slide 4: Agent Architecture
- Diagram: Planner → RAG → [Security, Perf, Arch, DevOps] → Consensus
- Each agent has specialized tools (Bandit, Semgrep, Git, Docker)
- Cross-review debate for higher accuracy
- LangGraph StateGraph with checkpointing

## Slide 5: Core Capabilities
- Multi-turn conversation with memory
- RAG-powered code retrieval (ChromaDB + ROCm embeddings)
- Tool invocation (static analysis, git history, docker validation)
- Multi-agent collaboration with consensus
- Quality scoring (0.0-1.0) for every finding

## Slide 6: GPU Optimization
- llama.cpp compiled with HIP/ROCm for gfx1100
- Q4_K_M quantization (4-bit, 2.6 GB VRAM)
- CUDA Graphs + MFMA instructions
- **124 tok/s** generation speed
- **15.5× faster** than CPU-only inference

## Slide 7: Demo Results
- Test repo with intentional vulnerabilities
- 30 findings: 3 critical, 8 high, 4 medium, 15 low
- Quality Score: 0.75
- End-to-end: "Find security vulnerabilities" → 10 findings, Quality 0.85

## Slide 8: Why AMD Radeon?
- Complete data privacy (no cloud)
- Consumer GPU accessible (4GB+ VRAM)
- ROCm ecosystem maturity
- Competitive inference speed (124 tok/s on 3B model)
- Cost-effective vs cloud API subscriptions

## Slide 9: Future Roadmap
- Multi-repo comparison
- Custom rule injection
- CI/CD integration (GitHub Actions)
- Fine-tuned models for code review
- VS Code extension

## Slide 10: Thank You
- GitHub: Script-Kitty01/devMaster_amd
- Live Demo: [Gradio URL]
- Built with ❤️ on AMD Radeon
