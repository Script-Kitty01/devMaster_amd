import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, socket

# Python socket test
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect(('127.0.0.1', 7860))
    print('Python socket: 127.0.0.1:7860 OPEN')
    s.send(b'GET / HTTP/1.0\\r\\nHost: localhost\\r\\n\\r\\n')
    resp = s.recv(4096)
    print(f'HTTP response: {len(resp)} bytes, starts with: {resp[:100]}')
    s.close()
except Exception as e:
    print(f'Python socket: {e}')

# Check all listening ports
result = subprocess.run(['bash', '-c', 'ss -tlnp 2>/dev/null | head -30'], capture_output=True, text=True)
print('\\nAll listening ports:')
print(result.stdout)

# Check process state
result = subprocess.run(['bash', '-c', 'cat /proc/39794/status 2>/dev/null | head -10'], capture_output=True, text=True)
print('Process state:')
print(result.stdout)

# Check if there's a gradio server file
result = subprocess.run(['bash', '-c', 'ls -la /tmp/gradio/ 2>/dev/null || echo "No /tmp/gradio"'], capture_output=True, text=True)
print('/tmp/gradio:', result.stdout.strip())
"""

msg_id = 'dc2'
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
