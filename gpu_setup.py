import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

def run_code(code, msg_id):
    msg = json.dumps({
        'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
        'parent_header': {}, 'metadata': {},
        'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
        'channel': 'shell'
    })
    ws.send(msg)
    
    output = []
    timeout = time.time() + 120
    while time.time() < timeout:
        ws.settimeout(5)
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

# Step 1: Check GPU
print('\n=== GPU Check ===')
print(run_code("""
import subprocess, os
print('rocm-smi:')
r = subprocess.run(['rocm-smi', '--showproductname'], capture_output=True, text=True, timeout=10)
print(r.stdout[:500] or r.stderr[:500])

print('\\nrocminfo (agent count):')
r = subprocess.run(['rocminfo'], capture_output=True, text=True, timeout=10)
for line in r.stdout.split(chr(10)):
    if 'Agent' in line or 'Name:' in line:
        print(line.strip())

print('\\nhipconfig:')
r = subprocess.run(['hipconfig', '--full'], capture_output=True, text=True, timeout=10)
print(r.stdout[:500] or r.stderr[:500])
""", 'gpu1'))

# Step 2: Install ROCm llama-cpp-python
print('\n=== Installing llama-cpp-python with ROCm/HIP BLAS ===')
print(run_code("""
import subprocess, os, sys

# Set ROCm path
os.environ['ROCM_PATH'] = '/opt/rocm'
os.environ['HIP_PLATFORM'] = 'amd'

cmd = [
    sys.executable, '-m', 'pip', 'install', 'llama-cpp-python',
    '--force-reinstall', '--no-cache-dir', '--break-system-packages',
    '-C', 'cmake.args="-DGGML_HIPBLAS=on;-DCMAKE_C_COMPILER=/opt/rocm/bin/hipcc;-DCMAKE_CXX_COMPILER=/opt/rocm/bin/hipcc;-DAMDGPU_TARGETS=gfx942"'
]

print('Running:', ' '.join(cmd))
r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
print(r.stdout[-1000:] if r.stdout else '')
if r.stderr:
    # Filter common non-error stderr
    for line in r.stderr.split(chr(10))[-20:]:
        if 'error' in line.lower() or 'fail' in line.lower():
            print('STDERR:', line)
print('Return code:', r.returncode)
""", 'gpu2'))

# Step 3: Verify GPU llama-cpp works
print('\n=== Verify GPU llama-cpp ===')
print(run_code("""
from llama_cpp import Llama
import os

model_path = '/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf'

llm = Llama(
    model_path=model_path,
    n_gpu_layers=-1,
    n_ctx=2048,
    n_batch=4,
    verbose=False,
)

print('Model loaded. Testing inference...')
result = llm('Q: What is 2+2? A:', max_tokens=50)
print('Output:', result['choices'][0]['text'])
print('GPU layers used:', llm.n_gpu_layers)
""", 'gpu3'))

ws.close()
print('\nDone!')
