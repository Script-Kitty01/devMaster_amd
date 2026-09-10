# Quick Start: Next Phase (Remote ROCm Verification & Build)

## Current Status
✅ All locally actionable phases complete (Phases 0-5)
✅ All 11 tests passing
✅ Baseline captured
✅ Helper scripts ready

## What's Next?

You need to execute **Phases 1-2** on the remote ROCm host:
- **Phase 1**: Verify the host has ROCm, hipcc, proper GPU
- **Phase 2**: Build llama-cpp-python with GGML_HIP=ON

## Quick Execution Steps

### Step 1: SSH to Remote Host
```powershell
# From Windows, connect to the remote Radeon machine
ssh user@u-14073-bcd85560.radeon-global.anruicloud.com
# Or use the Anrui web terminal at:
# https://radeon-global.anruicloud.com/instances/u-14073-bcd85560
```

### Step 2: Verify ROCm Host
```bash
# On the remote host, run:
cd /path/to/devmaster  # Clone the repo if needed
python3 scripts/verify_rocm_host.py

# Expected output: JSON with rocminfo, rocm-smi, hipcc checks all passing
# Look for: "suggested_amdgpu_targets" - should include gfx1100
```

### Step 3: Build HIP-Enabled llama-cpp-python
```bash
# On the remote host:
export AMDGPU_TARGETS=gfx1100  # Use value from verify_rocm_host.py output
bash scripts/build_llama_cpp_hip.sh

# This will:
# 1. Install pip, setuptools, cmake, ninja
# 2. Clone llama-cpp-python v0.3.34
# 3. Build with GGML_HIP=ON
# 4. Verify HIP symbols in libggml-hip.so
# 5. Show build.log output

# Expected time: 10-30 minutes depending on GPU
```

### Step 4: Validate Build Success
After build completes, verify:
```bash
# Check for HIP library
ls -la /opt/venv/lib/python3.12/site-packages/llama_cpp/lib/libggml-hip.so*

# Check for HIP symbols
strings /opt/venv/lib/python3.12/site-packages/llama_cpp/lib/libggml-hip.so | grep hipblas

# Check for HIP kernels
nm -D /opt/venv/lib/python3.12/site-packages/llama_cpp/lib/libggml-hip.so | grep -i hip
```

### Step 5: Smoke Test
Once build is verified:
```bash
# On remote host
source /opt/venv/bin/activate
export KUTAAR_LLM_BACKEND=llama_cpp
export KUTAAR_MODEL=/path/to/your/model.gguf
python3 -c "
from src.llm.rocm_service import ROCmLLM
llm = ROCmLLM.get_instance()
llm.initialize()
print(f'Backend: {llm.backend}')
print(f'Ready: {llm.is_ready}')
diag = llm.diagnostics()
print(f'Active backend: {diag[\"active_backend\"]}')
print(f'Embedding device: {diag[\"embedding_device\"]}')
"

# Expected output:
# Backend: rocm
# Ready: True
# Active backend: rocm
# Embedding device: cuda
```

## Troubleshooting

### Build Fails with CMake Error
- Check rocminfo output: `rocminfo`
- Ensure ROCm 7.2+ is installed
- Try with specific AMDGPU_TARGETS from rocminfo

### libggml-hip.so Not Found
- Check build.log for errors
- Ensure cmake configured with GGML_HIP=ON
- Verify ninja/cmake builds completed successfully

### HIP Symbols Not Found
- This means the build didn't actually use HIP
- Re-run with explicit environment setup:
```bash
unset CMAKE_ARGS  # Clear any old settings
export CMAKE_ARGS="-DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100 ..."
bash scripts/build_llama_cpp_hip.sh
```

### GPU Not Detected After Build
- Run `rocm-smi` to verify GPU is visible to ROCm
- Try: `python3 -c "import torch; print(torch.cuda.is_available())"`
- If still false, ROCm/HIP not properly installed on host

## Files You'll Need

On the remote host, ensure you have:
- `scripts/verify_rocm_host.py` - verification script
- `scripts/build_llama_cpp_hip.sh` - build script
- `src/llm/rocm_service.py` - LLM service with diagnostics
- A GGUF model file (e.g., `models/model.gguf`)
- Python 3.12 in `/opt/venv/`

## Post-Build: Phase 6 Validation

After successful build, run on remote host:
```bash
# Full Gradio smoke test
python3 src/ui/gradio_app.py &  # Start in background

# In another terminal:
# 1. Navigate to http://localhost:7860
# 2. Index demo_repos/fastapi_service
# 3. Send: "Find security vulnerabilities"
# 4. Verify non-empty response, ROCm backend shown
# 5. Check rocm-smi for VRAM usage during inference
```

## Quick Reference

| Command | Purpose |
|---------|---------|
| `python3 scripts/verify_rocm_host.py` | Check if host is ready |
| `bash scripts/build_llama_cpp_hip.sh` | Build HIP version |
| `rocminfo` | Verify GPU and ROCm |
| `rocm-smi` | Check GPU memory usage |
| `hipcc --version` | Verify HIP compiler |

## Success Indicators

✅ Phase 1: rocminfo detects GPU, hipcc available, target arch identified
✅ Phase 2: build.log shows "Build complete", libggml-hip.so exists, HIP symbols found
✅ Phase 6: Gradio loads model, rocm-smi shows VRAM usage, backend shows "rocm" in UI

---

**Next**: Execute the verification script on the remote host!

For detailed implementation info, see: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
For full migration plan, see: [plan.md](plan.md)
