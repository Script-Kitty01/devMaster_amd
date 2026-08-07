"""
Build HIPBLAS libs from vendored llama.cpp with GGML_HIP=ON.
Runs build in background, then checks results.
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

# Step 1: Configure cmake (fast)
code1 = """
import subprocess, sys, os

LLAMA_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp'
BUILD_DIR = f'{LLAMA_DIR}/build_hip'

subprocess.run(f'rm -rf {BUILD_DIR}', shell=True, capture_output=True, text=True, executable='/bin/bash')
os.makedirs(BUILD_DIR, exist_ok=True)

result = subprocess.run(
    f'cd {BUILD_DIR} && cmake .. '
    f'-DGGML_HIP=ON '
    f'-DAMDGPU_TARGETS=gfx1100 '
    f'-DCMAKE_BUILD_TYPE=Release '
    f'-DBUILD_SHARED_LIBS=ON '
    f'2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)
print(result.stdout[-2000:])
print(f"CMAKE_RC: {result.returncode}")

# Check for HIP
if 'Including HIP backend' in result.stdout:
    print("HIP_BACKEND: YES")
else:
    print("HIP_BACKEND: NO")
    sys.exit(1)
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code1, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Configuring cmake...")
time.sleep(5)
output = ""
while True:
    try:
        ws.settimeout(10)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            output += msg['content']['text']
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
    except Exception as e:
        if 'timed out' in str(e).lower():
            continue
        break

if 'HIP_BACKEND: YES' not in output:
    print("HIP backend not found, aborting")
    ws.close()
    sys.exit(1)

# Step 2: Build (long - use nohup)
code2 = """
import subprocess, sys, os

LLAMA_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp'
BUILD_DIR = f'{LLAMA_DIR}/build_hip'

# Run build with nohup and write output to file
result = subprocess.run(
    f'cd {BUILD_DIR} && nohup cmake --build . --config Release -j$(nproc) > /tmp/build_hip.log 2>&1 &',
    shell=True, capture_output=True, text=True, timeout=10, executable='/bin/bash'
)
print("Build started in background")
print(f"Build log: /tmp/build_hip.log")

# Wait for build to complete (poll the log file)
import time
max_wait = 1200  # 20 minutes
start = time.time()
while time.time() - start < max_wait:
    time.sleep(30)
    # Check if build is done
    result = subprocess.run(
        'tail -5 /tmp/build_hip.log 2>/dev/null',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    last_lines = result.stdout.strip()
    if last_lines:
        print(f"[{int(time.time()-start)}s] {last_lines[-200:]}")
    
    # Check for completion markers
    if 'Build finished' in last_lines or 'error:' in last_lines.lower():
        break
    
    # Check if cmake process is still running
    result = subprocess.run(
        'pgrep -f "cmake --build" > /dev/null && echo "RUNNING" || echo "DONE"',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    if 'DONE' in result.stdout:
        print("Build process completed!")
        break

# Show final output
result = subprocess.run(
    'tail -50 /tmp/build_hip.log 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("\\n=== Build output (last 50 lines) ===")
print(result.stdout)

# Check for errors
if 'error:' in result.stdout.lower():
    print("BUILD HAD ERRORS")
    # Show error context
    result = subprocess.run(
        'grep -A5 "error:" /tmp/build_hip.log 2>/dev/null | head -30',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print(result.stdout)
else:
    print("BUILD APPEARS SUCCESSFUL")
    
    # Find built libs
    result = subprocess.run(
        f'find {BUILD_DIR} -name "*.so" -type f | head -20',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print("\\nBuilt libs:")
    print(result.stdout)
    
    # Check for HIP symbols
    result = subprocess.run(
        f'for f in $(find {BUILD_DIR}/bin -name "*.so" -type f 2>/dev/null); do echo "=== $f ==="; nm -D "$f" 2>/dev/null | grep -i hip | head -3; done',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print("HIP symbols:", result.stdout[:2000])
    
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
    'content': {'code': code2, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("\nBuilding in background (this will take 10-20 minutes)...")
print("Waiting for output...")
time.sleep(10)

# Read with very long timeout
ws.settimeout(1200)  # 20 minute timeout
while True:
    try:
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
        if msg.get('msg_type') == 'status' and msg.get('content', {}).get('execution_state') == 'idle':
            print('\n=== Execution complete ===')
            break
    except Exception as e:
        print(f'WebSocket error: {e}')
        break

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\n\n=== ALL DONE ===')
