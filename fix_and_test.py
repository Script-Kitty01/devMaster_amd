"""Fix lib copy and test GPU"""
import requests, json, time, uuid, urllib3
from websocket import create_connection
urllib3.disable_warnings()

BASE = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
TOKEN = 'amd-oneclick'

r = requests.post(f'{BASE}/api/kernels', headers={'Authorization': f'token {TOKEN}'}, verify=False)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token={TOKEN}'
ws = create_connection(ws_url)
msg = json.loads(ws.recv())

code = """
import subprocess, os

SRC = '/tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip/bin'

# Find llama_cpp module location using the venv python
r = subprocess.run('/opt/venv/bin/python -c "import llama_cpp; import os; print(os.path.dirname(llama_cpp.__file__))"', shell=True, capture_output=True, text=True, executable='/bin/bash')
LLAMA_DIR = r.stdout.strip()
print('LLAMA_DIR:', LLAMA_DIR)

if not LLAMA_DIR:
    # Try to find it
    r = subprocess.run('find /opt/venv -name "llama_cpp" -type d 2>/dev/null', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print('Find result:', r.stdout)
    r2 = subprocess.run('find /opt/venv -path "*/llama_cpp/__init__.py" 2>/dev/null', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print('Init files:', r2.stdout)
    # Try pip show
    r3 = subprocess.run('/opt/venv/bin/pip show llama-cpp-python 2>/dev/null', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print('pip show:', r3.stdout)

# Also check sys.path
r = subprocess.run('/opt/venv/bin/python -c "import sys; print(chr(10).join(sys.path))"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('sys.path:', r.stdout[:500])
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(5)
while True:
    try:
        ws.settimeout(3)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
    except:
        break

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\nDone')
