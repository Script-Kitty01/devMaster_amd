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

# Find frpc in gradio package
result = subprocess.run(['bash', '-c', 'find /opt/venv -name "frpc*" -type f 2>/dev/null'], capture_output=True, text=True)
print('frpc in venv:', result.stdout.strip())

# Check gradio package for frpc
result = subprocess.run(['bash', '-c', 'python3 -c "import gradio; print(gradio.__file__)"'], capture_output=True, text=True)
print('Gradio location:', result.stdout.strip())

# Look for frpc in gradio package
result = subprocess.run(['bash', '-c', 'find /opt/venv/lib/python3.12/site-packages/gradio -name "*frpc*" 2>/dev/null'], capture_output=True, text=True)
print('frpc in gradio pkg:', result.stdout.strip())

# Try to get frpc from gradio's networking module
result = subprocess.run(['bash', '-c', 'python3 -c "from gradio import networking; print(dir(networking))" 2>&1'], capture_output=True, text=True)
print('gradio.networking:', result.stdout.strip())

# Check if there's a frpc download function in gradio
result = subprocess.run(['bash', '-c', 'grep -r "frpc" /opt/venv/lib/python3.12/site-packages/gradio/ --include="*.py" -l 2>/dev/null'], capture_output=True, text=True)
print('Files mentioning frpc:', result.stdout.strip())

# Check one of those files
if result.stdout.strip():
    for f in result.stdout.strip().split('\\n')[:3]:
        with open(f) as fh:
            content = fh.read()
        print(f'\\n=== {f} ===')
        # Find lines with frpc
        for i, line in enumerate(content.split('\\n')):
            if 'frpc' in line.lower():
                print(f'  L{i}: {line.strip()[:150]}')
"""

msg_id = 'ff'
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
