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
gpid = result.stdout.strip()
print(f"Gradio PID: {gpid}")

# Check all open FDs for model file
result = subprocess.run(["ls", "-la", f"/proc/{gpid}/fd/"], capture_output=True, text=True)
print("All FDs:")
print(result.stdout)

# Check memory maps for model
result = subprocess.run(["grep", "-i", "gguf\|llama\|model", f"/proc/{gpid}/maps"], capture_output=True, text=True)
if result.stdout.strip():
    print("Model in maps:")
    print(result.stdout[:1000])
else:
    print("No model in maps")

# Check RSS memory
result = subprocess.run(["grep", "VmRSS", f"/proc/{gpid}/status"], capture_output=True, text=True)
print(f"Memory: {result.stdout.strip()}")

# Check if any process has the model file open
result = subprocess.run(["fuser", "/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"], capture_output=True, text=True)
print(f"Model file users: {result.stdout.strip()}")
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
