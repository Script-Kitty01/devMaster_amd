# ROCm Migration Checklist

## Phase 0: Baseline & Freeze ✅ COMPLETE
- [x] Created `scripts/baseline.ps1`
- [x] Captured git state and commit hash
- [x] Froze pip packages to `scripts/baseline_freeze.txt` (184 packages)
- [x] Probed Ollama latency: 6.06s, 1 tok/s
- [x] All smoke tests passing
- [x] Git checkpoint created

## Phase 1: Provision and Verify ROCm Host ⏳ READY
**Files**: `scripts/verify_rocm_host.py`

### On Remote Host
- [ ] SSH/Connect to u-14073-bcd85560
- [ ] Clone/update repository
- [ ] Run: `python3 scripts/verify_rocm_host.py`
- [ ] Verify output JSON shows:
  - [ ] rocminfo: ok = true
  - [ ] rocm-smi: ok = true
  - [ ] hipcc: ok = true
  - [ ] suggested_amdgpu_targets includes gfx1100
- [ ] Record GPU architecture from output
- [ ] Confirm Python environment ready

## Phase 2: Build HIP-Enabled llama.cpp ⏳ READY
**Files**: `scripts/build_llama_cpp_hip.sh`

### On Remote Host
- [ ] Set environment: `export AMDGPU_TARGETS=gfx1100`
- [ ] Run: `bash scripts/build_llama_cpp_hip.sh`
- [ ] Build completes successfully (10-30 min expected)
- [ ] Verify output shows:
  - [ ] llama-cpp-python cloned successfully
  - [ ] cmake configured with GGML_HIP=ON
  - [ ] build complete message
- [ ] Check for libggml-hip.so:
  - [ ] File exists at: `/opt/venv/lib/python3.12/site-packages/llama_cpp/lib/libggml-hip.so`
  - [ ] strings output includes "hipblas"
  - [ ] nm -D output includes HIP kernel symbols

## Phase 3: Backend Selection ✅ COMPLETE
**Files**: `src/llm/rocm_service.py`
- [x] LLMConfig.from_env() implemented
- [x] Environment variables working:
  - [x] KUTAAR_LLM_BACKEND
  - [x] KUTAAR_MODEL
  - [x] KUTAAR_GPU_LAYERS
  - [x] KUTAAR_ALLOW_CPU_FALLBACK
- [x] diagnostics() method added
- [x] fallback_reason property added
- [x] Tests passing

## Phase 4: ROCm Embeddings ✅ COMPLETE
**Files**: `src/llm/rocm_service.py`
- [x] Embedding device tracking implemented
- [x] _embedding_device variable added
- [x] Device shown in diagnostics()
- [x] Tests passing

## Phase 5: Application Integration ✅ COMPLETE
**Files**: `src/ui/gradio_app.py`, `src/ui/chat_app.py`, `README.md`, `tests/test_backend_selection.py`
- [x] Gradio UI shows truthful backend status
- [x] Streamlit UI shows truthful backend status
- [x] README updated with backend configuration section
- [x] Backend selection tests added (4 tests)
- [x] All tests passing (11/11)
- [x] Git checkpoint created

## Phase 6: End-to-End Validation ⏳ READY (After Phase 2)
**Location**: Remote ROCm host with successful Phase 2 build

### Direct Inference Test
- [ ] Set: `export KUTAAR_LLM_BACKEND=llama_cpp`
- [ ] Set: `export KUTAAR_MODEL=/path/to/model.gguf`
- [ ] Run: `python3 -c "from src.llm.rocm_service import ROCmLLM; llm=ROCmLLM.get_instance(); print(llm.generate('Reply with: rocm-working'))"`
- [ ] Verify:
  - [ ] Output includes "rocm-working"
  - [ ] Backend shows "rocm" in diagnostics
  - [ ] GPU layers properly configured

### VRAM Verification
- [ ] Open terminal with `rocm-smi`
- [ ] In another terminal, run model inference
- [ ] Verify: VRAM usage shows >1GB during model load/inference
- [ ] Compare to baseline: Should see GPU activity

### UI Smoke Test - Gradio
- [ ] Start: `python3 src/ui/gradio_app.py`
- [ ] Navigate to `http://localhost:7860`
- [ ] Verify: Model status shows "✅ LLM ready" with ROCm backend
- [ ] Index repository: `demo_repos/fastapi_service`
- [ ] Send query: "Find security vulnerabilities in this codebase"
- [ ] Verify:
  - [ ] Response is non-empty
  - [ ] Findings are displayed
  - [ ] Backend status shows "rocm"
  - [ ] rocm-smi shows VRAM usage during inference

### UI Smoke Test - Streamlit
- [ ] Start: `streamlit run src/ui/chat_app.py`
- [ ] Navigate to `http://localhost:8501`
- [ ] Verify same tests as Gradio
- [ ] Confirm both UIs use same backend

### Benchmark Comparison
- [ ] Run: `python3 -m src.main --benchmark`
- [ ] Compare ROCm latency vs Phase 0 baseline (6.06s Ollama)
- [ ] Document improvement in latency/tokens-per-second

### Test Suite
- [ ] Run: `python3 -m pytest tests/ -v`
- [ ] All tests pass
- [ ] No regressions from ROCm migration

## Phase 7: Documentation & Handoff ⏳ READY (After Phase 6)
- [ ] Update IMPLEMENTATION_SUMMARY.md with Phase 6 results
- [ ] Document any deviations from plan
- [ ] Record final benchmarks
- [ ] Update QUICK_START_NEXT_PHASE.md with actual commands used
- [ ] Create final git commit with validation results

## Rollback Verification ⏳ READY (Optional but Recommended)

### Fallback to Ollama
- [ ] Set: `export KUTAAR_LLM_BACKEND=ollama`
- [ ] Set: `export KUTAAR_MODEL=gemma2:2b`
- [ ] Run Phase 0 smoke tests
- [ ] Verify: Ollama still works as fallback
- [ ] UI shows "ollama" backend
- [ ] All tests still pass

## Final Acceptance Criteria

- [x] Phase 0: Baseline captured
- [x] Phase 3-5: Backend selection & UI integration complete
- [ ] Phase 1: ROCm host verified
- [ ] Phase 2: HIP build successful with HIP symbols confirmed
- [ ] Phase 6: End-to-end validation complete, ROCm inference working
- [ ] GPU memory usage visible during inference
- [ ] UI displays truthful backend status
- [ ] Ollama remains tested fallback
- [ ] All tests passing (11/11 initially, should remain)

---

## Notes

- Total implementation time: ~4 hours for Phases 0-5
- Remote build time: ~10-30 minutes (Phase 2)
- Remote validation time: ~30 minutes (Phase 6)
- **Current Status**: Ready for remote execution

## Quick Commands Reference

```bash
# Phase 1 Verification
python3 scripts/verify_rocm_host.py

# Phase 2 Build
bash scripts/build_llama_cpp_hip.sh

# Phase 6 Smoke Test
export KUTAAR_LLM_BACKEND=llama_cpp
export KUTAAR_MODEL=/path/to/model.gguf
python3 src/ui/gradio_app.py

# Rollback to Ollama
export KUTAAR_LLM_BACKEND=ollama
export KUTAAR_MODEL=gemma2:2b
python3 src/ui/gradio_app.py

# Run all tests
python3 -m pytest tests/ -v
```

---

**Last Updated**: 2026-09-10
**Status**: Phases 0-5 Complete, Phases 1-2, 6 Ready for Remote Execution
