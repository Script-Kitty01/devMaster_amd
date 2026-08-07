"""
Build the vendored llama.cpp directly with HIPBLAS, then copy .so files into llama-cpp-python.
This bypasses scikit-build-core entirely.
"""
import requests, json, time, uuid, urllib3
from websocket import create_connection
urllib3.disable_warnings()

BASE = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
TOKEN = 'amd-oneclick'

r = requests.post(f'{BASE}/api/kernels', headers={'Authorization': f'token {TOKEN}'}, verify=False)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token={TOKEN}'
ws = create_connection(ws_url, timeout=900)
msg = json.loads(ws.recv())

code = """
import subprocess, sys, os, shutil

# The vendored llama.cpp is at /tmp/llama_cpp_python_src/vendor/llama.cpp/
LLAMA_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp'
BUILD_DIR = f'{LLAMA_DIR}/build_hipblas'

# Step 1: Clean and configure cmake with HIPBLAS
print("=== Step 1: Configuring cmake with HIPBLAS ===")
os.makedirs(BUILD_DIR, exist_ok=True)

result = subprocess.run(
    f'cd {BUILD_DIR} && cmake .. '
    '-DGGML_HIPBLAS=ON '
    '-DAMDGPU_TARGETS=gfx1100 '
    '-DCMAKE_BUILD_TYPE=Release '
    '-DBUILD_SHARED_LIBS=ON '
    '2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)
print(result.stdout[-3000:])
if result.stderr:
    # Filter out routine warnings
    stderr_lines = [l for l in result.stderr.split('\\n') if 'Warning' not in l or 'HIP' in l or 'hipblas' in l.lower()]
    if stderr_lines:
        print("STDERR (filtered):", '\\n'.join(stderr_lines[-20:]))

if result.returncode != 0:
    print(f"CMAKE FAILED (rc={result.returncode})")
    sys.exit(1)

# Check for HIPBLAS in cmake output
if 'GGML_HIPBLAS' in result.stdout or 'hipblas' in result.stdout.lower():
    print("\\n*** HIPBLAS DETECTED in cmake output! ***")
else:
    print("\\nWARNING: HIPBLAS not in cmake output - checking config...")
    # Check cmake cache
    result2 = subprocess.run(
        f'grep -i hipblas {BUILD_DIR}/CMakeCache.txt 2>/dev/null || echo "No CMakeCache"',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print(result2.stdout[:500])

# Step 2: Build
print("\\n=== Step 2: Building (this will take several minutes) ===")
result = subprocess.run(
    f'cd {BUILD_DIR} && cmake --build . --config Release -j$(nproc) 2>&1 | tail -60',
    shell=True, capture_output=True, text=True, timeout=600, executable='/bin/bash'
)
print(result.stdout[-3000:])
print(f"Build RC: {result.returncode}")

if result.returncode != 0:
    print("BUILD FAILED")
    sys.exit(1)

# Step 3: Find built HIPBLAS libs
print("\\n=== Step 3: Finding HIPBLAS libs ===")
result = subprocess.run(
    f'find {BUILD_DIR} -name "*.so" -type f 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("All built .so files:")
print(result.stdout)

# Check for hipblas specifically
result = subprocess.run(
    f'find {BUILD_DIR} -name "*hipblas*" -o -name "*HIP*" 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print(f"HIPBLAS files: {result.stdout if result.stdout.strip() else 'NONE'}")

# Check symbols
result = subprocess.run(
    f'for f in $(find {BUILD_DIR} -name "*.so" -type f); do echo "=== $f ==="; nm -D "$f" 2>/dev/null | grep -i hip | head -5; done',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("\\nHIP symbols in libs:")
print(result.stdout[:2000])

# Step 4: Copy HIPBLAS libs into llama-cpp-python
print("\\n=== Step 4: Installing HIPBLAS libs ===")
# Find the llama-cpp-python lib directory
result = subprocess.run(
    'python3.12 -c "import llama_cpp; import os; print(os.path.dirname(llama_cpp.__file__))"',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
llama_cpp_dir = result.stdout.strip()
lib_dir = f'{llama_cpp_dir}/lib'
print(f"llama-cpp-python dir: {llama_cpp_dir}")
print(f"lib dir: {lib_dir}")

# Copy all .so files from build to lib_dir
result = subprocess.run(
    f'cp -v {BUILD_DIR}/bin/*.so* {lib_dir}/ 2>&1 && '
    f'cp -v {BUILD_DIR}/bin/*.so* {llama_cpp_dir}/../../lib/ 2>&1 && '
    f'echo "COPY DONE"',
    shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
)
print(result.stdout)

# Also copy ggml .so files if they're in a different location
result = subprocess.run(
    f'find {BUILD_DIR} -name "libggml*.so*" -exec cp -v {{}} {lib_dir}/ \\; 2>&1',
    shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
)
print(result.stdout)

# Step 5: Verify
print("\\n=== Step 5: Verification ===")
result = subprocess.run(
    f'ls -la {lib_dir}/libggml* {lib_dir}/libllama* 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("Libs in llama-cpp-python:")
print(result.stdout)

result = subprocess.run(
    f'ldd {lib_dir}/libllama.so 2>/dev/null | grep -iE "hip|rocm|amd"',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print(f"\\nHIP/ROCm links: {'FOUND' if result.stdout.strip() else 'NONE'}")
if result.stdout.strip():
    print(result.stdout)

# Check for hipblas strings
result = subprocess.run(
    f'strings {lib_dir}/libllama.so 2>/dev/null | grep -i hipblas | head -10',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
has_hip = bool(result.stdout.strip())
print(f"\\nHIPBLAS strings in libllama.so: {'*** FOUND ***' if has_hip else 'NOT FOUND'}")
if has_hip:
    print(result.stdout[:500])

# Step 6: Test GPU load
if has_hip:
    print("\\n=== Step 6: Testing GPU model load ===")
    test_code = '''
import os, sys
sys.path.insert(0, "/workspace/template-repos/template-1005/repo")
from llama_cpp import Llama

model_path = "/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
print(f"Model: {model_path}")
print(f"Exists: {os.path.exists(model_path)}")

try:
    llm = Llama(
        model_path=model_path,
        n_gpu_layers=-1,
        n_ctx=2048,
        n_batch=512,
        verbose=True
    )
    print("\\n*** GPU LOAD SUCCESS! ***")
    result = llm("Hello, what is 2+2?", max_tokens=50)
    print(f"Response: {result['choices'][0]['text']}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
'''
    result = subprocess.run(
        [sys.executable, '-c', test_code],
        capture_output=True, text=True, timeout=120
    )
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[-1000:])

print("\\n=== DONE ===")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Building vendored llama.cpp with HIPBLAS directly...")
time.sleep(10)
while True:
    try:
        ws.settimeout(10)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
    except Exception as e:
        if 'timed out' in str(e).lower():
            continue
        break

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\n\n=== ALL DONE ===')
