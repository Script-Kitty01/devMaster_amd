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
import subprocess

# Find gradio PID
result = subprocess.run(["pgrep", "-f", "gradio_app"], capture_output=True, text=True)
pid = result.stdout.strip()
print(f"Gradio PID: {pid}")

# Check /proc/PID/fd for model file
result = subprocess.run(["ls", "-la", f"/proc/{pid}/fd/"], capture_output=True, text=True)
for line in result.stdout.split(chr(10)):
    if "Llama" in line or "gguf" in line or ".gguf" in line:
        print(f"MODEL FD: {line}")

# Check if model is loaded via /proc/PID/maps
result = subprocess.run(["grep", "-c", "kfd", f"/proc/{pid}/maps"], capture_output=True, text=True)
kfd_count = result.stdout.strip()
print(f"KFD mappings: {kfd_count}")

# Check /proc/PID/maps for large allocations
result = subprocess.run(["grep", "kfd", f"/proc/{pid}/maps"], capture_output=True, text=True)
if result.stdout.strip():
    print(f"KFD maps: {result.stdout[:500]}")

# Check the Gradio process's /proc/PID/environ for HIP vars
result = subprocess.run(["cat", f"/proc/{pid}/environ"], capture_output=True, text=True)
env_vars = result.stdout.split(chr(0))
for var in env_vars:
    if "HIP" in var or "ROCM" in var or "HSA" in var:
        print(f"ENV: {var}")
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
