import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

def run_code(code, msg_id, timeout_sec=120):
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

# Find the model
print('=== Finding model file ===')
run_code("""
import subprocess
r = subprocess.run(['find', '/workspace', '-name', '*.gguf', '-type', 'f'], capture_output=True, text=True, timeout=30)
print(r.stdout or 'No GGUF files found')
""", 'find1', 60)

# Test GPU inference
print('\n=== Testing GPU inference ===')
run_code("""
from llama_cpp import Llama
import time, os, subprocess

# Find model
r = subprocess.run(['find', '/workspace', '-name', '*.gguf', '-type', 'f'], capture_output=True, text=True, timeout=30)
model_path = r.stdout.strip().split(chr(10))[0] if r.stdout.strip() else ''
print(f'Model: {model_path}')

if model_path:
    llm = Llama(
        model_path=model_path,
        n_gpu_layers=-1,
        n_ctx=2048,
        n_batch=4,
        verbose=False,
    )
    print(f'GPU layers: {llm.n_gpu_layers}')
    
    t0 = time.time()
    result = llm('Q: What is 2+2? A:', max_tokens=50)
    elapsed = time.time() - t0
    tokens = result['usage']['completion_tokens']
    print(f'Output: {result["choices"][0]["text"].strip()}')
    print(f'Tokens: {tokens}, Time: {elapsed:.2f}s, Speed: {tokens/elapsed:.1f} tok/s')
    print('GPU INFERENCE WORKING!')
else:
    print('No model found!')
""", 'test1', 120)

ws.close()
print('\nDone!')
