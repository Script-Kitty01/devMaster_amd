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

# Find gradio PID
result = subprocess.run(["pgrep", "-f", "gradio_app"], capture_output=True, text=True)
pids = result.stdout.strip().split()
print(f"Gradio PIDs: {pids}")

for pid in pids:
    # Check open files for model
    result = subprocess.run(["ls", "-la", f"/proc/{pid}/fd/"], capture_output=True, text=True)
    for line in result.stdout.split(chr(10)):
        if "Llama" in line or "gguf" in line or "model" in line.lower():
            print(f"PID {pid}: {line}")
    
    # Check /proc/pid/maps for GPU memory
    result = subprocess.run(["grep", "-i", "kfd", f"/proc/{pid}/maps"], capture_output=True, text=True)
    if result.stdout.strip():
        print(f"PID {pid} has KFD mappings (GPU): {result.stdout[:500]}")

# Also check if any process has the model file open
result = subprocess.run(["lsof", "/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"], capture_output=True, text=True)
print(f"Model file open by: {result.stdout[:500] if result.stdout else 'NOTHING'}")

# Check stderr
result = subprocess.run(["cat", "/tmp/gradio_stderr.log"], capture_output=True, text=True)
if result.stdout.strip():
    print(f"STDERR: {result.stdout[-2000:]}")
else:
    print("No stderr log")
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
