import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess, os

# Check if Gradio process is running
r = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in r.stdout.split('\n'):
    if 'gradio' in line.lower() or 'frpc' in line.lower():
        print('PROC:', line[:200])

# Check port 7860
r = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True)
for line in r.stdout.split('\n'):
    if '7860' in line:
        print('PORT:', line)

# Try to curl the local Gradio
r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'http://localhost:7860'], 
                   capture_output=True, text=True, timeout=10)
print('Local curl status:', r.stdout.strip())

# Check for errors in Gradio output
r = subprocess.run(['curl', '-s', 'http://localhost:7860'], capture_output=True, text=True, timeout=10)
html = r.stdout
print('HTML length:', len(html))
# Check for error messages in HTML
for line in html.split('\n'):
    if 'error' in line.lower() or 'traceback' in line.lower() or 'exception' in line.lower():
        print('ERROR LINE:', line[:200])

# Check if the page has actual content
if 'gradio' in html.lower():
    print('Gradio content found in HTML')
else:
    print('NO Gradio content in HTML!')
    print('First 500 chars:', html[:500])
"""

msg_id = 'dui'
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
