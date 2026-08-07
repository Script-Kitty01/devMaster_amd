#!/bin/bash
# =============================================================================
# Kutaar — Radeon Cloud Startup Script
# Runs on AMD OneClick Base (rocm7.2.1-py3.12) with Gradio App deploy type.
# Gradio uses HTTP polling (no WebSockets) — works behind all proxies.
# =============================================================================
set -e

echo "============================================"
echo "  Kutaar — Multi-Agent Engineering Assistant"
echo "  AMD ROCm + Radeon Cloud"
echo "============================================"

# ------------------------------------------------------------------
# 1. Install Python dependencies
# ------------------------------------------------------------------
echo "[1/3] Installing dependencies..."
# Try pre-built ROCm wheel first (fast), fall back to CPU-only (instant)
pip install llama-cpp-python \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/rocm \
    --quiet 2>/dev/null || \
pip install llama-cpp-python --quiet
# Install the rest of the project
pip install -e . --quiet

# ------------------------------------------------------------------
# 2. Download GGUF model from HuggingFace
# ------------------------------------------------------------------
MODEL_DIR="models"
MODEL_FILE="Llama-3.2-3B-Instruct-Q4_K_M.gguf"

if [ -f "${MODEL_DIR}/${MODEL_FILE}" ]; then
    echo "[2/3] Model already cached: ${MODEL_DIR}/${MODEL_FILE}"
else
    echo "[2/3] Downloading model (1.88 GB)..."
    mkdir -p "${MODEL_DIR}"
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    'unsloth/Llama-3.2-3B-Instruct-GGUF',
    '${MODEL_FILE}',
    local_dir='${MODEL_DIR}',
)
print('Download complete.')
"
fi

# ------------------------------------------------------------------
# 3. Launch Gradio (HTTP polling, no WebSockets needed)
# ------------------------------------------------------------------
echo "[3/3] Launching Kutaar Gradio UI on port 7860..."
exec python src/ui/gradio_app.py
