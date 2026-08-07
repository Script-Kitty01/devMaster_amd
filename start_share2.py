import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os, socket, time

os.chdir('/workspace/template-repos/template-1005/repo')

# Kill ALL gradio processes
os.system('pkill -9 -f gradio 2>/dev/null')
time.sleep(3)

# Create unbuffered script
script = '''
import sys, os
os.environ['PYTHONUNBUFFERED'] = '1'
sys.path.insert(0, "/workspace/template-repos/template-1005/repo")
from src.ui.gradio_app import demo
demo.launch(server_name="0.0.0.0", server_port=7860, share=True)
'''

with open('/tmp/gradio_share2.py', 'w') as f:
    f.write(script)

# Start with unbuffered output
proc = subprocess.Popen(
    ['/opt/venv/bin/python', '-u', '/tmp/gradio_share2.py'],
    stdout=open('/tmp/gradio_share2_out.txt', 'w', buffering=1),
    stderr=open('/tmp/gradio_share2_err.txt', 'w', buffering=1),
    start_new_session=True,
    env={**os.environ, 'PYTHONUNBUFFERED': '1'}
)
print(f'Started PID: {proc.pid}')
print('Waiting 90s...')
time.sleep(90)

# Check output
for fname in ['/tmp/gradio_share2_out.txt', '/tmp/gradio_share2_err.txt']:
    try:
        with open(fname) as f:
            content = f.read()
        print(f'--- {fname} ({len(content)} bytes) ---')
        print(content[-5000:] if len(content) > 5000 else content)
    except Exception as e:
        print(f'{fname}: {e}')

# Check process
result = subprocess.run(['ps', '-p', str(proc.pid), '-o', 'pid,stat,etime'], capture_output=True, text=True)
print('PROC:', result.stdout)
"""

msg_id = 'share2'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 150
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
