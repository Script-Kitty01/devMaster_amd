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

# Check if HIP libraries are available
r = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True)
for line in r.stdout.split('\n'):
    if 'hip' in line.lower() or 'rocm' in line.lower() or 'amd' in line.lower():
        print('LIB:', line.strip())

# Check rocminfo
r = subprocess.run(['rocminfo'], capture_output=True, text=True)
for line in r.stdout.split('\n'):
    if 'Name:' in line or 'Marketing' in line or 'Compute' in line or 'gfx' in line:
        print('ROCm:', line.strip())

# Check if llama.cpp was compiled with HIP
import llama_cpp
print('\nllama_cpp version:', llama_cpp.__version__)
print('llama_cpp file:', llama_cpp.__file__)

# Check the library for HIP symbols
lib_path = os.path.join(os.path.dirname(llama_cpp.__file__), 'lib')
print('lib dir:', lib_path)
if os.path.exists(lib_path):
    for f in os.listdir(lib_path):
        print('  ', f)

# Try to detect backend from llama
from llama_cpp import Llama
os.chdir('/workspace/template-repos/template-1005/repo')
llm = Llama(
    model_path='models/Llama-3.2-3B-Instruct-Q4_K_M.gguf',
    n_gpu_layers=-1,
    n_ctx=2048,
    n_batch=512,
    verbose=True,
)
print('\nMetadata:', llm.metadata)
print('n_gpu_layers:', llm.n_gpu_layers)

# Check if GPU is actually being used via rocm-smi
r = subprocess.run(['rocm-smi', '--showuse'], capture_output=True, text=True, timeout=10)
print('\nrocm-smi GPU usage:')
print(r.stdout[:500])
"""

msg_id = 'ch'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 60
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
            print('ERROR:', '\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
