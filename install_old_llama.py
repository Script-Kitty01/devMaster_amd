"""
Try installing older llama-cpp-python that uses setuptools (respects CMAKE_ARGS).
Also try forcing scikit-build-core with cmake.args config setting.
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

# Approach 1: Try scikit-build-core with cmake.args (not cmake.define)
print("=== Approach 1: scikit-build-core with cmake.args ===")
result = subprocess.run(
    '/opt/venv/bin/pip uninstall llama-cpp-python -y 2>&1',
    shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
)
print(result.stdout.strip())

result = subprocess.run(
    '/opt/venv/bin/pip install llama-cpp-python --no-binary :all: --no-cache-dir '
    '--config-settings=cmake.args="-DGGML_HIPBLAS=ON;-DAMDGPU_TARGETS=gfx1100" '
    '-v 2>&1 | tail -50',
    shell=True, capture_output=True, text=True, timeout=300, executable='/bin/bash'
)
print(result.stdout.strip())

# Check
result = subprocess.run(
    'python3.12 -c "from llama_cpp import llama_cpp; print([x for x in dir(llama_cpp) if \\'hip\\' in x.lower() or \\'rocm\\' in x.lower()])" 2>&1',
    shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
)
print("HIP attrs:", result.stdout.strip())

result = subprocess.run(
    'python3.12 -c "import llama_cpp; print(llama_cpp.__file__); import ctypes; lib = ctypes.CDLL(llama_cpp.__file__.replace(\\'__init__.py\\',\\'lib/libllama.so\\')); print(dir(lib))" 2>&1',
    shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
)
print("Lib check:", result.stdout.strip()[-500:])

# Check for hipblas in the .so
result = subprocess.run(
    'find /opt/venv/lib/python3.12/site-packages/llama_cpp -name "*.so" -exec sh -c "strings {} | grep -i hipblas | head -5" \\; 2>/dev/null',
    shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
)
has_hip = bool(result.stdout.strip())
print(f"\\nHIPBLAS strings in .so: {'*** FOUND ***' if has_hip else 'NOT FOUND'}")
if has_hip:
    print(result.stdout[:500])

print("\\n=== DONE ===")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Trying cmake.args approach...")
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
