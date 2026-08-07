import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os, socket

# Kill ALL gradio processes
os.system('pkill -9 -f gradio_app 2>/dev/null; sleep 3')

# Verify port is free
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
r = s.connect_ex(('127.0.0.1', 7860))
s.close()
print('Port 7860:', 'FREE' if r != 0 else 'STILL IN USE')

# Check what's on port 7860 if still in use
if r == 0:
    result = subprocess.run(['fuser', '7860/tcp'], capture_output=True, text=True)
    print('Port users:', result.stdout)

# Check Jupyter config for proxy settings
for path in ['/etc/jupyter', '/root/.jupyter', '/home/*/.jupyter']:
    try:
        result = subprocess.run(['find', path, '-name', '*.py', '-o', '-name', '*.json'], capture_output=True, text=True)
        print(f'Config in {path}:', result.stdout[:500])
    except:
        pass

# Check if there's a server proxy extension
result = subprocess.run(['/opt/venv/bin/pip', 'list'], capture_output=True, text=True)
for line in result.stdout.split('\\n'):
    if 'proxy' in line.lower() or 'jupyter' in line.lower():
        print('PKG:', line.strip())
"""

msg_id = 'fixp'
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
