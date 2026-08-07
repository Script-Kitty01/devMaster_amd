import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os, time, socket

# First, start Gradio in background
os.chdir('/workspace/template-repos/template-1005/repo')
print('Starting Gradio...')
proc = subprocess.Popen(
    ['/opt/venv/bin/python', '-u', 'src/ui/gradio_app.py'],
    stdout=open('/tmp/gradio_out.log', 'w', buffering=1),
    stderr=open('/tmp/gradio_err.log', 'w', buffering=1),
    env={**os.environ, 'PYTHONUNBUFFERED': '1'},
    cwd='/workspace/template-repos/template-1005/repo'
)
print(f'Gradio PID: {proc.pid}')

# Wait for port 7860
for i in range(30):
    time.sleep(2)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    if s.connect_ex(('127.0.0.1', 7860)) == 0:
        print(f'Port 7860 OPEN after {(i+1)*2}s')
        s.close()
        break
    s.close()
else:
    print('Port 7860 did not open')

# Check Gradio output
with open('/tmp/gradio_out.log') as f:
    print('Gradio stdout:', f.read()[-500:])
with open('/tmp/gradio_err.log') as f:
    err = f.read()
    if err:
        print('Gradio stderr:', err[-500:])

# Now try to access proxy through JupyterLab API
print('\\n=== Testing proxy via JupyterLab API ===')
result = subprocess.run(['bash', '-c', 'curl -s http://localhost:8888/proxy/7860/ -o /dev/null -w "%{http_code}"'], capture_output=True, text=True)
print(f'localhost:8888/proxy/7860/ -> HTTP {result.stdout.strip()}')

# Try with base_url
result = subprocess.run(['bash', '-c', 'curl -s http://localhost:8888/instances/u-14073-bcd85560/proxy/7860/ -o /dev/null -w "%{http_code}"'], capture_output=True, text=True)
print(f'localhost:8888/instances/.../proxy/7860/ -> HTTP {result.stdout.strip()}')

# Check JupyterLab server extensions API
result = subprocess.run(['bash', '-c', 'curl -s http://localhost:8888/api/sessions?token=amd-oneclick 2>/dev/null | head -200'], capture_output=True, text=True)
print('Sessions API:', result.stdout[:300])

# Check if there's a proxy servers list
result = subprocess.run(['bash', '-c', 'curl -s http://localhost:8888/server-proxy/servers 2>/dev/null || echo "No server-proxy API"'], capture_output=True, text=True)
print('Server-proxy API:', result.stdout[:300])
"""

msg_id = 'sa'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 90
while time.time() < deadline:
    ws.settimeout(15)
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
