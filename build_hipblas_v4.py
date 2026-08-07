"""
Build llama-cpp-python with HIPBLAS - v4: set env vars in shell before pip.
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
import subprocess, sys, os

# Uninstall first
print("=== Uninstalling ===")
subprocess.run([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y"], capture_output=True)

# Try approach 1: Set env vars in shell and run pip via shell
print("\\n=== Approach 1: Shell with env vars ===")
result = subprocess.run(
    'export CMAKE_ARGS="-DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100" && export FORCE_CMAKE=1 && pip install llama-cpp-python --no-binary :all: --no-cache-dir 2>&1 | tail -50',
    shell=True, capture_output=True, text=True, timeout=600, executable='/bin/bash'
)
print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[-1000:])
print("RC:", result.returncode)

# Check
print("\\n=== Checking for HIPBLAS ===")
result = subprocess.run(["find", "/opt/venv", "-name", "*hipblas*"], capture_output=True, text=True)
has = bool(result.stdout.strip())
print(f"HIPBLAS: {'FOUND!' if has else 'NOT FOUND'}")
if has:
    print(result.stdout)

if not has:
    # Try approach 2: Use pip --config-settings
    print("\\n=== Approach 2: pip --config-settings ===")
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y"], capture_output=True)
    
    result = subprocess.run([
        sys.executable, "-m", "pip", "install", "llama-cpp-python",
        "--no-binary", ":all:", "--no-cache-dir",
        "--config-settings=cmake.args=-DGGML_HIPBLAS=ON",
        "--config-settings=cmake.args=-DAMDGPU_TARGETS=gfx1100"
    ], capture_output=True, text=True, timeout=600)
    print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
    print("RC:", result.returncode)
    
    result = subprocess.run(["find", "/opt/venv", "-name", "*hipblas*"], capture_output=True, text=True)
    has = bool(result.stdout.strip())
    print(f"HIPBLAS: {'FOUND!' if has else 'NOT FOUND'}")

if not has:
    # Try approach 3: Build llama.cpp separately first
    print("\\n=== Approach 3: Build llama.cpp separately ===")
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y"], capture_output=True)
    
    # Clone and build llama.cpp with HIPBLAS
    build_script = '''
cd /tmp
rm -rf llama-cpp-build
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git llama-cpp-build 2>&1 || echo "GIT CLONE FAILED"
if [ -d llama-cpp-build ]; then
    cd llama-cpp-build
    mkdir -p build && cd build
    cmake .. -DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100 -DCMAKE_C_COMPILER=hipcc -DCMAKE_CXX_COMPILER=hipcc 2>&1 | tail -20
    cmake --build . --config Release -j$(nproc) 2>&1 | tail -20
    echo "BUILD DONE"
    find . -name "libggml*" -o -name "libllama*" 2>/dev/null
fi
'''
    result = subprocess.run(build_script, shell=True, capture_output=True, text=True, timeout=600, executable='/bin/bash')
    print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
    print("RC:", result.returncode)

print("\\n=== FINAL CHECK ===")
result = subprocess.run(["find", "/opt/venv", "/tmp/llama-cpp-build", "-name", "*hipblas*", "-o", "-name", "libggml-hipblas*"], capture_output=True, text=True)
print(result.stdout if result.stdout.strip() else "NO HIPBLAS ANYWHERE")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Waiting for build...")
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
print('\n\n=== DONE ===')
