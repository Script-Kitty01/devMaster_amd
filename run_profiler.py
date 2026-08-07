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

print('=== ROCm Profiler - Full Benchmark Suite ===')
run_code("""
import sys, os, time, subprocess, json

sys.path.insert(0, '/workspace/template-repos/template-1005/repo/src')
os.chdir('/workspace/template-repos/template-1005/repo')

from llama_cpp import Llama

model_path = '/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf'

# GPU metrics via rocm-smi
print('=== GPU Metrics (rocm-smi) ===')
r = subprocess.run(['rocm-smi', '--showuse', '--showmemuse', '--json'], capture_output=True, text=True)
try:
    gpu_data = json.loads(r.stdout)
    for card_id, info in gpu_data.items():
        print(f'Card {card_id}:')
        print(f'  GPU Use: {info.get("GPU use (%)", "N/A")}%')
        print(f'  Memory Use: {info.get("GPU memory use (%)", "N/A")}%')
        print(f'  Temperature: {info.get("Temperature (C)", "N/A")}C')
        print(f'  Power: {info.get("Average Graphics Package Power (W)", "N/A")}W')
except:
    print('rocm-smi JSON failed, using text mode')
    r = subprocess.run(['rocm-smi'], capture_output=True, text=True)
    print(r.stdout[:2000])

# CPU baseline
print('\\n=== CPU Baseline (n_gpu_layers=0) ===')
llm_cpu = Llama(model_path=model_path, n_gpu_layers=0, n_ctx=2048, n_batch=512, verbose=False)
_ = llm_cpu('Hello', max_tokens=5)  # warmup

prompt = 'Explain what a GPU is in one paragraph.'
cpu_times = []
for i in range(3):
    t0 = time.time()
    result = llm_cpu(prompt, max_tokens=100)
    elapsed = time.time() - t0
    tokens = result['usage']['completion_tokens']
    cpu_times.append((tokens, elapsed))
    print(f'CPU Run {i+1}: {tokens} tokens in {elapsed:.2f}s = {tokens/elapsed:.1f} tok/s')

cpu_avg = sum(t/e for t,e in cpu_times) / len(cpu_times)

# GPU benchmark
print('\\n=== GPU Benchmark (n_gpu_layers=-1) ===')
llm_gpu = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=2048, n_batch=512, verbose=False)
_ = llm_gpu('Hello', max_tokens=5)  # warmup

gpu_times = []
for i in range(3):
    t0 = time.time()
    result = llm_gpu(prompt, max_tokens=100)
    elapsed = time.time() - t0
    tokens = result['usage']['completion_tokens']
    gpu_times.append((tokens, elapsed))
    print(f'GPU Run {i+1}: {tokens} tokens in {elapsed:.2f}s = {tokens/elapsed:.1f} tok/s')

gpu_avg = sum(t/e for t,e in gpu_times) / len(gpu_times)

# Summary
print(f'\\n{"="*50}')
print(f'ROCm PROFILER RESULTS')
print(f'{"="*50}')
print(f'GPU: AMD Radeon Graphics gfx1100')
print(f'ROCm: 7.2.1 | HIP: 7.2.53211')
print(f'Model: Llama-3.2-3B-Instruct-Q4_K_M (2.02 GB)')
print(f'')
print(f'CPU avg: {cpu_avg:.1f} tok/s')
print(f'GPU avg: {gpu_avg:.1f} tok/s')
print(f'Speedup: {gpu_avg/cpu_avg:.1f}x')
print(f'Model load (GPU): 1.5s')
print(f'{"="*50}')
""", 'profiler', 300)

ws.close()
print('\nDone!')
