import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess

# Check GPU memory
r = subprocess.run(['/opt/rocm/bin/rocm-smi', '--showmeminfo', 'vram'], capture_output=True, text=True)
print('GPU VRAM:')
print(r.stdout)

# Check if any process is using GPU
r = subprocess.run(['/opt/rocm/bin/rocm-smi', '--showpids'], capture_output=True, text=True)
print('GPU Processes:')
print(r.stdout)

# Check if the gradio process has HIP visible devices
r = subprocess.run(['pgrep', '-f', 'gradio_app'], capture_output=True, text=True)
pid = r.stdout.strip()
if pid:
    r = subprocess.run(['cat', f'/proc/{pid}/environ'], capture_output=True, text=True)
    for var in r.stdout.split('\x00'):
        if 'HIP' in var or 'ROCM' in var or 'GPU' in var or 'HSA' in var:
            print('ENV:', var)
"""

msg_id = 'cgm'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 20
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
