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

# Check if ROCm/HIP SDK is available for building
print("=== ROCm SDK ===")
result = subprocess.run(["which", "hipcc"], capture_output=True, text=True)
print(f"hipcc: {result.stdout.strip() or 'NOT FOUND'}")

result = subprocess.run(["which", "rocm-smi"], capture_output=True, text=True)
print(f"rocm-smi: {result.stdout.strip() or 'NOT FOUND'}")

# Check cmake
result = subprocess.run(["which", "cmake"], capture_output=True, text=True)
print(f"cmake: {result.stdout.strip() or 'NOT FOUND'}")

# Check HIP includes
result = subprocess.run(["ls", "/opt/rocm/include/hip/"], capture_output=True, text=True)
print(f"HIP includes: {result.stdout[:200]}")

# Check if we can find a pre-built wheel with HIPBLAS
result = subprocess.run(["/opt/venv/bin/pip", "list"], capture_output=True, text=True)
for line in result.stdout.split(chr(10)):
    if "llama" in line.lower():
        print(f"Installed: {line}")

# Check if there's a cached wheel
result = subprocess.run(["find", "/root/.cache", "-name", "*llama*hip*", "-o", "-name", "*llama*rocm*"], capture_output=True, text=True)
print(f"Cached HIP wheels: {result.stdout[:500] or 'NONE'}")

# Check GPU arch
result = subprocess.run(["/opt/rocm/bin/rocminfo"], capture_output=True, text=True)
for line in result.stdout.split(chr(10)):
    if "gfx" in line.lower() or "Name:" in line:
        print(f"rocminfo: {line.strip()}")
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
