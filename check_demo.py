import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess

repo = '/workspace/template-repos/template-1005/repo'

r = subprocess.run(['ls', '-la', f'{repo}/demo_repos/'], capture_output=True, text=True)
print('=== demo_repos/ ===')
print(r.stdout)

# Check recursively
r = subprocess.run(['find', f'{repo}/demo_repos', '-type', 'f', '-name', '*.py'], capture_output=True, text=True)
print('=== Python files in demo_repos ===')
print(r.stdout[:2000])

r = subprocess.run(['find', f'{repo}/demo_repos', '-type', 'f', '-name', '*.js'], capture_output=True, text=True)
print('=== JS files in demo_repos ===')
print(r.stdout[:1000])

r = subprocess.run(['find', f'{repo}/demo_repos', '-type', 'f', '-name', '*.java'], capture_output=True, text=True)
print('=== Java files in demo_repos ===')
print(r.stdout[:1000])

# Also check src directory structure
r = subprocess.run(['ls', '-la', f'{repo}/src/'], capture_output=True, text=True)
print('=== src/ ===')
print(r.stdout)
"""

msg = json.dumps({
    'header': {'msg_id': 'cd1', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

timeout = time.time() + 15
while time.time() < timeout:
    ws.settimeout(3)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'cd1':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'cd1':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'cd1':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'cd1':
            break
    except:
        break
ws.close()
