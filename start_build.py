"""
Start the HIP build in background via nohup.
"""
import requests, json, time, uuid, urllib3
from websocket import create_connection
urllib3.disable_warnings()

BASE = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
TOKEN = 'amd-oneclick'

r = requests.post(f'{BASE}/api/kernels', headers={'Authorization': f'token {TOKEN}'}, verify=False)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token={TOKEN}'
ws = create_connection(ws_url, timeout=30)
msg = json.loads(ws.recv())

code = """
import subprocess, os

LLAMA_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp'
BUILD_DIR = f'{LLAMA_DIR}/build_hip'

# Clean and reconfigure
subprocess.run(f'rm -rf {BUILD_DIR}', shell=True, capture_output=True, executable='/bin/bash')
os.makedirs(BUILD_DIR, exist_ok=True)

# Configure cmake
result = subprocess.run(
    f'cd {BUILD_DIR} && cmake .. '
    f'-DGGML_HIP=ON '
    f'-DAMDGPU_TARGETS=gfx1100 '
    f'-DCMAKE_BUILD_TYPE=Release '
    f'-DBUILD_SHARED_LIBS=ON '
    f'2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)
print(result.stdout[-1500:])

if 'Including HIP backend' not in result.stdout:
    print("FATAL: HIP backend not found!")
else:
    print("HIP_BACKEND: YES - Starting background build...")
    
    # Start build with nohup
    subprocess.run(
        f'cd {BUILD_DIR} && nohup cmake --build . --config Release -j$(nproc) > /tmp/build_hip.log 2>&1 &',
        shell=True, capture_output=True, text=True, timeout=10, executable='/bin/bash'
    )
    
    import time
    time.sleep(3)
    
    # Verify it started
    result = subprocess.run(
        'ps aux | grep "cmake --build" | grep -v grep',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    if result.stdout.strip():
        print(f"Build process running: {result.stdout[:200]}")
    else:
        print("WARNING: Build process may not have started")
    
    result = subprocess.run(
        'wc -l /tmp/build_hip.log 2>/dev/null || echo "0"',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print(f"Log lines so far: {result.stdout.strip()}")
    
    result = subprocess.run(
        'tail -3 /tmp/build_hip.log 2>/dev/null',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print(f"Last log lines: {result.stdout.strip()}")
    
    print("BUILD_STARTED: True")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Starting build...")
time.sleep(5)

output = ""
ws.settimeout(30)
while True:
    try:
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            output += msg['content']['text']
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
        if msg.get('msg_type') == 'status' and msg.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        if 'timed out' in str(e).lower():
            continue
        break

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\n=== Build started in background ===')
print('Wait 10-15 minutes, then run check_build.py')
