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

os.chdir('/workspace/template-repos/template-1005/repo')

# Test loading the model with GPU offloading
test_code = '''
import sys
sys.path.insert(0, ".")
import time

print("Loading ROCmLLM...")
from src.llm.rocm_service import ROCmLLM

llm = ROCmLLM.get_instance()
print("Initializing...")
t0 = time.time()
llm.initialize()
t1 = time.time()
print(f"Init took {t1-t0:.1f}s")
print(f"Backend: {llm.backend}")
print(f"Is ready: {llm.is_ready}")

# Check GPU layers
if hasattr(llm, '_model') and llm._model:
    print(f"Model loaded: {llm._model}")
    if hasattr(llm._model, 'n_gpu_layers'):
        print(f"n_gpu_layers: {llm._model.n_gpu_layers}")

# Try a quick generation
print("\\nGenerating test...")
t0 = time.time()
result = llm.generate("Hello, what is 2+2?")
t1 = time.time()
print(f"Result: {result.text[:200]}")
print(f"Tokens: {result.tokens_generated}, Speed: {result.tokens_per_second:.1f} tok/s")
print(f"Time: {t1-t0:.1f}s")
'''

r = subprocess.run(['/opt/venv/bin/python', '-c', test_code],
                   capture_output=True, text=True, cwd='/workspace/template-repos/template-1005/repo', timeout=120)
print('STDOUT:')
print(r.stdout[-2000:])
if r.stderr:
    print('STDERR (last 1000 chars):')
    print(r.stderr[-1000:])
"""

msg_id = 'cllm'
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
