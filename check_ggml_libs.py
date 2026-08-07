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

# Find all ggml libs
result = subprocess.run(["find", "/opt/venv", "-name", "libggml*"], capture_output=True, text=True)
print("All ggml libs:")
print(result.stdout)

# Check llama_cpp package info
result = subprocess.run(["/opt/venv/bin/pip", "show", "llama-cpp-python"], capture_output=True, text=True)
print("llama-cpp-python info:")
print(result.stdout)

# Check if HIPBLAS is available
import llama_cpp
print(f"llama_cpp.__file__: {llama_cpp.__file__}")

# Check what backends are compiled in
lib_dir = os.path.dirname(llama_cpp.__file__) + "/lib"
if os.path.exists(lib_dir):
    print(f"Lib dir contents: {os.listdir(lib_dir)}")

# Check Gradio process maps for hip/rocm
result = subprocess.run(["pgrep", "-f", "gradio_app"], capture_output=True, text=True)
gpid = result.stdout.strip()
result = subprocess.run(["grep", "-i", "hip\\|rocm\\|kfd", f"/proc/{gpid}/maps"], capture_output=True, text=True)
if result.stdout.strip():
    print(f"HIP/ROCm in Gradio maps: {result.stdout[:500]}")
else:
    print("NO HIP/ROCm in Gradio maps!")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(5)
while True:
    try:
        ws.settimeout(2)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
    except:
        break
ws.close()
print('\nDone')
