import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os

# Kill all existing gradio
os.system('pkill -f gradio_app 2>/dev/null; sleep 2')

# Verify nothing on port 7860
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
r = s.connect_ex(('127.0.0.1', 7860))
s.close()
print('Port 7860 before:', 'OPEN' if r == 0 else 'FREE')

# Start gradio WITHOUT share (share requires internet)
# But with the original file (not patched)
os.chdir('/workspace/template-repos/template-1005/repo')
proc = subprocess.Popen(
    ['/opt/venv/bin/python', 'src/ui/gradio_app.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    start_new_session=True,
    text=True
)
print(f'Started PID: {proc.pid}')

# Wait and read initial output
import time, select
deadline = time.time() + 60
output = []
while time.time() < deadline:
    if proc.poll() is not None:
        break
    ready, _, _ = select.select([proc.stdout], [], [], 2)
    if ready:
        line = proc.stdout.readline()
        if line:
            output.append(line)
            print(line, end='')
    if any('Running on' in l for l in output):
        break

print('\\n---FINAL OUTPUT---')
print(''.join(output[-20:]))

# Check port
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
r = s.connect_ex(('127.0.0.1', 7860))
s.close()
print('Port 7860:', 'OPEN' if r == 0 else 'CLOSED')
"""

msg_id = 'gterm'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 90
while time.time() < deadline:
    ws.settimeout(15)
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
