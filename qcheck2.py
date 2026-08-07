"""Deeper check: find libllama.so, libggml.so, check HIP symbols"""
import requests, json, time, uuid, urllib3
from websocket import create_connection
urllib3.disable_warnings()

BASE = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
TOKEN = 'amd-oneclick'

r = requests.post(f'{BASE}/api/kernels', headers={'Authorization': f'token {TOKEN}'}, verify=False)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token={TOKEN}'
ws = create_connection(ws_url)
msg = json.loads(ws.recv())

code = """
import subprocess

# 1. Find ALL .so files in build_hip
r = subprocess.run('find /tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip -name "*.so" -type f 2>/dev/null', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"ALL .so in build_hip:\\n{r.stdout.strip()}")

# 2. Check for libllama.so specifically
r = subprocess.run('find /tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip -name "libllama.so" -o -name "libggml.so" 2>/dev/null', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\nMain libs: {r.stdout.strip() or 'NOT FOUND'}")

# 3. Check HIP symbols in any libllama.so found
r = subprocess.run('for f in $(find /tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip -name "libllama.so" -type f 2>/dev/null); do echo "=== $f ==="; nm -D "$f" 2>/dev/null | grep -i hip | head -5; done', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\nHIP symbols: {r.stdout.strip() or 'NONE'}")

# 4. Check hipblas strings
r = subprocess.run('for f in $(find /tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip -name "libllama.so" -type f 2>/dev/null); do echo "=== $f ==="; strings "$f" 2>/dev/null | grep -i hipblas | head -5; done', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\nhipBLAS strings: {r.stdout.strip() or 'NONE'}")

# 5. Check build_hipblas (old CPU build)
r = subprocess.run('find /tmp/llama_cpp_python_src/vendor/llama.cpp/build_hipblas -name "libllama.so" -o -name "libggml.so" 2>/dev/null', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\nbuild_hipblas main libs: {r.stdout.strip() or 'NOT FOUND'}")

# 6. Check /tmp/llama.cpp
r = subprocess.run('find /tmp/llama.cpp/build -name "libllama.so" -o -name "libggml.so" 2>/dev/null', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\n/tmp/llama.cpp main libs: {r.stdout.strip() or 'NOT FOUND'}")

# 7. Kill old builds
r = subprocess.run('pkill -f "build_hipblas" 2>/dev/null; pkill -f "/tmp/llama.cpp" 2>/dev/null; echo "Killed old builds"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\n{r.stdout.strip()}")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(5)
while True:
    try:
        ws.settimeout(2)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
    except:
        break
ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\nDone')
