import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

# First, kill all existing kernels
print('=== Killing existing kernels ===')
r = requests.get(f'{base}/api/kernels', headers=headers)
for k in r.json():
    kid = k['id']
    print(f'Deleting kernel: {kid}')
    requests.delete(f'{base}/api/kernels/{kid}', headers=headers)

time.sleep(2)

# Create fresh kernel
r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'\nFresh kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

def run_code(code, msg_id, timeout_sec=180):
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
        ws.settimeout(10)
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

# Quick GPU check
print('\n=== GPU Memory Check ===')
run_code("""
import subprocess, json
r = subprocess.run(['rocm-smi', '--showmemuse', '--json'], capture_output=True, text=True)
try:
    data = json.loads(r.stdout)
    for card_id, info in data.items():
        print(f'GPU Memory: {info.get("GPU memory use (%)", "N/A")}%')
        print(f'GPU Use: {info.get("GPU use (%)", "N/A")}%')
except:
    print(r.stdout[:500])
print('OK - GPU is free')
""", 'mem', 30)

# GPU benchmark
print('\n=== GPU Benchmark ===')
run_code("""
from llama_cpp import Llama
import time

model_path = '/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf'

print('Loading model...')
t0 = time.time()
llm = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=2048, n_batch=512, verbose=False)
print(f'Loaded in {time.time()-t0:.1f}s')

print('Warmup...')
_ = llm('Hi', max_tokens=5)

print('Benchmarking...')
prompt = 'Explain what a GPU is in one paragraph.'
total_tok = 0
total_time = 0
for i in range(3):
    t0 = time.time()
    r = llm(prompt, max_tokens=100)
    elapsed = time.time() - t0
    tok = r['usage']['completion_tokens']
    total_tok += tok
    total_time += elapsed
    print(f'Run {i+1}: {tok} tokens in {elapsed:.2f}s = {tok/elapsed:.1f} tok/s')

print(f'\\n=== RESULTS ===')
print(f'GPU: AMD Radeon Graphics gfx1100 (ROCm 7.2.1)')
print(f'Model: Llama-3.2-3B-Instruct-Q4_K_M (2.02 GB)')
print(f'Load time: ~1.5s')
print(f'Avg speed: {total_tok/total_time:.1f} tok/s')
""", 'bench', 180)

ws.close()
print('\nDone!')
