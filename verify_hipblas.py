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
import subprocess, os

# Check for hipblas lib
result = subprocess.run(["find", "/opt/venv", "-name", "*hipblas*", "-o", "-name", "*hip*ggml*"], capture_output=True, text=True)
print("HIPBLAS libs:")
print(result.stdout or "NONE FOUND")

# Check llama_cpp lib dir
import llama_cpp
lib_dir = os.path.dirname(llama_cpp.__file__) + "/lib"
print(f"Lib dir: {os.listdir(lib_dir)}")

# Try loading with GPU
import sys
sys.path.insert(0, "/workspace/template-repos/template-1005/repo")
os.chdir("/workspace/template-repos/template-1005/repo")

from llama_cpp import Llama
model_path = "models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
print(f"\\nLoading model with n_gpu_layers=-1...")
try:
    llm = Llama(
        model_path=model_path,
        n_gpu_layers=-1,
        n_ctx=2048,
        n_batch=512,
        verbose=True,
    )
    print("GPU LOAD SUCCESS!")
except Exception as e:
    print(f"FAILED: {e}")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(30)
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
print('\nDone')
