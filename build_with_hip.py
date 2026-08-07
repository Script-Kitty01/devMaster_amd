"""
Try GGML_HIP=ON (not GGML_HIPBLAS) - the option name changed in newer llama.cpp.
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

LLAMA_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp'

# Check what the ggml CMakeLists.txt says about HIP
print("=== Checking ggml CMakeLists for HIP options ===")
result = subprocess.run(
    f'grep -n "GGML_HIP" {LLAMA_DIR}/ggml/CMakeLists.txt | head -30',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("GGML_HIP in ggml/CMakeLists.txt:")
print(result.stdout[:2000])

# Check the ggml-hip CMakeLists
result = subprocess.run(
    f'cat {LLAMA_DIR}/ggml/src/ggml-hip/CMakeLists.txt 2>/dev/null | head -50',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("\\nggml-hip CMakeLists.txt:")
print(result.stdout[:2000])

# Check the main CMakeLists for HIP
result = subprocess.run(
    f'grep -n "GGML_HIP\\|hipblas\\|HIP" {LLAMA_DIR}/CMakeLists.txt | head -30',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("\\nGGML_HIP in main CMakeLists.txt:")
print(result.stdout[:2000])

# Try building with GGML_HIP=ON
print("\\n=== Building with GGML_HIP=ON ===")
BUILD_DIR = f'{LLAMA_DIR}/build_hip'
subprocess.run(f'rm -rf {BUILD_DIR}', shell=True, capture_output=True, text=True, executable='/bin/bash')
os.makedirs(BUILD_DIR, exist_ok=True)

result = subprocess.run(
    f'cd {BUILD_DIR} && '
    f'CMAKE_PREFIX_PATH="/opt/rocm" '
    f'cmake .. '
    f'-DGGML_HIP=ON '
    f'-DAMDGPU_TARGETS=gfx1100 '
    f'-DCMAKE_BUILD_TYPE=Release '
    f'-DBUILD_SHARED_LIBS=ON '
    f'2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)
print(result.stdout[-3000:])

# Check for HIP backend
hip_found = False
for line in result.stdout.split('\\n'):
    if any(kw in line for kw in ['HIP', 'hip', 'GPU', 'backend', 'GGML_HIP']):
        print(f"  >> {line.strip()[:150]}")
        if 'HIP backend' in line or 'GGML_HIP' in line:
            hip_found = True

print(f"\\nHIP backend found: {hip_found}")

if result.returncode != 0:
    print(f"CMAKE FAILED (rc={result.returncode})")
    print("STDERR:", result.stderr[-2000:])
    sys.exit(1)

# Build
print("\\n=== Building (this will take several minutes) ===")
result = subprocess.run(
    f'cd {BUILD_DIR} && cmake --build . --config Release -j$(nproc) 2>&1 | tail -50',
    shell=True, capture_output=True, text=True, timeout=600, executable='/bin/bash'
)
print(result.stdout[-3000:])
print(f"Build RC: {result.returncode}")

if result.returncode != 0:
    print("BUILD FAILED")
    sys.exit(1)

# Find and copy libs
print("\\n=== Installing libs ===")
result = subprocess.run(
    f'find {BUILD_DIR} -name "*.so" -type f | head -20',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("Built libs:", result.stdout[:1000])

# Check for HIP symbols
result = subprocess.run(
    f'for f in $(find {BUILD_DIR}/bin -name "*.so" -type f); do echo "=== $f ==="; nm -D "$f" 2>/dev/null | grep -i hip | head -3; done',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("\\nHIP symbols:", result.stdout[:2000])

# Copy to llama-cpp-python
result = subprocess.run(
    'python3.12 -c "import llama_cpp; import os; print(os.path.dirname(llama_cpp.__file__))"',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
llama_dir = result.stdout.strip()
lib_dir = f'{llama_dir}/lib'

result = subprocess.run(
    f'cp -v {BUILD_DIR}/bin/*.so* {lib_dir}/ 2>&1 && echo "COPIED"',
    shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
)
print(result.stdout)

# Verify
result = subprocess.run(
    f'strings {lib_dir}/libllama.so 2>/dev/null | grep -i hipblas | head -5',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
has_hip = bool(result.stdout.strip())
print(f"\\nHIPBLAS in libllama.so: {'*** YES ***' if has_hip else 'NO'}")

# Test GPU load
if has_hip:
    print("\\n=== Testing GPU load ===")
    test_code = '''
import os, sys
sys.path.insert(0, "/workspace/template-repos/template-1005/repo")
from llama_cpp import Llama

model_path = "/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
try:
    llm = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=2048, n_batch=512, verbose=True)
    print("\\n*** GPU LOAD SUCCESS! ***")
    result = llm("Hello, what is 2+2?", max_tokens=50)
    print(f"Response: {result['choices'][0]['text']}")
except Exception as e:
    print(f"ERROR: {e}")
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

print("Building with GGML_HIP=ON...")
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
