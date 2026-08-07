"""Copy to correct lib dir and test GPU"""
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
LIB_DIR = '/opt/venv/lib/python3.12/site-packages/llama_cpp/lib'

# Backup
subprocess.run('mkdir -p ' + LIB_DIR + '/backup', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
subprocess.run('cp ' + LIB_DIR + '/*.so* ' + LIB_DIR + '/backup/ 2>/dev/null || true', shell=True, executable='/bin/bash', capture_output=True, timeout=5)

# Copy new HIP .so files
r = subprocess.run('cp -v ' + SRC + '/*.so* ' + LIB_DIR + '/', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== COPY ===')
print(r.stdout)

# List
r = subprocess.run('ls -la ' + LIB_DIR + '/libggml* ' + LIB_DIR + '/libllama*', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== LIBS ===')
print(r.stdout)

# Test GPU with venv python
print('\\n=== TESTING GPU ===')
test_code = '''
import sys
sys.path.insert(0, "/workspace/template-repos/template-1005/repo")
from llama_cpp import Llama
import os

model_path = "/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
print(f"Loading: {model_path}")
print("n_gpu_layers=-1")

llm = Llama(
    model_path=model_path,
    n_gpu_layers=-1,
    n_ctx=2048,
    n_batch=512,
    verbose=True
)
print("GPU MODEL LOADED SUCCESSFULLY!")

result = llm("Hello, what is 2+2?", max_tokens=20)
print("Test output:", result["choices"][0]["text"])
'''

with open('/tmp/test_gpu2.py', 'w') as f:
    f.write(test_code)

r = subprocess.run('/opt/venv/bin/python /tmp/test_gpu2.py', shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash')
print('STDOUT:')
print(r.stdout[-3000:] if len(r.stdout) > 3000 else r.stdout)
if r.stderr:
    print('STDERR:')
    print(r.stderr[-2000:])
print('RC:', r.returncode)
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(20)
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
