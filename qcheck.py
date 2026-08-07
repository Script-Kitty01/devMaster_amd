"""Quick check: build status, log tail, .so files"""
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

# 1. Check if build process is running
r = subprocess.run('pgrep -af "cmake" 2>/dev/null || echo "NONE"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"CMake processes: {r.stdout.strip()}")

# 2. Check build log
r = subprocess.run('tail -20 /tmp/build_hip.log 2>/dev/null || echo "No log"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\nBuild log tail:\\n{r.stdout.strip()}")

# 3. Check for .so files
r = subprocess.run('find /tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip -name "*.so" -type f 2>/dev/null | head -10', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\n.so files: {r.stdout.strip() or 'NONE'}")

# 4. Check log size
r = subprocess.run('wc -l /tmp/build_hip.log 2>/dev/null || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\nLog lines: {r.stdout.strip()}")

# 5. Check for errors
r = subprocess.run('grep -i "error:" /tmp/build_hip.log 2>/dev/null | head -5 || echo "No errors"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\nErrors: {r.stdout.strip() or 'None found'}")
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
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\nDone')
