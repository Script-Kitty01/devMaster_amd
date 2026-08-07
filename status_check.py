import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess

# Check JupyterLab
result = subprocess.run(['pgrep', '-f', 'jupyter-lab'], capture_output=True, text=True)
print('JupyterLab PID:', result.stdout.strip())

# Check port 8888
result = subprocess.run(['bash', '-c', 'ss -tlnp | grep 8888'], capture_output=True, text=True)
print('Port 8888:', result.stdout.strip())

# Check port 7860
result = subprocess.run(['bash', '-c', 'ss -tlnp | grep 7860 || echo "FREE"'], capture_output=True, text=True)
print('Port 7860:', result.stdout.strip())

# Check any gradio processes
result = subprocess.run(['bash', '-c', 'ps aux | grep -i gradio | grep -v grep || echo "No gradio processes"'], capture_output=True, text=True)
print('Gradio procs:', result.stdout.strip())

# Check jupyter config for proxy
result = subprocess.run(['bash', '-c', 'cat /root/.jupyter/jupyter_server_config.json 2>/dev/null || echo "No config"'], capture_output=True, text=True)
print('Jupyter config:', result.stdout.strip()[:500])

# Check if jupyter-server-proxy is enabled
result = subprocess.run(['bash', '-c', '/opt/venv/bin/jupyter server extension list 2>&1 | head -20'], capture_output=True, text=True)
print('Server extensions:', result.stdout.strip())
"""

msg_id = 'st2'
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
