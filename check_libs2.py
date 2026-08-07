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

# Check all ggml libs
result = subprocess.run(["find", "/opt/venv", "-name", "libggml*"], capture_output=True, text=True)
print("All ggml libs:")
for line in sorted(result.stdout.strip().split(chr(10))):
    print(f"  {line}")

# Check if hipblas lib exists
result = subprocess.run(["find", "/opt/venv", "-name", "*hip*"], capture_output=True, text=True)
print(f"\\nHIP files: {result.stdout[:500] or 'NONE'}")

# Check the actual libggml.so to see what it links to
result = subprocess.run(["ldd", "/opt/venv/lib/python3.12/site-packages/llama_cpp/lib/libggml.so"], capture_output=True, text=True)
print(f"\\nlibggml.so links:")
for line in result.stdout.split(chr(10)):
    if "hip" in line.lower() or "rocm" in line.lower() or "amd" in line.lower():
        print(f"  {line}")

# Check libllama.so links
result = subprocess.run(["ldd", "/opt/venv/lib/python3.12/site-packages/llama_cpp/lib/libllama.so"], capture_output=True, text=True)
print(f"\\nlibllama.so links (hip/rocm):")
for line in result.stdout.split(chr(10)):
    if "hip" in line.lower() or "rocm" in line.lower() or "amd" in line.lower() or "ggml" in line.lower():
        print(f"  {line}")
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
