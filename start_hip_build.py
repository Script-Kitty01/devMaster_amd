"""Start HIP build in background via nohup, return immediately"""
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

LLAMA_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp'
BUILD_DIR = f'{LLAMA_DIR}/build_hip'

# Kill old builds
subprocess.run('pkill -9 -f "cmake --build" 2>/dev/null; sleep 1', shell=True, capture_output=True, text=True, executable='/bin/bash')

# Clean
subprocess.run(f'rm -rf {BUILD_DIR}', shell=True, capture_output=True, text=True, executable='/bin/bash')
os.makedirs(BUILD_DIR, exist_ok=True)

# Configure
result = subprocess.run(
    f'cd {BUILD_DIR} && cmake .. '
    f'-DGGML_HIP=ON '
    f'-DAMDGPU_TARGETS=gfx1100 '
    f'-DCMAKE_BUILD_TYPE=Release '
    f'-DBUILD_SHARED_LIBS=ON '
    f'2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)

if 'Including HIP backend' not in result.stdout:
    print("FATAL: HIP backend not configured!")
    print(result.stdout[-1000:])
else:
    print("HIP_CONFIGURED: YES")
    
    # Start build in background with full log
    cmd = f'cd {BUILD_DIR} && cmake --build . --config Release -j$(nproc) > /tmp/build_hip_full.log 2>&1'
    subprocess.Popen(cmd, shell=True, executable='/bin/bash', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    import time
    time.sleep(3)
    
    # Verify running
    r = subprocess.run('pgrep -fc "cmake --build"', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print(f"Build processes: {r.stdout.strip()}")
    
    r = subprocess.run('wc -c /tmp/build_hip_full.log 2>/dev/null || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print(f"Log size: {r.stdout.strip()} bytes")
    
    print("BUILD_STARTED: True")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(8)
while True:
    try:
        ws.settimeout(3)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
    except:
        break

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\nDone - build started in background')
