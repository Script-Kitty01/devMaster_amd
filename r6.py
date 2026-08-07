import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os, signal, time

# Find and kill gradio
r = subprocess.run(['pgrep', '-f', 'gradio_app.py'], capture_output=True, text=True)
pids = r.stdout.strip().split()
for pid in pids:
    os.kill(int(pid), signal.SIGKILL)
    print(f'Killed PID {pid}')

time.sleep(2)

# Start fresh
os.chdir('/workspace/template-repos/template-1005/repo')
subprocess.Popen(
    ['/opt/venv/bin/python3.12', '-u', 'src/ui/gradio_app.py'],
    stdout=open('/tmp/gradio9999.log', 'w'),
    stderr=subprocess.STDOUT,
    start_new_session=True
)
print('Started new Gradio')

time.sleep(6)

# Verify
r = subprocess.run(['pgrep', '-f', 'gradio_app.py'], capture_output=True, text=True)
print('New PID:', r.stdout.strip())

r = subprocess.run(['tail', '-3', '/tmp/gradio9999.log'], capture_output=True, text=True)
print('Log:', r.stdout.strip())
"""

msg = json.dumps({
    'header': {'msg_id': 'rg2', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

timeout = time.time() + 20
while time.time() < timeout:
    ws.settimeout(3)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'rg2':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'rg2':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'rg2':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'rg2':
            break
    except:
        break
ws.close()
