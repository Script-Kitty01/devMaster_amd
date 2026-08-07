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
import subprocess, os, sys

print("=== Rebuilding llama-cpp-python with HIPBLAS ===")

# Set env vars for build
env = os.environ.copy()
env["CMAKE_ARGS"] = "-DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100"
env["FORCE_CMAKE"] = "1"

print(f"CMAKE_ARGS={env['CMAKE_ARGS']}")

# Rebuild
cmd = [
    "/opt/venv/bin/pip", "install", "--force-reinstall", "--no-cache-dir",
    "--verbose", "llama-cpp-python"
]

print("Running pip install...")
result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)

# Print last 200 lines
lines = result.stdout.split(chr(10)) + result.stderr.split(chr(10))
print("\\n".join(lines[-100:]))

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
