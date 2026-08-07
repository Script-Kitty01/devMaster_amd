"""Launch HIP build via 'at' command - completely independent of kernel"""
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
    
    # Write build script using echo commands
    subprocess.run('echo "#!/bin/bash" > /tmp/build_hip.sh', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
    subprocess.run(f'echo "cd {BUILD_DIR}" >> /tmp/build_hip.sh', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
    subprocess.run('echo \'echo "Build started at $(date)" >> /tmp/build_hip_status.txt\' >> /tmp/build_hip.sh', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
    subprocess.run('echo "cmake --build . --config Release -j\\\\$(nproc) >> /tmp/build_hip_full.log 2>&1" >> /tmp/build_hip.sh', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
    subprocess.run('echo \'echo "Build exit code: $?" >> /tmp/build_hip_status.txt\' >> /tmp/build_hip.sh', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
    subprocess.run('echo \'echo "Build finished at $(date)" >> /tmp/build_hip_status.txt\' >> /tmp/build_hip.sh', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
    subprocess.run('chmod +x /tmp/build_hip.sh', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
    
    # Try 'at' first, fall back to nohup
    r = subprocess.run('which at 2>/dev/null', shell=True, capture_output=True, text=True, executable='/bin/bash')
    if r.stdout.strip():
        # Use 'at' to schedule immediately
        result = subprocess.run('echo "/tmp/build_hip.sh" | at now 2>&1', shell=True, capture_output=True, text=True, executable='/bin/bash')
        print(f"at result: {result.stdout.strip()}")
        print("BUILD_SCHEDULED_VIA_AT: True")
    else:
        # Fallback: use nohup + disown
        subprocess.run('nohup /tmp/build_hip.sh > /dev/null 2>&1 & disown', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
        print("BUILD_SCHEDULED_VIA_NOHUP: True")
    
    import time
    time.sleep(3)
    
    # Verify
    r = subprocess.run('cat /tmp/build_hip_status.txt 2>/dev/null || echo "No status yet"', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print(f"Status: {r.stdout.strip()}")
    
    r = subprocess.run('pgrep -fc "cmake --build" || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print(f"Build processes: {r.stdout.strip()}")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(10)
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
print('\nDone - build launched independently')
