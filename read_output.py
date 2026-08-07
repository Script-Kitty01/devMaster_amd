"""Read warmup output file."""
import requests, json
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = '''
import os
path = "/tmp/warmup_output.txt"
if os.path.exists(path):
    with open(path) as f:
        content = f.read()
    print(content[-3000:])
else:
    print("Output file not found yet")
    
# Also check if warmup is running
import subprocess
result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
for line in result.stdout.split("\\n"):
    if "terminal_warmup" in line and "grep" not in line:
        print(f"\\nWARMUP RUNNING: {line.strip()}")
'''

msg_id = 'read-output'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

import time
deadline = time.time() + 15
while time.time() < deadline:
    ws.settimeout(5)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        pid = data.get('parent_header', {}).get('msg_id', '')
        if pid != msg_id:
            continue
        if data.get('msg_type') == 'stream':
            print(data.get('content', {}).get('text', ''), end='', flush=True)
        elif data.get('msg_type') == 'error':
            print('\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'\n[{e}]')
        break

ws.close()
