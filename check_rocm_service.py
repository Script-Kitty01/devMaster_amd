import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess, os

os.chdir('/workspace/template-repos/template-1005/repo')

# Read rocm_service.py to see how it initializes
with open('src/llm/rocm_service.py') as f:
    content = f.read()

# Print the initialize method and model loading section
lines = content.split('\n')
in_init = False
in_model_load = False
for i, line in enumerate(lines):
    if 'def initialize' in line:
        in_init = True
    if in_init:
        print(f'{i+1}: {line}')
        if in_init and line.strip() == '' and i > 0 and lines[i-1].strip() == '':
            # Stop after two blank lines
            pass
        if 'n_gpu_layers' in line or 'n_ctx' in line or 'n_batch' in line or 'Llama' in line:
            in_model_load = True
    if i > 200:
        break
"""

msg_id = 'crs'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 15
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
