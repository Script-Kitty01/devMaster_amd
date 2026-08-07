import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os, time

os.chdir('/workspace/template-repos/template-1005/repo')

# Start Gradio in background with unbuffered output
with open('/tmp/gradio_fresh_out.txt', 'w', buffering=1) as out, open('/tmp/gradio_fresh_err.txt', 'w', buffering=1) as err:
    proc = subprocess.Popen(
        ['/opt/venv/bin/python', '-u', 'src/ui/gradio_app.py'],
        stdout=out, stderr=err,
        env={**os.environ, 'PYTHONUNBUFFERED': '1'},
        cwd='/workspace/template-repos/template-1005/repo'
    )
    print(f'Started PID: {proc.pid}')

# Wait for port to open
for i in range(30):
    time.sleep(2)
    result = subprocess.run(['bash', '-c', 'ss -tlnp | grep 7860'], capture_output=True, text=True)
    if result.returncode == 0:
        print(f'Port 7860 OPEN after {(i+1)*2}s')
        break
else:
    print('Port 7860 did not open within 60s')

# Check output
time.sleep(3)
with open('/tmp/gradio_fresh_out.txt') as f:
    out = f.read()
with open('/tmp/gradio_fresh_err.txt') as f:
    err = f.read()
print(f'--- STDOUT ({len(out)} bytes) ---')
print(out[-2000:])
print(f'--- STDERR ({len(err)} bytes) ---')
print(err[-1000:])
"""

msg_id = 'gfr'
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
            print('ERROR:', '\\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
