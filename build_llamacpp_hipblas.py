"""
Build llama.cpp separately with HIPBLAS, then use with llama-cpp-python.
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

# Step 1: Download llama.cpp source with curl (git doesn't work due to SSL)
print("=== Step 1: Downloading llama.cpp ===")
result = subprocess.run(
    'cd /tmp && rm -rf llama.cpp && curl -skL -o llama.cpp.tar.gz https://github.com/ggerganov/llama.cpp/archive/refs/heads/master.tar.gz && tar xzf llama.cpp.tar.gz && mv llama.cpp-master llama.cpp && echo "DOWNLOAD OK"',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)
print(result.stdout.strip())
if result.returncode != 0:
    print("STDERR:", result.stderr[-500:])
    print("FAILED to download")
    sys.exit(1)

# Step 2: Build llama.cpp with HIPBLAS
print("\\n=== Step 2: Building llama.cpp with HIPBLAS ===")
result = subprocess.run(
    'cd /tmp/llama.cpp && mkdir -p build && cd build && '
    'cmake .. -DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100 -DCMAKE_C_COMPILER=/usr/bin/hipcc -DCMAKE_CXX_COMPILER=/usr/bin/hipcc 2>&1 | tail -30',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)
print(result.stdout.strip())
if 'HIPBLAS' not in result.stdout and 'hipblas' not in result.stdout.lower():
    print("\\nWARNING: HIPBLAS not mentioned in cmake output")
    print("STDERR:", result.stderr[-1000:])

print("\\n=== Building (this will take a few minutes) ===")
result = subprocess.run(
    'cd /tmp/llama.cpp/build && cmake --build . --config Release -j$(nproc) 2>&1 | tail -30',
    shell=True, capture_output=True, text=True, timeout=600, executable='/bin/bash'
)
print(result.stdout.strip())
print("Build RC:", result.returncode)

# Step 3: Check what was built
print("\\n=== Step 3: Checking built libs ===")
result = subprocess.run(
    'find /tmp/llama.cpp/build -name "libggml*" -o -name "libllama*" 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print(result.stdout if result.stdout.strip() else "NO LIBS FOUND")

# Check for HIPBLAS specifically
result = subprocess.run(
    'find /tmp/llama.cpp/build -name "*hipblas*" 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
has_hipblas = bool(result.stdout.strip())
print(f"\\nHIPBLAS libs in build: {'*** FOUND! ***' if has_hipblas else 'NOT FOUND'}")
if has_hipblas:
    print(result.stdout)

# Step 4: If HIPBLAS built, copy libs to llama-cpp-python location
if has_hipblas:
    print("\\n=== Step 4: Installing HIPBLAS libs ===")
    # Find the llama-cpp-python lib directory
    result = subprocess.run(
        'find /opt/venv/lib/python3.12/site-packages -name "libllama.so" -type f 2>/dev/null',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print("Existing libllama.so locations:")
    print(result.stdout)
    
    # Copy HIPBLAS-enabled libs
    result = subprocess.run(
        'cp -v /tmp/llama.cpp/build/bin/libllama.so /opt/venv/lib/python3.12/site-packages/llama_cpp/lib/libllama.so && '
        'cp -v /tmp/llama.cpp/build/bin/libggml*.so* /opt/venv/lib/python3.12/site-packages/llama_cpp/lib/ && '
        'cp -v /tmp/llama.cpp/build/bin/libllama.so /opt/venv/lib/python3.12/site-packages/lib/libllama.so && '
        'cp -v /tmp/llama.cpp/build/bin/libggml*.so* /opt/venv/lib/python3.12/site-packages/lib/ && '
        'echo "COPY DONE"',
        shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
    )
    print(result.stdout)
    
    # Verify
    print("\\n=== Verification ===")
    result = subprocess.run(
        'ldd /opt/venv/lib/python3.12/site-packages/llama_cpp/lib/libllama.so | grep -E "hip|rocm|ggml"',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print("libllama.so links:")
    print(result.stdout)
    
    # Test GPU loading
    print("\\n=== Testing GPU model load ===")
    test_code = '''
import sys
sys.path.insert(0, "/workspace/template-repos/template-1005/repo")
from llama_cpp import Llama
import os

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
    print("GPU LOAD SUCCESS!")
    
    # Test inference
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

print("Building llama.cpp with HIPBLAS...")
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
