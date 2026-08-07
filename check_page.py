import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess

# Check local Gradio
r = subprocess.run(['curl', '-s', 'http://localhost:7860'], capture_output=True, text=True, timeout=10)
html = r.stdout
print('HTML length:', len(html))

# Check for key Gradio markers
checks = ['gr-box', 'gradio-app', 'gradio-container', 'chatbot', 'textarea', 'input']
for c in checks:
    if c in html:
        print('FOUND:', c)
    else:
        print('MISSING:', c)

# Check for errors
for line in html.split('\n'):
    low = line.lower()
    if 'error' in low or 'traceback' in low or 'exception' in low or 'fail' in low:
        print('ERR:', line[:200])

# Check the Gradio process stderr (if any was captured)
print('\n--- Process check ---')
r = subprocess.run(['cat', '/proc/4620/cmdline'], capture_output=True, text=True)
print('Cmdline:', r.stdout.replace(chr(0), ' '))

# Check if there's a wrapper or proxy issue
r = subprocess.run(['curl', '-s', '-I', 'http://localhost:7860'], capture_output=True, text=True, timeout=10)
print('\nHeaders:')
for line in r.stdout.split('\n')[:15]:
    print(line)
"""

msg_id = 'cp'
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
            print('ERROR:', '\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
