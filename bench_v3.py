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

# Check kernel Python
print('Kernel Python:', sys.executable)
print('Kernel sys.path:', sys.path[:3])

# Check if /opt/venv/bin/python has llama_cpp
r = subprocess.run(['/opt/venv/bin/python', '-c', 'import llama_cpp; print("llama_cpp version:", llama_cpp.__version__)'],
                   capture_output=True, text=True, timeout=10)
print('/opt/venv/bin/python:', r.stdout.strip() or r.stderr.strip())

# Read full rocm_service.py to find generate/stream methods
os.chdir('/workspace/template-repos/template-1005/repo')
with open('src/llm/rocm_service.py') as f:
    content = f.read()

# Find all method definitions
import re
methods = re.findall(r'def (\w+)\(', content)
print('\nMethods in ROCmLLM:', methods)

# Find the generate/stream method
for i, line in enumerate(content.split('\n')):
    if 'def generate' in line or 'def stream' in line or 'def __call__' in line or 'def chat' in line or 'def complete' in line:
        # Print surrounding context
        start = max(0, i-2)
        end = min(len(content.split('\n')), i+15)
        print(f'\n--- Lines {start+1}-{end} ---')
        for j in range(start, end):
            print(f'{j+1}: {content.split(chr(10))[j]}')
"""

msg_id = 'bv3'
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
