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
os.chdir('/workspace/template-repos/template-1005/repo')
# Kill any existing gradio
os.system('pkill -f gradio_app.py 2>/dev/null; sleep 1')
# Start gradio in background
proc = subprocess.Popen(
    ['/opt/venv/bin/python', 'src/ui/gradio_app.py'],
    stdout=open('/tmp/gradio_stdout.txt', 'w'),
    stderr=open('/tmp/gradio_stderr.txt', 'w'),
    start_new_session=True
)
print(f'Gradio PID: {proc.pid}')
print('Waiting 15s for startup...')
import time
time.sleep(15)
# Check if still running
result = subprocess.run(['ps', '-p', str(proc.pid), '-o', 'pid,stat,etime'], capture_output=True, text=True)
print(result.stdout)
# Check stderr for errors
with open('/tmp/gradio_stderr.txt') as f:
    err = f.read()
print('STDERR (last 2000):', err[-2000:] if len(err) > 2000 else err)
# Check stdout
with open('/tmp/gradio_stdout.txt') as f:
    out = f.read()
print('STDOUT (last 2000):', out[-2000:] if len(out) > 2000 else out)
"""

msg_id = 'gradio'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 30
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
            print('ERROR:', '\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
