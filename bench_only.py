"""Quick GPU benchmark only."""
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
        ws.settimeout(120)
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
                traceback = '\n'.join(data.get('content', {}).get('traceback', []))
                print(traceback)
                output.append(traceback)
            elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
                break
        except Exception as e:
            print(f'\n[ws: {e}]')
            break
    return ''.join(output)

print('=== GPU Benchmark ===')
result = run_code("""
from llama_cpp import Llama
import time

llm = Llama(model_path='/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf', n_gpu_layers=-1, n_ctx=2048, n_batch=512, verbose=False)
_ = llm('Hello', max_tokens=10)

prompt = 'Explain what a GPU is in one paragraph.'
total_tokens = 0
total_time = 0
for i in range(5):
    t0 = time.time()
    result = llm(prompt, max_tokens=100)
    elapsed = time.time() - t0
    tokens = result['usage']['completion_tokens']
    speed = tokens / elapsed
    total_tokens += tokens
    total_time += elapsed
    print(f'Run {i+1}: {tokens} tok in {elapsed:.2f}s = {speed:.1f} tok/s')

avg = total_tokens / total_time
print(f'\\nGPU: AMD Radeon gfx1100 | ROCm 7.2.1 + HIP BLAS')
print(f'AVG: {avg:.1f} tok/s | ZERO NVIDIA')
""", 'bench', 300)

ws.close()
print('\nDone!')
