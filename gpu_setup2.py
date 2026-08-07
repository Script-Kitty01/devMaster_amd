import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

def run_code(code, msg_id, timeout_sec=300):
    msg = json.dumps({
        'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
        'parent_header': {}, 'metadata': {},
        'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
        'channel': 'shell'
    })
    ws.send(msg)
    
    output = []
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ws.settimeout(10)
        try:
            resp = ws.recv()
            data = json.loads(resp)
            pid = data.get('parent_header', {}).get('msg_id', '')
            if pid != msg_id:
                continue
            if data.get('msg_type') == 'stream':
                output.append(data.get('content', {}).get('text', ''))
            elif data.get('msg_type') == 'execute_result':
                output.append(data.get('content', {}).get('data', {}).get('text/plain', ''))
            elif data.get('msg_type') == 'error':
                output.append(f"ERROR: {data.get('content', {}).get('ename', '')}: {data.get('content', {}).get('evalue', '')}")
            elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
                break
        except:
            break
    return ''.join(output)

# Step 1: Check current llama-cpp status
print('\n=== Current llama-cpp status ===')
print(run_code("""
try:
    import llama_cpp
    print('llama_cpp version:', llama_cpp.__version__)
    # Check if it has GPU support
    from llama_cpp import Llama
    print('Llama class available')
except Exception as e:
    print('llama_cpp not installed or broken:', e)
""", 's1', 30))

# Step 2: Install with correct GPU target (gfx1100)
print('\n=== Installing llama-cpp-python with ROCm for gfx1100 ===')
print(run_code("""
import subprocess, os, sys

os.environ['ROCM_PATH'] = '/opt/rocm'
os.environ['HIP_PLATFORM'] = 'amd'

cmd = [
    sys.executable, '-m', 'pip', 'install', 'llama-cpp-python',
    '--force-reinstall', '--no-cache-dir', '--break-system-packages',
    '-C', 'cmake.args="-DGGML_HIPBLAS=on;-DCMAKE_C_COMPILER=/opt/rocm/bin/hipcc;-DCMAKE_CXX_COMPILER=/opt/rocm/bin/hipcc;-DAMDGPU_TARGETS=gfx1100"'
]

print('Running install (this may take 5-10 min)...')
r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
# Print last 2000 chars of stdout
out = r.stdout
if len(out) > 2000:
    out = '...(truncated)...\\n' + out[-2000:]
print(out)
if r.stderr:
    err_lines = [l for l in r.stderr.split(chr(10)) if 'error' in l.lower() or 'fail' in l.lower() or 'warning' in l.lower()]
    if err_lines:
        print('\\nSTDERR (filtered):')
        for l in err_lines[-10:]:
            print(l)
print('\\nReturn code:', r.returncode)
""", 's2', 600))

# Step 3: Verify GPU llama-cpp works
print('\n=== Verify GPU llama-cpp ===')
print(run_code("""
from llama_cpp import Llama

model_path = '/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf'

import os
print('Model exists:', os.path.exists(model_path))

llm = Llama(
    model_path=model_path,
    n_gpu_layers=-1,
    n_ctx=2048,
    n_batch=4,
    verbose=False,
)

print('Model loaded successfully!')
print('GPU layers:', llm.n_gpu_layers)

# Quick inference test
import time
t0 = time.time()
result = llm('Q: What is 2+2? A:', max_tokens=50)
elapsed = time.time() - t0
tokens = result['usage']['completion_tokens']
print(f'Output: {result["choices"][0]["text"].strip()}')
print(f'Tokens: {tokens}, Time: {elapsed:.2f}s, Speed: {tokens/elapsed:.1f} tok/s')
""", 's3', 60))

ws.close()
print('\nDone!')
