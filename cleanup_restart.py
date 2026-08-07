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

# Kill all gradio/share python processes
print('=== Killing Gradio processes ===')
result = subprocess.run(['pkill', '-f', 'gradio'], capture_output=True, text=True)
print('pkill gradio rc:', result.returncode)
result = subprocess.run(['pkill', '-f', 'share'], capture_output=True, text=True)
print('pkill share rc:', result.returncode)

time.sleep(2)

# Check port 7860
result = subprocess.run(['bash', '-c', 'ss -tlnp | grep 7860 || echo "Port 7860: FREE"'], capture_output=True, text=True)
print('Port 7860:', result.stdout.strip())

# Check JupyterLab PID
result = subprocess.run(['pgrep', '-f', 'jupyter-lab'], capture_output=True, text=True)
jpid = result.stdout.strip()
print(f'JupyterLab PID: {jpid}')

# Restart JupyterLab
print('=== Restarting JupyterLab ===')
result = subprocess.run(['kill', '-HUP', jpid], capture_output=True, text=True)
print('Sent HUP to', jpid, 'rc:', result.returncode)

time.sleep(5)

# Check if JupyterLab is back
result = subprocess.run(['pgrep', '-f', 'jupyter-lab'], capture_output=True, text=True)
print('JupyterLab PID after restart:', result.stdout.strip())

# Check port 8888
result = subprocess.run(['bash', '-c', 'ss -tlnp | grep 8888 || echo "Port 8888: NOT LISTENING"'], capture_output=True, text=True)
print('Port 8888:', result.stdout.strip())
"""

msg_id = 'cln'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 60
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
