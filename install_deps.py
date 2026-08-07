import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print('Kernel:', kid)

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, sys

# Install all missing deps
pkgs = ['langchain-core', 'langgraph', 'langchain-community', 'chromadb', 'sentence-transformers']
for pkg in pkgs:
    print(f'Installing {pkg}...')
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', pkg, '--break-system-packages', '-q'], capture_output=True, text=True, timeout=120)
    if r.returncode == 0:
        print(f'  OK: {pkg}')
    else:
        print(f'  FAIL: {pkg} - {r.stderr[-200:]}')

# Verify
for pkg in pkgs:
    r = subprocess.run([sys.executable, '-c', f'import {pkg.replace("-","_")}; print("  OK:", {pkg.replace("-","_")}.__version__ if hasattr({pkg.replace("-","_")}, "__version__") else "imported")'], capture_output=True, text=True)
    print(r.stdout.strip() or f'  FAIL: {pkg} - {r.stderr.strip()[:100]}')
"""

msg = json.dumps({
    'header': {'msg_id': 'deps1', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

timeout = time.time() + 180
while time.time() < timeout:
    ws.settimeout(10)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'deps1':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'deps1':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'deps1':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'deps1':
            break
    except:
        break
ws.close()
print('---DONE---')
