import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess, os, time, signal

# Kill old processes
print('Killing old processes...')
subprocess.run(['pkill', '-f', 'gradio_app'], capture_output=True)
subprocess.run(['pkill', '-f', 'frpc_linux_amd64'], capture_output=True)
time.sleep(2)

# Verify we're in the right directory
repo_dir = '/workspace/template-repos/template-1005/repo'
os.chdir(repo_dir)
print('Working dir:', os.getcwd())

# Verify src module is importable
r = subprocess.run(['/opt/venv/bin/python', '-c', 'import sys; sys.path.insert(0, "."); from src.ui.gradio_app import demo; print("Import OK")'],
                   capture_output=True, text=True, cwd=repo_dir, timeout=15)
print('Import test:', r.stdout.strip() or 'FAILED: ' + r.stderr.strip()[:300])

# Start Gradio from the correct directory
print('\nStarting Gradio from', repo_dir, '...')
proc = subprocess.Popen(
    ['/opt/venv/bin/python', '-u', 'src/ui/gradio_app.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    cwd=repo_dir
)

# Wait for public URL
deadline = time.time() + 60
while time.time() < deadline:
    line = proc.stdout.readline()
    if line:
        print(line, end='')
        if 'gradio.live' in line:
            break
    else:
        if proc.poll() is not None:
            print('Process exited early!')
            break
        time.sleep(0.5)

print('\nDone!')
"""

msg_id = 'rf'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 90
while time.time() < deadline:
    ws.settimeout(20)
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
