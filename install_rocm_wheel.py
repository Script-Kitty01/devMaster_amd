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

# First, check what wheels are available
print("=== Checking available ROCm wheels ===")
result = subprocess.run([
    "/opt/venv/bin/pip", "index", "versions", "llama-cpp-python"
], capture_output=True, text=True, timeout=30)
print(result.stdout[:500])
print(result.stderr[:500])

# Try installing with ROCm extra
print("\\n=== Trying pip install with ROCm extra index ===")
env = os.environ.copy()
cmd = [
    "/opt/venv/bin/pip", "install", "--force-reinstall", "--no-cache-dir",
    "llama-cpp-python",
    "--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/rocm"
]
result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)
print(result.stdout[-500:])
print(result.stderr[-500:])
print(f"Return code: {result.returncode}")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(60)
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
