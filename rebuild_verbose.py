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

# First check what the previous build did
result = subprocess.run(["/opt/venv/bin/pip", "show", "llama-cpp-python"], capture_output=True, text=True)
print(result.stdout)

# Check if there's a build log
result = subprocess.run(["find", "/tmp", "-name", "*llama*", "-o", "-name", "*cmake*"], capture_output=True, text=True)
print(f"Build logs: {result.stdout[:500] or 'NONE'}")

# Try rebuilding with correct flags for newer llama-cpp-python
# Newer versions use GGML_HIPBLAS=ON
env = os.environ.copy()
env["CMAKE_ARGS"] = "-DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100 -DCMAKE_HIP_ARCHITECTURES=gfx1100"
env["FORCE_CMAKE"] = "1"

print("\\n=== Rebuilding with verbose output ===")
cmd = [
    "/opt/venv/bin/pip", "install", "--force-reinstall", "--no-cache-dir",
    "llama-cpp-python==0.3.34"
]

result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)

# Print output that mentions hip/rocm/gpu
for line in (result.stdout + result.stderr).split(chr(10)):
    low = line.lower()
    if any(kw in low for kw in ["hip", "rocm", "gpu", "blas", "error", "fail", "ggml_hip", "amd", "gfx"]):
        print(line[:300])

print(f"\\nReturn code: {result.returncode}")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(120)
while True:
    try:
        ws.settimeout(5)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
    except:
        break
ws.close()
print('\nDone')
