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

print('Installing langchain-core and langgraph...')

r = subprocess.run(
    ['/opt/venv/bin/pip', 'install', 'langchain-core', 'langgraph'],
    capture_output=True, text=True, timeout=120
)
print(r.stdout[-800:] if len(r.stdout) > 800 else r.stdout)
if r.returncode != 0:
    print('STDERR:', r.stderr[-500:])

print('\n--- Verification ---')
r = subprocess.run(['/opt/venv/bin/python', '-c', 'import langchain_core; print("langchain_core:", langchain_core.__version__)'],
                   capture_output=True, text=True)
print(r.stdout.strip() or 'FAILED: ' + r.stderr.strip())

r = subprocess.run(['/opt/venv/bin/python', '-c', 'import langgraph; print("langgraph OK")'],
                   capture_output=True, text=True)
print(r.stdout.strip() or 'FAILED: ' + r.stderr.strip())
"""

msg_id = 'ilc'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 150
while time.time() < deadline:
    ws.settimeout(30)
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
