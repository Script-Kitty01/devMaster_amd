import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, socket, os

# Check Gradio
result = subprocess.run(['pgrep', '-f', 'gradio_app'], capture_output=True, text=True)
print('Gradio PID:', result.stdout.strip())

# Check port 7860
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
if s.connect_ex(('127.0.0.1', 7860)) == 0:
    print('Port 7860: OPEN')
    s.send(b'GET / HTTP/1.0\\r\\nHost: localhost\\r\\n\\r\\n')
    resp = s.recv(1024)
    print(f'HTTP: {resp[:100]}')
else:
    print('Port 7860: CLOSED')
s.close()

# Check Gradio output
for f in ['/tmp/gradio_out.log', '/tmp/gradio_err.log']:
    try:
        with open(f) as fh:
            content = fh.read()
        print(f'\\n{f} ({len(content)} bytes):')
        print(content[-1000:])
    except:
        print(f'{f}: not found')

# Check JupyterLab
result = subprocess.run(['pgrep', '-f', 'jupyter-lab'], capture_output=True, text=True)
print('\\nJupyterLab PID:', result.stdout.strip())

# Test proxy from localhost
result = subprocess.run(['bash', '-c', 'curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/proxy/7860/ 2>/dev/null'], capture_output=True, text=True)
print(f'localhost proxy: HTTP {result.stdout.strip()}')
"""

msg_id = 'ca'
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
