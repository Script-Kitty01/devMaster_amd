import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess, os, sys

print('=== Checking langchain_core ===')

# Check if installed
r = subprocess.run(['/opt/venv/bin/pip', 'list'], capture_output=True, text=True)
for line in r.stdout.split('\n'):
    if 'langchain' in line.lower():
        print('PIP:', line)

# Try importing
r = subprocess.run(['/opt/venv/bin/python', '-c', 'import langchain_core; print("langchain_core OK:", langchain_core.__version__)'],
                   capture_output=True, text=True)
print('Import test:', r.stdout.strip() or 'FAILED: ' + r.stderr.strip())

# Check what the Gradio app imports
os.chdir('/workspace/template-repos/template-1005/repo')
with open('src/graph/workflow.py') as f:
    content = f.read()
print('\n=== workflow.py imports ===')
for line in content.split('\n')[:30]:
    if 'import' in line or 'from' in line:
        print(line)

# Check if Gradio is still running
r = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in r.stdout.split('\n'):
    if 'gradio' in line.lower() or 'python' in line.lower() and 'app' in line.lower():
        print('PROC:', line[:150])
"""

msg_id = 'flc'
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
