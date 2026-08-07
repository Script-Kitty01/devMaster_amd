import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import os

# Verify the correct path exists
correct_path = '/workspace/template-repos/template-1005/repo/demo_repos/sample_app'
print('Checking correct path:', correct_path)
print('Exists:', os.path.exists(correct_path))

if os.path.exists(correct_path):
    print('Files:')
    for f in os.listdir(correct_path):
        print(' ', f)

# Check the wrong path
wrong_path = '/workspace/demo_repos/sample_app'
print('\nWrong path:', wrong_path)
print('Exists:', os.path.exists(wrong_path))

# Read gradio_app.py to find where the default path is set
os.chdir('/workspace/template-repos/template-1005/repo')
with open('src/ui/gradio_app.py') as f:
    content = f.read()

# Find lines with demo_repos or sample_app
for i, line in enumerate(content.split('\n')):
    if 'demo_repos' in line or 'sample_app' in line or ('DEFAULT' in line and 'repo' in line.lower()):
        print(f'  Line {i+1}: {line}')
"""

msg_id = 'fdp'
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
