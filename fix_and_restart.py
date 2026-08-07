import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print('Kernel:', kid)

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, sys, os, time

repo = '/workspace/template-repos/template-1005/repo'

# Check which python has gradio
r = subprocess.run([sys.executable, '-c', 'import gradio; print(gradio.__version__)'], capture_output=True, text=True)
print('Current python gradio:', r.stdout.strip(), r.stderr.strip())

# Check pip list for gradio
r = subprocess.run([sys.executable, '-m', 'pip', 'list'], capture_output=True, text=True)
for line in r.stdout.split(chr(10)):
    if 'gradio' in line.lower():
        print('PIP:', line)

# Check if there's a venv
r = subprocess.run(['find', repo, '-name', 'activate', '-path', '*/bin/activate'], capture_output=True, text=True)
print('Venvs:', r.stdout.strip())

# Check what python3 is
r = subprocess.run(['which', 'python3'], capture_output=True, text=True)
print('python3:', r.stdout.strip())
r = subprocess.run(['which', 'python'], capture_output=True, text=True)
print('python:', r.stdout.strip())

# Try installing gradio
r = subprocess.run([sys.executable, '-m', 'pip', 'install', 'gradio', '--break-system-packages'], capture_output=True, text=True, timeout=60)
print('Install:', r.stdout[-500:], r.stderr[-500:])
"""

msg = json.dumps({
    'header': {'msg_id': 'x10', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

timeout = time.time() + 90
while time.time() < timeout:
    ws.settimeout(10)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'x10':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'x10':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'x10':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'x10':
            break
    except:
        break

ws.close()
print('---DONE---')
