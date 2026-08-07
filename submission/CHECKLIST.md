# Kutaar — Hackathon Submission Checklist

## Track 2: Development & Local Deployment of Private AI Agents

### Required Deliverables

| # | Item | Status | File/Location |
|---|------|--------|---------------|
| 1 | **Project Spec Document (PDF)** | ✅ Markdown ready | `PROJECT_SPEC.md` → convert to PDF |
| 2 | **Source Code** | ✅ On GitHub | `Script-Kitty01/devMaster_amd` |
| 3 | **Demo Video (3-5 min)** | ✅ Recorded | https://drive.google.com/drive/folders/1PHfQT8CkQi6C3Jq6fY6C_3cnXVxyGfLl |
| 4 | **Supplementary (PPT/Poster)** | ✅ Outline ready | `submission/PPT_OUTLINE.md` → create PPT |

### Submission Steps

1. **Fork the hackathon repo**: `AMD-DEV-CONTEST/Radeon-hackathon-2026-07`
2. **Create a branch**: `track2-script-kitty01-kutaar`
3. **Add deliverables**:
   - `PROJECT_SPEC.pdf` (converted from `PROJECT_SPEC.md`)
   - Link to source code repo
   - Demo video: https://drive.google.com/drive/folders/1PHfQT8CkQi6C3Jq6fY6C_3cnXVxyGfLl
   - PPT/Poster file
4. **Open PR** with title: `Track 2, Script-Kitty01, Kutaar`

### Demo Video Script (3-5 min)

1. **Intro (30s)**: "Hi, I'm [name] from Team Script-Kitty01. This is Kutaar — a private multi-agent AI engineering assistant running entirely on AMD Radeon GPU."
2. **Architecture (45s)**: Show the agent diagram, explain the 6-agent system
3. **Live Demo (2min)**:
   - Launch Gradio UI
   - Index the sample repo
   - Ask: "Find all security vulnerabilities"
   - Show agents working (Planner → Security → Consensus)
   - Show findings with severity scores
   - Ask follow-up: "Tell me more about the SQL injection"
4. **GPU Performance (30s)**: Show `rocminfo`, VRAM usage, 124 tok/s benchmark
5. **Outro (15s)**: "Kutaar — your private AI engineering team on AMD Radeon. Thank you!"

### Notes

- Convert `PROJECT_SPEC.md` to PDF using: `pandoc PROJECT_SPEC.md -o submission/PROJECT_SPEC.pdf`
- Or use any Markdown-to-PDF converter (VS Code extension, browser print, etc.)
- Demo video can be recorded with OBS Studio
- PPT can be created from `submission/PPT_OUTLINE.md` using PowerPoint, Google Slides, or Canva
