# ROCm Migration Plan

## Objective

Move Kutaar's primary inference path from the current Windows/Ollama setup to native AMD ROCm/HIP inference through `llama-cpp-python`, while preserving a working CPU/Ollama fallback for development and recovery.

## Verified Starting State

- Host: Windows with a project virtual environment at `.venv`.
- Current default: `LLMConfig.backend = "ollama"` and model `gemma2:2b`.
- Current UI responses come from Ollama, not the in-process HIP backend.
- Installed PyTorch is CPU-only: no HIP runtime or AMD device is exposed.
- `llama_cpp` is installed, but its Windows native library cannot load.
- ROCm tools (`rocminfo`, `rocm-smi`, `hipcc`) are unavailable on this host.
- The repository already contains Linux build scripts targeting `gfx1100`, including `GGML_HIP=ON` builds.

## Target Architecture

```text
Streamlit/Gradio
        |
        v
ROCmLLM(backend="llama_cpp")
        |
        v
llama-cpp-python with GGML_HIP=ON
        |
        v
AMD ROCm runtime + HIP + hipBLAS
        |
        v
AMD Radeon GPU
```

Ollama remains available only as an explicit fallback:

```text
ROCm unavailable -> backend="ollama" -> local Ollama service
```

## Platform Decision

Do not attempt to make the current Windows environment the ROCm build target. The supported migration target is a Linux ROCm machine or container with a compatible AMD GPU. The existing remote Radeon environment is the preferred build and validation host. Windows remains useful for UI development and fallback testing.

## Phase 0: Freeze and Baseline

1. Record the current commit and Python dependency state.
2. Keep Ollama smoke coverage working:
   - `/api/tags` sees the configured model.
   - A short prompt returns non-empty text.
   - Gradio indexes `demo_repos/fastapi_service` and returns an answer.
3. Record CPU/Ollama latency, tokens per second, and response correctness.
4. Do not remove the Ollama path until the ROCm acceptance gate passes.

**Gate:** the fallback UI and focused tests pass before migration begins.

## Phase 1: Provision and Verify the ROCm Host

1. Use a Linux host with the intended AMD GPU and a supported ROCm release.
2. Create a clean Python 3.12 virtual environment.
3. Install project dependencies without replacing the ROCm build with a generic prebuilt `llama-cpp-python` wheel.
4. Verify the host before building:

```bash
rocminfo
rocm-smi
hipcc --version
python -c "import torch; print(torch.version.hip, torch.cuda.is_available())"
```

5. Record the GPU architecture from `rocminfo`. Use that value for `AMDGPU_TARGETS`; do not assume `gfx1100` unless the host reports it.

**Gate:** `rocminfo` detects the GPU, `rocm-smi` reports it, and the Python environment exposes the ROCm device.

## Phase 2: Build HIP-Enabled llama.cpp

1. Build from source in an isolated directory using the vendored llama.cpp source shipped with `llama-cpp-python` or a pinned source checkout.
2. Use the current llama.cpp option names:

```bash
cmake .. \
  -DGGML_HIP=ON \
  -DAMDGPU_TARGETS=<reported-gpu-arch> \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_SERVER=OFF
cmake --build . --config Release --target ggml llama -j"$(nproc)"
```

3. Install or copy the complete matching shared-library set into the active `llama_cpp/lib` directory, including `libggml-base.so*`, `libggml-cpu.so*`, `libggml-hip.so*`, `libggml.so*`, and `libllama.so*`.
4. Pin the resulting package/build metadata so a later `pip install` cannot silently replace it with a CPU wheel.

**Gate:**

```bash
strings <venv>/lib/python*/site-packages/llama_cpp/lib/libggml-hip.so | grep -i hipblas
nm -D <venv>/lib/python*/site-packages/llama_cpp/lib/libggml-hip.so | grep -i hip
```

Both checks must show HIP symbols, and `import llama_cpp` must succeed.

## Phase 3: Make Backend Selection Explicit

1. Update `LLMConfig` so backend selection is controlled by an environment variable or CLI setting:
   - `KUTAAR_LLM_BACKEND=llama_cpp` for ROCm.
   - `KUTAAR_LLM_BACKEND=ollama` for fallback.
2. Add an explicit model path setting for a GGUF file on the ROCm host.
3. Do not label the backend as ROCm merely because the class is named `ROCmLLM`; report the verified runtime backend.
4. On `backend="llama_cpp"`, fail clearly if the model file or native library is missing. Only fall back to CPU/Ollama when the user explicitly enables fallback behavior.
5. Preserve the existing Ollama health check and response path.
6. Add a runtime diagnostic containing the selected backend, model path/name, GPU offload layer count, detected GPU/runtime, and fallback reason if any.

**Gate:** startup reports `ROCm/HIP` only when the llama.cpp GPU backend is actually loaded; CPU and Ollama states are visibly distinct.

## Phase 4: ROCm Embeddings

1. Choose an embedding model available on the ROCm host and pin its version.
2. Confirm the embedding model uses the ROCm device rather than silently using CPU.
3. Keep deterministic fallback embeddings only for unavailable-model development mode; never describe them as GPU embeddings.
4. Rebuild the Chroma index after switching embedding models. Do not reuse an index created with a different embedding dimension/model without a reset.

**Gate:** indexing the FastAPI fixture succeeds, Chroma query returns snippets, and GPU memory/utilization changes during embedding or inference.

## Phase 5: Application Integration

1. Add a ROCm configuration example to the README and startup commands.
2. Update Streamlit and Gradio status panels to show the actual backend.
3. Ensure both UIs use the same `ROCmLLM` configuration source.
4. Keep the current bounded interactive workflow: no redundant planner generation, no debate round for the default fast response path, and clear error text on failed inference.
5. Add tests for backend selection, missing model behavior, and non-empty response handling.

## Phase 6: End-to-End Validation

Run these checks on the ROCm host:

1. Direct inference:

```bash
KUTAAR_LLM_BACKEND=llama_cpp python -c "from src.llm.rocm_service import ROCmLLM; llm=ROCmLLM.get_instance(); print(llm.generate('Reply with exactly: rocm smoke', max_tokens=16))"
```

2. Verify output/log evidence includes a ROCm backend and GPU offload.
3. Confirm `rocm-smi` shows model VRAM usage while the model is loaded.
4. Index `demo_repos/fastapi_service`.
5. Send `Find security vulnerabilities in this codebase` through Gradio.
6. Verify the UI displays a non-empty assistant response, findings, the actual ROCm backend, and no CPU/Ollama fallback warning.
7. Repeat the smoke path in Streamlit.
8. Run focused tests and the complete maintained test suite.
9. Compare ROCm latency/tokens-per-second with the Phase 0 baseline.

**Definition of Done:** both UIs complete the fixture analysis using `llama-cpp-python` with HIP/ROCm, GPU memory is observed during inference, the backend status is truthful, and Ollama remains a tested fallback.

## Rollback Plan

1. Set `KUTAAR_LLM_BACKEND=ollama`.
2. Restore the known working Ollama model and URL.
3. Leave HIP build artifacts isolated from the fallback environment.
4. Re-run the Phase 0 smoke checks.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Windows host cannot provide ROCm runtime | Build and run inference on Linux ROCm host; keep Windows as fallback UI host. |
| Generic wheel replaces HIP build | Pin the source build and verify HIP symbols after installation. |
| Wrong GPU architecture target | Read `rocminfo` and configure the reported target. |
| Embedding model downloads or falls back silently | Use local-only loading, explicit device checks, and visible fallback status. |
| LLM output is truncated or invalid JSON | Bound prompts/tokens, tolerate malformed findings, and always render a response. |
| ROCm model is too slow for interactive use | Use a small quantized GGUF, tune `n_ctx`/`n_batch`, and benchmark before enabling larger models. |
