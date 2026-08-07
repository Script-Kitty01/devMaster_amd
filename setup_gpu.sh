#!/bin/bash
# Kutaar GPU Setup — installs llama-cpp-python with ROCm/HIP BLAS
# Run once on AMD GPU instances (Radeon Cloud, etc.)
set -e

echo "=== Kutaar GPU Setup ==="
echo "Detecting GPU..."

# Detect GPU architecture
GPU_ARCH=$(rocminfo 2>/dev/null | grep -oP 'gfx\w+' | head -1)
if [ -z "$GPU_ARCH" ]; then
    echo "ERROR: No AMD GPU detected or ROCm not installed."
    echo "Install ROCm first: https://rocm.docs.amd.com/"
    exit 1
fi
echo "Detected GPU: $GPU_ARCH"

# Check ROCm version
HIP_VERSION=$(hipcc --version 2>/dev/null | grep -oP 'roc-\S+' | head -1 || echo "unknown")
echo "ROCm/HIP: $HIP_VERSION"

echo ""
echo "Installing llama-cpp-python with HIP BLAS for $GPU_ARCH..."
echo "This compiles C++ HIP kernels — may take 5-10 minutes."
echo ""

pip install llama-cpp-python --force-reinstall --no-cache-dir --break-system-packages \
    -C cmake.args="-DGGML_HIPBLAS=on;-DCMAKE_C_COMPILER=/opt/rocm/bin/hipcc;-DCMAKE_CXX_COMPILER=/opt/rocm/bin/hipcc;-DAMDGPU_TARGETS=$GPU_ARCH"

echo ""
echo "=== Verifying GPU Inference ==="
python3 -c "
from llama_cpp import Llama
import time, os

# Find model
import subprocess
r = subprocess.run(['find', '/workspace', '-name', '*.gguf', '-type', 'f'], capture_output=True, text=True, timeout=30)
model_path = r.stdout.strip().split(chr(10))[0] if r.stdout.strip() else ''

if not model_path:
    print('No GGUF model found. Download one first:')
    print('  python3 -c \"from huggingface_hub import hf_hub_download; hf_hub_download(repo_id=\\\"bartowski/Llama-3.2-3B-Instruct-GGUF\\\", filename=\\\"Llama-3.2-3B-Instruct-Q4_K_M.gguf\\\", local_dir=\\\"./models\\\")\"')
    exit(0)

print(f'Model: {model_path}')
print(f'Size: {os.path.getsize(model_path)/1e9:.2f} GB')

t0 = time.time()
llm = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=2048, n_batch=512, verbose=False)
print(f'Loaded in {time.time()-t0:.1f}s')

_ = llm('Hello', max_tokens=5)  # warmup

t0 = time.time()
r = llm('Explain what a GPU is in one paragraph.', max_tokens=100)
elapsed = time.time() - t0
tok = r['usage']['completion_tokens']
print(f'GPU Inference: {tok} tokens in {elapsed:.2f}s = {tok/elapsed:.1f} tok/s')
print('GPU SETUP COMPLETE!')
"
