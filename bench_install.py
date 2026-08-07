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

print('Installing llama-cpp-python with HIP support...')
r = subprocess.run(['/opt/venv/bin/pip', 'install', 'llama-cpp-python', '--extra-index-url', 'https://download.pytorch.org/whl/rocm7.2.1'], 
                   capture_output=True, text=True, timeout=120)
print(r.stdout[-500:] if len(r.stdout) > 500 else r.stdout)
if r.returncode != 0:
    print('STDERR:', r.stderr[-500:])
    # Try without ROCm index
    print('\nTrying without ROCm index...')
    r = subprocess.run(['/opt/venv/bin/pip', 'install', 'llama-cpp-python'], 
                       capture_output=True, text=True, timeout=120)
    print(r.stdout[-500:] if len(r.stdout) > 500 else r.stdout)
"""

msg_id = 'bi'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 150
while time.time() < deadline:
    ws.settimeout(30)
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
