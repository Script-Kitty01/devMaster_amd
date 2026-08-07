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

# Install gradio
print('=== Installing Gradio ===')
result = subprocess.run(['/opt/venv/bin/pip', 'install', 'gradio'], capture_output=True, text=True, timeout=120)
print('pip rc:', result.returncode)
print(result.stdout[-500:])
if result.stderr:
    print('STDERR:', result.stderr[-500:])

# Verify
result = subprocess.run(['/opt/venv/bin/python', '-c', 'import gradio; print(gradio.__version__)'], capture_output=True, text=True)
print('Gradio version:', result.stdout.strip())

# Try to download frpc using gradio's own mechanism
print('\\n=== Trying gradio frpc download ===')
result = subprocess.run(['/opt/venv/bin/python', '-c', '''
import gradio
from gradio import networking
# Try to trigger frpc download
try:
    networking.setup_tunnel('localhost', 7860, None, None)
except Exception as e:
    print(f"setup_tunnel error: {e}")
'''], capture_output=True, text=True, timeout=60)
print(result.stdout)
print(result.stderr)

# Check if frpc was downloaded
result = subprocess.run(['bash', '-c', 'ls -la /root/.cache/huggingface/gradio/frpc/ 2>/dev/null || echo "No frpc dir"'], capture_output=True, text=True)
print('frpc dir:', result.stdout.strip())
"""

msg_id = 'ias'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 180
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
            print('ERROR:', '\\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
