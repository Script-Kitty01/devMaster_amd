import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os

# Check what's in /workspace
r = subprocess.run(['ls', '-la', '/workspace/'], capture_output=True, text=True)
print('=== /workspace/ ===')
print(r.stdout)

# Check demo_repos
r = subprocess.run(['ls', '-la', '/workspace/demo_repos/'], capture_output=True, text=True)
print('=== /workspace/demo_repos/ ===')
print(r.stdout)

# Check template-repos
r = subprocess.run(['ls', '-la', '/workspace/template-repos/'], capture_output=True, text=True)
print('=== /workspace/template-repos/ ===')
print(r.stdout)

# Find any Python/JS/Java projects
r = subprocess.run(['find', '/workspace', '-maxdepth', '4', '-name', '*.py', '-type', 'f'], capture_output=True, text=True)
print('=== Python files (first 30) ===')
lines = r.stdout.strip().split(chr(10))[:30]
for l in lines:
    print(l)

# Check if Kutaar repo itself has sample code
r = subprocess.run(['ls', '-la', '/workspace/template-repos/template-1005/repo/'], capture_output=True, text=True)
print('=== Kutaar repo root ===')
print(r.stdout)
"""

msg = json.dumps({
    'header': {'msg_id': 'fr1', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

timeout = time.time() + 20
while time.time() < timeout:
    ws.settimeout(3)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'fr1':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'fr1':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'fr1':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'fr1':
            break
    except:
        break
ws.close()
