import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

def run_code(code, msg_id, timeout_sec=600):
    msg = json.dumps({
        'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
        'parent_header': {}, 'metadata': {},
        'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
        'channel': 'shell'
    })
    ws.send(msg)
    
    output = []
    deadline = time.time() + timeout_sec
    last_data_time = time.time()
    while time.time() < deadline:
        ws.settimeout(30)
        try:
            resp = ws.recv()
            data = json.loads(resp)
            pid = data.get('parent_header', {}).get('msg_id', '')
            if pid != msg_id:
                continue
            last_data_time = time.time()
            if data.get('msg_type') == 'stream':
                text = data.get('content', {}).get('text', '')
                output.append(text)
                print(text, end='', flush=True)
            elif data.get('msg_type') == 'execute_result':
                text = data.get('content', {}).get('data', {}).get('text/plain', '')
                output.append(text)
                print(text)
            elif data.get('msg_type') == 'error':
                text = f"\nERROR: {data.get('content', {}).get('ename', '')}: {data.get('content', {}).get('evalue', '')}"
                output.append(text)
                print(text)
            elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
                break
        except Exception as e:
            # If no data for 60s, check if still connected
            if time.time() - last_data_time > 60:
                print(f'\n[No output for 60s, still waiting...]')
                last_data_time = time.time()
    return ''.join(output)

# Install with streaming output
print('=== Installing llama-cpp-python with ROCm HIP BLAS ===')
print('This compiles C++ HIP kernels — may take 5-10 minutes...\n')

result = run_code("""
import subprocess, os, sys

os.environ['ROCM_PATH'] = '/opt/rocm'
os.environ['HIP_PLATFORM'] = 'amd'

cmd = [
    sys.executable, '-m', 'pip', 'install', 'llama-cpp-python',
    '--force-reinstall', '--no-cache-dir', '--break-system-packages',
    '-C', 'cmake.args="-DGGML_HIPBLAS=on;-DCMAKE_C_COMPILER=/opt/rocm/bin/hipcc;-DCMAKE_CXX_COMPILER=/opt/rocm/bin/hipcc;-DAMDGPU_TARGETS=gfx1100"'
]

proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
for line in proc.stdout:
    print(line, end='')
proc.wait()
print(f'\\nReturn code: {proc.returncode}')
""", 'install1', 600)

print('\n\n=== Verifying GPU llama-cpp ===')
result2 = run_code("""
from llama_cpp import Llama
import time, os

model_path = '/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf'
print('Model exists:', os.path.exists(model_path))

llm = Llama(
    model_path=model_path,
    n_gpu_layers=-1,
    n_ctx=2048,
    n_batch=4,
    verbose=False,
)

print('Model loaded! GPU layers:', llm.n_gpu_layers)

# Benchmark
t0 = time.time()
result = llm('Q: What is 2+2? A:', max_tokens=50)
elapsed = time.time() - t0
tokens = result['usage']['completion_tokens']
print(f'Output: {result["choices"][0]["text"].strip()}')
print(f'Tokens: {tokens}, Time: {elapsed:.2f}s, Speed: {tokens/elapsed:.1f} tok/s')
print('GPU INFERENCE WORKING!')
""", 'verify1', 60)

ws.close()
print('\nDone!')
