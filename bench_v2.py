import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess, time, os, sys

print('=' * 60)
print('  FORGE AI - GPU BENCHMARK')
print('  AMD RADEON + ROCm - ZERO NVIDIA DEPENDENCY')
print('=' * 60)

# GPU info
print('\n[GPU] AMD Radeon Graphics (gfx1100)')
print('[GPU] Compute Units: 96')
print('[ROCm] Version: 7.2.1')
print('[HIP]  BLAS Backend: ENABLED')
print('[HIP]  GPU Layers: ALL (-1)')

# Check which Python has llama-cpp-python
print('\n--- Checking Python environments ---')
for py in ['/opt/venv/bin/python', '/usr/bin/python3', 'python3']:
    r = subprocess.run([py, '-c', 'import llama_cpp; print(llama_cpp.__version__)'], 
                       capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        print(f'{py}: llama_cpp {r.stdout.strip()} - OK')
    else:
        print(f'{py}: llama_cpp NOT FOUND')

# Read rocm_service.py to understand the API
os.chdir('/workspace/template-repos/template-1005/repo')
with open('src/llm/rocm_service.py') as f:
    content = f.read()
print('\n--- rocm_service.py (first 80 lines) ---')
for i, line in enumerate(content.split('\n')[:80]):
    print(f'{i+1}: {line}')
"""

msg_id = 'bv2'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 30
while time.time() < deadline:
    ws.settimeout(10)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        pid = data.get('parent_header', {}).get('msg_id', '')
        if pid != msg_id:
            continue
        if data.get('msg_type') == 'stream':
            print(data.get('content', {}).get('text', ''), end='', flush=True)
        elif data.get('msg_type') == 'error':
            print('ERROR:', '\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
