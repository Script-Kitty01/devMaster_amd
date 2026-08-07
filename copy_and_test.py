"""Copy .so files and test GPU model load"""
import requests, json, time, uuid, urllib3
from websocket import create_connection
urllib3.disable_warnings()

BASE = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
TOKEN = 'amd-oneclick'

r = requests.post(f'{BASE}/api/kernels', headers={'Authorization': f'token {TOKEN}'}, verify=False)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token={TOKEN}'
ws = create_connection(ws_url)
msg = json.loads(ws.recv())

code = """
import subprocess, os, shutil

SRC = '/tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip/bin'
LLAMA_DIR = subprocess.run('python3.12 -c "import llama_cpp; import os; print(os.path.dirname(llama_cpp.__file__))"', shell=True, capture_output=True, text=True, executable='/bin/bash').stdout.strip()
LIB_DIR = LLAMA_DIR + '/lib'

print('LLAMA_DIR:', LLAMA_DIR)
print('LIB_DIR:', LIB_DIR)

# Backup existing
subprocess.run('mkdir -p ' + LIB_DIR + '/backup', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
subprocess.run('cp ' + LIB_DIR + '/*.so* ' + LIB_DIR + '/backup/ 2>/dev/null || true', shell=True, executable='/bin/bash', capture_output=True, timeout=5)

# Copy all .so files
r = subprocess.run('cp -v ' + SRC + '/*.so* ' + LIB_DIR + '/', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== COPY ===')
print(r.stdout)
print(r.stderr)

# List what we have
r = subprocess.run('ls -la ' + LIB_DIR + '/*.so*', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== LIB DIR ===')
print(r.stdout)

# Check HIP symbols in libggml-hip.so
r = subprocess.run('nm -D ' + LIB_DIR + '/libggml-hip.so 2>/dev/null | grep -i hip | head -10', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== HIP SYMBOLS IN libggml-hip.so ===')
print(r.stdout if r.stdout else 'EMPTY')

# Check for hipblas strings
r = subprocess.run('strings ' + LIB_DIR + '/libggml-hip.so | grep -i hipblas | head -10', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== hipBLAS STRINGS ===')
print(r.stdout if r.stdout else 'EMPTY')

# Now test GPU model load
print('\\n=== TESTING GPU MODEL LOAD ===')
test_code = '''
import sys
sys.path.insert(0, "/workspace/template-repos/template-1005/repo")
from llama_cpp import Llama
import os

model_path = "/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
if not os.path.exists(model_path):
    # Try to find any gguf
    import glob
    models = glob.glob("/workspace/**/*.gguf", recursive=True)
    print("Available models:", models)
    if models:
        model_path = models[0]

print(f"Loading: {model_path}")
print(f"n_gpu_layers=-1 (all layers on GPU)")

llm = Llama(
    model_path=model_path,
    n_gpu_layers=-1,
    n_ctx=2048,
    n_batch=512,
    verbose=True
)
print("GPU MODEL LOADED SUCCESSFULLY!")

# Quick test
result = llm("Hello, what is 2+2?", max_tokens=20)
print("Test output:", result["choices"][0]["text"])
'''

with open('/tmp/test_gpu.py', 'w') as f:
    f.write(test_code)

r = subprocess.run('python3.12 /tmp/test_gpu.py', shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash')
print('=== GPU TEST ===')
print(r.stdout[-2000:] if len(r.stdout) > 2000 else r.stdout)
if r.stderr:
    print('STDERR:', r.stderr[-1000:])
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(15)
while True:
    try:
        ws.settimeout(3)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
    except:
        break

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\nDone')
