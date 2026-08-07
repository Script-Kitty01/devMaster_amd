import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import socket, os, time

# Check if port 7860 is listening via Python
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = s.connect_ex(('127.0.0.1', 7860))
s.close()
print('Port 7860:', 'OPEN' if result == 0 else f'CLOSED (err={result})')

# Check stdout file size
for fname in ['/tmp/gradio_stdout.txt', '/tmp/gradio_stderr.txt']:
    try:
        size = os.path.getsize(fname)
        print(f'{fname}: {size} bytes')
        if size > 0:
            with open(fname) as f:
                content = f.read()
            print(content[-2000:] if len(content) > 2000 else content)
    except Exception as e:
        print(f'{fname}: {e}')

# Check process
import subprocess
result = subprocess.run(['ps', '-p', '37923', '-o', 'pid,stat,etime,rss,cmd'], capture_output=True, text=True)
print(result.stdout)

# Also check all python processes
result2 = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in result2.stdout.split('\\n'):
    if 'gradio' in line.lower() and 'grep' not in line:
        print('PS:', line.strip())
"""

msg_id = 'port2'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 60
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
