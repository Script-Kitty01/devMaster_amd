import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print('Kernel:', kid)

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os

# Kill stuck gradio
subprocess.run('pkill -9 -f gradio_app.py', shell=True)
print('Killed gradio')

# Read the workflow file
r = subprocess.run(['cat', '/workspace/template-repos/template-1005/repo/src/graph/workflow.py'], capture_output=True, text=True)
print('=== WORKFLOW ===')
print(r.stdout[:10000])

print('=== END WORKFLOW ===')

# Read full rocm_service.py
r = subprocess.run(['cat', '/workspace/template-repos/template-1005/repo/src/llm/rocm_service.py'], capture_output=True, text=True)
print('=== ROCM SERVICE ===')
print(r.stdout[:10000])
"""

msg = json.dumps({
    'header': {'msg_id': 'x6', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

timeout = time.time() + 20
while time.time() < timeout:
    ws.settimeout(5)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'x6':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'x6':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'x6':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'x6':
            break
    except:
        break

ws.close()
print('---DONE---')
