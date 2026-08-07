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

print('=== Quick CPU vs GPU Benchmark ===')
run_code("""
from llama_cpp import Llama
import time

model_path = '/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf'

# GPU test (already known fast)
print('GPU (n_gpu_layers=-1):')
llm_gpu = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=512, n_batch=512, verbose=False)
_ = llm_gpu('Hi', max_tokens=5)

prompt = 'What is 2+2? Answer briefly.'
t0 = time.time()
r = llm_gpu(prompt, max_tokens=30)
gpu_time = time.time() - t0
gpu_tok = r['usage']['completion_tokens']
print(f'  {gpu_tok} tokens in {gpu_time:.2f}s = {gpu_tok/gpu_time:.1f} tok/s')

# CPU test with very short prompt
print('\\nCPU (n_gpu_layers=0):')
llm_cpu = Llama(model_path=model_path, n_gpu_layers=0, n_ctx=512, n_batch=512, verbose=False)
_ = llm_cpu('Hi', max_tokens=5)

t0 = time.time()
r = llm_cpu(prompt, max_tokens=30)
cpu_time = time.time() - t0
cpu_tok = r['usage']['completion_tokens']
print(f'  {cpu_tok} tokens in {cpu_time:.2f}s = {cpu_tok/cpu_time:.1f} tok/s')

print(f'\\nSpeedup: {cpu_time/gpu_time:.1f}x faster on GPU')
print(f'GPU: {gpu_tok/gpu_time:.1f} tok/s vs CPU: {cpu_tok/cpu_time:.1f} tok/s')
""", 'bench', 300)

ws.close()
print('\nDone!')
