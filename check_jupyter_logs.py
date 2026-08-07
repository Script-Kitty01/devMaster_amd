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

# Check JupyterLab process
result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in result.stdout.split('\\n'):
    if 'jupyter' in line.lower():
        print(line)

# Check Jupyter config
print('\\n=== Jupyter Config ===')
for path in ['/root/.jupyter/jupyter_server_config.json', '/root/.jupyter/jupyter_server_config.py']:
    try:
        with open(path) as f:
            print(f'{path}:')
            print(f.read()[:1000])
    except:
        print(f'{path}: not found')

# Check if there's a way to list proxy routes
print('\\n=== Checking proxy routes ===')
result = subprocess.run(['bash', '-c', 'curl -s http://localhost:8888/api/proxy 2>/dev/null || echo "No proxy API"'], capture_output=True, text=True)
print('Proxy API:', result.stdout[:500])

# Check JupyterLab API for available routes
result = subprocess.run(['bash', '-c', 'curl -s http://localhost:8888/api/servers 2>/dev/null || echo "No servers API"'], capture_output=True, text=True)
print('Servers API:', result.stdout[:500])

# Check if Gradio is still running
result = subprocess.run(['pgrep', '-f', 'gradio_app'], capture_output=True, text=True)
print('\\nGradio PID:', result.stdout.strip())

# Check port 7860
result = subprocess.run(['bash', '-c', 'ss -tlnp | grep 7860'], capture_output=True, text=True)
print('Port 7860:', result.stdout.strip())
"""

msg_id = 'jpl'
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
            print('ERROR:', '\\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
