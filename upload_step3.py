"""Upload step3_only.py to remote via base64."""
import requests, json, base64
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

with open('step3_only.py', 'rb') as f:
    content = f.read()

encoded = base64.b64encode(content).decode('ascii')

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = f'''
import base64
data = base64.b64decode("{encoded}")
with open("/workspace/template-repos/template-1005/repo/step3_only.py", "wb") as f:
    f.write(data)
print(f"Script written! Size: {{len(data)}} bytes")
'''

msg_id = 'upload-step3'
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
print("\nDone! Run in terminal: /opt/venv/bin/python step3_only.py")
