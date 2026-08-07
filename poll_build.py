"""Poll build progress - check log size, process status, errors"""
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

# 1. Build process status
r = subprocess.run('pgrep -fc "cmake --build" || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"Build processes: {r.stdout.strip()}")

# 2. Log size
r = subprocess.run('wc -c /tmp/build_hip_full.log 2>/dev/null || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"Log size: {r.stdout.strip()} bytes")

# 3. Log tail
r = subprocess.run('tail -5 /tmp/build_hip_full.log 2>/dev/null || echo "No log"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"Log tail:\\n{r.stdout.strip()}")

# 4. Check for .o files (indicates compilation progress)
r = subprocess.run('find /tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip -name "*.o" | wc -l', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f".o files: {r.stdout.strip()}")

# 5. Check for HIP .o files specifically
r = subprocess.run('find /tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip -path "*/ggml-hip/*" -name "*.o" | wc -l', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"HIP .o files: {r.stdout.strip()}")

# 6. Check for errors
r = subprocess.run('grep -c "error:" /tmp/build_hip_full.log 2>/dev/null || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"Errors: {r.stdout.strip()}")

# 7. Check for warnings
r = subprocess.run('grep -c "warning:" /tmp/build_hip_full.log 2>/dev/null || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"Warnings: {r.stdout.strip()}")

# 8. Check if libggml.so exists and has HIP symbols
r = subprocess.run('nm -D /tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip/bin/libggml.so 2>/dev/null | grep -c "hip" || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"HIP symbols in libggml.so: {r.stdout.strip()}")
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
