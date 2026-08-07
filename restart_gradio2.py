import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os, sys
os.chdir('/workspace/template-repos/template-1005/repo')

# Kill existing gradio
os.system('pkill -f gradio_app.py 2>/dev/null; sleep 2')

# Patch gradio_app.py to use share=True
with open('src/ui/gradio_app.py') as f:
    content = f.read()

# Replace share=False with share=True
content = content.replace('share=False,', 'share=True,')

with open('src/ui/gradio_app_patched.py', 'w') as f:
    f.write(content)

print('Patched file written')

# Start patched gradio
proc = subprocess.Popen(
    ['/opt/venv/bin/python', 'src/ui/gradio_app_patched.py'],
    stdout=open('/tmp/gradio_stdout3.txt', 'w'),
    stderr=open('/tmp/gradio_stderr3.txt', 'w'),
    start_new_session=True
)
print(f'Gradio PID: {proc.pid}')
print('Waiting 45s for startup + share tunnel...')
import time
time.sleep(45)

# Check output
for fname in ['/tmp/gradio_stdout3.txt', '/tmp/gradio_stderr3.txt']:
    try:
        with open(fname) as f:
            content = f.read()
        print(f'--- {fname} ({len(content)} bytes) ---')
        print(content[-4000:] if len(content) > 4000 else content)
    except Exception as e:
        print(f'{fname}: {e}')

# Check process
result = subprocess.run(['ps', '-p', str(proc.pid), '-o', 'pid,stat,etime'], capture_output=True, text=True)
print(result.stdout)
"""

msg_id = 'restart2'
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
