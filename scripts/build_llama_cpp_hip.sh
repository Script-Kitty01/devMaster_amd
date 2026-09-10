#!/usr/bin/env bash
# Phase 2 — Build llama-cpp-python with HIP/ROCm on a Linux host.
# Run after scripts/verify_rocm_host.py reports success.
# Assumes: python3 venv, ROCm installed, git-lfs optional.

set -euo pipefail

: "${AMDGPU_TARGETS:=gfx1100}"
: "${PYTHON:=python3}"
: "${VENV_DIR:=/opt/venv}"
: "${LLAMA_VERSION:=v0.3.34}"

export CMAKE_ARGS="-DGGML_HIP=ON -DAMDGPU_TARGETS=${AMDGPU_TARGETS} -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=OFF"

echo "=== Building llama-cpp-python ${LLAMA_VERSION} with HIP ==="
echo "AMDGPU_TARGETS=${AMDGPU_TARGETS}"
echo "CMAKE_ARGS=${CMAKE_ARGS}"

if [[ -f "${VENV_DIR}/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "${VENV_DIR}/bin/activate"
fi

# Ensure pip/setuptools/build up to date
python -m pip install --upgrade pip setuptools scikit-build-core cmake ninja wheel

BUILD_DIR="$(mktemp -d)"
cd "${BUILD_DIR}"

git clone --depth 1 --branch "${LLAMA_VERSION}" https://github.com/abetancord/llama-cpp-python.git

cd llama-cpp-python
# scikit-build-core ignores CMAKE_ARGS; pass via environment that the build reads.
python -m pip install . --no-build-isolation -v 2>&1 | tee build.log

echo "=== Verify HIP symbols in libggml-hip.so ==="
PYTHON_SITE="$(python -c 'import site; print(site.getsitepackages()[0])')"
LIB_DIR="${PYTHON_SITE}/llama_cpp/lib"
if [[ -f "${LIB_DIR}/libggml-hip.so" ]]; then
    echo "Found ${LIB_DIR}/libggml-hip.so"
    strings "${LIB_DIR}/libggml-hip.so" | grep -m1 hipblas || echo "WARNING: hipblas symbols not found"
    nm -D "${LIB_DIR}/libggml-hip.so" | grep -i hip | head -n 5 || echo "WARNING: HIP kernel symbols not found"
else
    echo "WARNING: libggml-hip.so not present in ${LIB_DIR}"
fi

echo "=== Build complete ==="
