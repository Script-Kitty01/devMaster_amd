import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, json, os

# Create jupyter server config to enable proxy
config = {
    "ServerApp": {
        "jpserver_extensions": {
            "jupyter_server_proxy": True
        }
    }
}

os.makedirs('/root/.jupyter', exist_ok=True)
with open('/root/.jupyter/jupyter_server_config.json', 'w') as f:
    json.dump(config, f, indent=2)
print('Created jupyter_server_config.json')

# Check current JupyterLab process
result = subprocess.run(['pgrep', '-f', 'jupyter-lab'], capture_output=True, text=True)
jpid = result.stdout.strip()
print(f'JupyterLab PID: {jpid}')

# Kill and restart JupyterLab
print('Killing JupyterLab...')
subprocess.run(['kill', '-9', jpid], capture_output=True)

import time
time.sleep(3)

# Start JupyterLab again
print('Starting JupyterLab...')
subprocess.Popen(
    ['/opt/venv/bin/jupyter-lab', '--ip=0.0.0.0', '--port=8888', '--no-browser', '--allow-root', '--ServerApp.token=amd-oneclick'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)

time.sleep(8)

# Verify it's back
result = subprocess.run(['pgrep', '-f', 'jupyter-lab'], capture_output=True, text=True)
print(f'JupyterLab PID after restart: {result.stdout.strip()}')

result = subprocess.run(['bash', '-c', 'ss -tlnp | grep 8888'], capture_output=True, text=True)
print(f'Port 8888: {result.stdout.strip()}')

# Check extensions
result = subprocess.run(['bash', '-c', '/opt/venv/bin/jupyter server extension list 2>&1 | grep -i proxy'], capture_output=True, text=True)
print(f'Proxy extension: {result.stdout.strip()}')
"""

msg_id = 'fxp2'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 45
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
            print('ERROR:', '\\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
