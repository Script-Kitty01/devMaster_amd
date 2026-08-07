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

# Get Gradio PID
result = subprocess.run(["pgrep", "-f", "gradio_app"], capture_output=True, text=True)
gpid = result.stdout.strip()

# Get kernel's own PID
kpid = str(os.getpid())

print(f"Kernel PID: {kpid}")
print(f"Gradio PID: {gpid}")

# Compare environments
for label, pid in [("KERNEL", kpid), ("GRADIO", gpid)]:
    result = subprocess.run(["cat", f"/proc/{pid}/environ"], capture_output=True, text=True)
    env_vars = {}
    for var in result.stdout.split(chr(0)):
        if "=" in var:
            k, v = var.split("=", 1)
            env_vars[k] = v
    
    # Check key vars
    for key in ["LD_LIBRARY_PATH", "PATH", "LD_PRELOAD", "HIP_VISIBLE_DEVICES", 
                "CUDA_VISIBLE_DEVICES", "HSA_OVERRIDE_GFX_VERSION", "GGML_HIPBLAS_PATH",
                "GGML_CUDA_NO_PINNED", "ROCR_VISIBLE_DEVICES"]:
        val = env_vars.get(key, "NOT SET")
        print(f"{label} {key}={val[:200] if len(val) > 200 else val}")
    
    print()
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
