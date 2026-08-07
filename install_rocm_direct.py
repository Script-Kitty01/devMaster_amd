"""
Try downloading pre-built ROCm wheel directly from GitHub releases.
"""
import subprocess, sys, os

# First, check what Python version and platform we need
result = subprocess.run([sys.executable, '-c', 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}"); print(sys.platform)'], capture_output=True, text=True)
lines = result.stdout.strip().split('\n')
cp_tag = lines[0]
platform = lines[1]
print(f"Python: {cp_tag}, Platform: {platform}")

# Check ROCm version
result = subprocess.run(['apt-cache', 'policy', 'rocm-core'], capture_output=True, text=True)
print(f"ROCm core: {result.stdout.strip()}")

# Try to find pre-built wheels
# The wheel naming convention is: llama_cpp_python-{version}-{cp_tag}-{cp_tag}-{platform}.whl
# For ROCm: llama_cpp_python-{version}-{cp_tag}-{cp_tag}-manylinux_2_28_x86_64.whl

# Let's try pip install with the direct wheel URL from GitHub
# First check if there's a wheel for our version
print("\n=== Trying direct wheel download from GitHub releases ===")

# Try the latest release
wheel_urls = [
    f"https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.34/llama_cpp_python-0.3.34-{cp_tag}-{cp_tag}-manylinux_2_28_x86_64.whl",
    f"https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.33/llama_cpp_python-0.3.33-{cp_tag}-{cp_tag}-manylinux_2_28_x86_64.whl",
]

for url in wheel_urls:
    print(f"\nTrying: {url}")
    result = subprocess.run([sys.executable, '-m', 'pip', 'install', url, '--no-deps'], capture_output=True, text=True, timeout=60)
    print(result.stdout[-1000:])
    if result.returncode == 0:
        print("SUCCESS!")
        break
    else:
        print(f"Failed: {result.stderr[-500:]}")

# Check if we got HIPBLAS
print("\n=== Checking for HIPBLAS libs ===")
result = subprocess.run(['find', '/opt/venv/lib/python3.12/site-packages', '-name', '*hipblas*', '-o', '-name', '*rocm*'], capture_output=True, text=True)
print(result.stdout if result.stdout else "No HIPBLAS/ROCm libs found")

# Also check the llama_cpp lib dir
result = subprocess.run(['find', '/opt/venv/lib/python3.12/site-packages/llama_cpp', '-name', '*.so*'], capture_output=True, text=True)
print("\nllama_cpp libs:")
print(result.stdout)
