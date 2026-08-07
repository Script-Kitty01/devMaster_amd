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

# Clone llama-cpp-python and build from source
os.chdir("/tmp")

# Remove if exists
subprocess.run(["rm", "-rf", "/tmp/llama-cpp-python"], capture_output=True)

print("Cloning llama-cpp-python...")
result = subprocess.run(
    ["git", "clone", "--depth", "1", "--branch", "v0.3.34", "https://github.com/abetlen/llama-cpp-python.git"],
    capture_output=True, text=True, timeout=60
)
print(f"Clone: {result.returncode}")

os.chdir("/tmp/llama-cpp-python")

# Set env for HIPBLAS build
env = os.environ.copy()
env["CMAKE_ARGS"] = "-DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100"
env["FORCE_CMAKE"] = "1"
env["GGML_HIPBLAS"] = "1"

print("Building with HIPBLAS...")
result = subprocess.run(
    ["/opt/venv/bin/pip", "install", "-e", "."],
    capture_output=True, text=True, env=env, timeout=600
)

# Print relevant lines
for line in (result.stdout + result.stderr).split(chr(10)):
    low = line.lower()
    if any(kw in low for kw in ["hip", "rocm", "gpu", "blas", "error", "fail", "ggml_hip", "amd", "gfx", "building", "cmake", "success", "found"]):
        print(line[:300])

print(f"\\nReturn code: {result.returncode}")

# Check libs
result = subprocess.run(["find", "/opt/venv", "-name", "libggml*"], capture_output=True, text=True)
print("\\nAll ggml libs:")
for line in sorted(result.stdout.strip().split(chr(10))):
    print(f"  {line}")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(300)
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
