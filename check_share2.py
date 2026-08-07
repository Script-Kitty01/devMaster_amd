import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import os, subprocess

# Check output files
for fname in ['/tmp/gradio_share_out.txt', '/tmp/gradio_share_err.txt']:
    try:
        with open(fname) as f:
            content = f.read()
        print(f'--- {fname} ({len(content)} bytes) ---')
        print(content)
    except Exception as e:
        print(f'{fname}: {e}')

# Check process
result = subprocess.run(['ps', '-p', '38508', '-o', 'pid,stat,etime,rss'], capture_output=True, text=True)
print('PROC:', result.stdout)

# Check all gradio processes
result2 = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in result2.stdout.split('\\n'):
    if 'gradio' in line.lower() and 'grep' not in line:
        print('PS:', line.strip())
    if 'frpc' in line.lower() and 'grep' not in line:
        print('FRPC:', line.strip())
"""

msg_id = 'chks2'
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
