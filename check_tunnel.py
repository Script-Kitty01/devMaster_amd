import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess

# Check frpc process
r = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in r.stdout.split('\n'):
    if 'frpc' in line:
        print('FRPC:', line)

# Try to access the share URL from the instance itself
r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'https://6cc5a6495aac4ac877.gradio.live', '--max-time', '15'],
                   capture_output=True, text=True, timeout=20)
print('\nShare URL status from instance:', r.stdout.strip())

# Check if frpc can reach gradio.live
r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'https://gradio.live', '--max-time', '10'],
                   capture_output=True, text=True, timeout=15)
print('gradio.live reachable:', r.stdout.strip())

# Check DNS
r = subprocess.run(['nslookup', 'gradio.live'], capture_output=True, text=True, timeout=10)
print('\nDNS for gradio.live:')
print(r.stdout[:500] if r.stdout else r.stderr[:500])

# Check if the frpc has established connection
r = subprocess.run(['cat', '/proc/4695/net/tcp'], capture_output=True, text=True)
print('\nfrpc TCP connections:')
for line in r.stdout.split('\n'):
    print(line)
"""

msg_id = 'ct'
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
