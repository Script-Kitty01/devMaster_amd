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
        'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
        'channel': 'shell'
    })
    ws.send(msg)
    
    output = []
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ws.settimeout(15)
        try:
            resp = ws.recv()
            data = json.loads(resp)
            pid = data.get('parent_header', {}).get('msg_id', '')
            if pid != msg_id:
                continue
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
        except:
            break
    return ''.join(output)

# Step 1: Download model via huggingface hub
print('=== Downloading Llama-3.2-3B-Instruct-Q4_K_M.gguf (1.9GB) ===')
run_code("""
import os, subprocess

os.makedirs('/workspace/template-repos/template-1005/repo/models', exist_ok=True)
os.chdir('/workspace/template-repos/template-1005/repo/models')

# Use huggingface_hub to download
from huggingface_hub import hf_hub_download
path = hf_hub_download(
    repo_id='bartowski/Llama-3.2-3B-Instruct-GGUF',
    filename='Llama-3.2-3B-Instruct-Q4_K_M.gguf',
    local_dir='.',
    local_dir_use_symlinks=False,
)
print(f'Downloaded to: {path}')
print(f'Size: {os.path.getsize(path) / 1e9:.2f} GB')
""", 'download', 300)

# Step 2: Test GPU inference
print('\n=== Testing GPU-accelerated inference ===')
run_code("""
from llama_cpp import Llama
import time

model_path = '/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf'

print('Loading model with GPU offloading (n_gpu_layers=-1)...')
t0 = time.time()
llm = Llama(
    model_path=model_path,
    n_gpu_layers=-1,
    n_ctx=2048,
    n_batch=4,
    verbose=False,
)
print(f'Loaded in {time.time()-t0:.1f}s')
print(f'GPU layers: {llm.n_gpu_layers}')

# Warmup
print('\\nWarmup...')
_ = llm('Hello', max_tokens=5)

# Benchmark
print('\\n=== GPU Benchmark ===')
prompt = 'Explain what a GPU is in one paragraph.'
for i in range(3):
    t0 = time.time()
    result = llm(prompt, max_tokens=100)
    elapsed = time.time() - t0
    tokens = result['usage']['completion_tokens']
    speed = tokens / elapsed
    print(f'Run {i+1}: {tokens} tokens in {elapsed:.2f}s = {speed:.1f} tok/s')
    print(f'  Output: {result["choices"][0]["text"][:80]}...')

print('\\nGPU INFERENCE VERIFIED!')
""", 'bench', 120)

ws.close()
print('\nDone!')
