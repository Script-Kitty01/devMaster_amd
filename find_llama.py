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

# Check pip list for llama
r = subprocess.run(['/opt/venv/bin/pip', 'list'], capture_output=True, text=True, timeout=15)
for line in r.stdout.split('\n'):
    if 'llama' in line.lower():
        print('PIP:', line)

# Check if llama_cpp is installed as a package in site-packages
r = subprocess.run(['/opt/venv/bin/python', '-c', 'import site; print(site.getsitepackages())'], capture_output=True, text=True)
print('Site packages:', r.stdout.strip())

# Look for llama_cpp in site-packages
for sp in r.stdout.strip().split('\n'):
    sp = sp.strip().strip("[],' ")
    if sp:
        r2 = subprocess.run(['ls', sp + '/llama_cpp*'], capture_output=True, text=True)
        print(f'  {sp}/llama_cpp*:', r2.stdout.strip() or 'NOT FOUND')

# Check if there's a different venv
r = subprocess.run(['find', '/workspace', '-name', 'llama_cpp', '-type', 'd', '-maxdepth', '6'], capture_output=True, text=True, timeout=15)
print('\nllama_cpp dirs:', r.stdout.strip() or 'NONE')

# Check the Gradio process environment
r = subprocess.run(['cat', '/proc/286/environ'], capture_output=True, text=True)
env = r.stdout.replace('\x00', '\n')
for line in env.split('\n'):
    if 'PYTHON' in line.upper() or 'PATH' in line.upper() or 'VENV' in line.upper():
        print('ENV:', line)
"""

msg_id = 'fl2'
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
