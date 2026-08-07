"""Launch HIP build in detached screen session - survives kernel death"""
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

# Simple code - no complex escaping needed
code = """
import subprocess, os

LLAMA_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp'
BUILD_DIR = LLAMA_DIR + '/build_hip'

# Clean
subprocess.run('rm -rf ' + BUILD_DIR, shell=True, capture_output=True, text=True, executable='/bin/bash')
os.makedirs(BUILD_DIR, exist_ok=True)

# Configure
result = subprocess.run(
    'cd ' + BUILD_DIR + ' && cmake .. -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100 -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON 2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)

if 'Including HIP backend' not in result.stdout:
    print('FATAL: HIP backend not configured!')
    print(result.stdout[-1000:])
else:
    print('HIP_CONFIGURED: YES')
    
    # Check if screen is available
    r = subprocess.run('which screen 2>/dev/null || echo NOT_FOUND', shell=True, capture_output=True, text=True, executable='/bin/bash')
    has_screen = 'NOT_FOUND' not in r.stdout
    
    if has_screen:
        # Use screen for full detachment
        cmd = 'screen -dmS hipbuild bash -c "cd ' + BUILD_DIR + ' && cmake --build . --config Release -j$(nproc) > /tmp/build_hip_full.log 2>&1; echo BUILD_EXIT_CODE=\\$? >> /tmp/build_hip_status.txt; date >> /tmp/build_hip_status.txt"'
        subprocess.run(cmd, shell=True, executable='/bin/bash', capture_output=True, timeout=10)
        print('BUILD_STARTED_IN_SCREEN: hipbuild')
    else:
        # Fallback: write script and use nohup
        script = '#!/bin/bash\\ncd ' + BUILD_DIR + '\\ncmake --build . --config Release -j$(nproc) > /tmp/build_hip_full.log 2>&1\\necho BUILD_EXIT_CODE=$? >> /tmp/build_hip_status.txt\\ndate >> /tmp/build_hip_status.txt\\n'
        with open('/tmp/build_hip.sh', 'w') as f:
            f.write(script)
        subprocess.run('chmod +x /tmp/build_hip.sh', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
        subprocess.run('nohup /tmp/build_hip.sh > /dev/null 2>&1 &', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
        print('BUILD_STARTED_VIA_NOHUP')
    
    import time
    time.sleep(3)
    
    # Verify
    r = subprocess.run('pgrep -fc "cmake --build" || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print('Build processes: ' + r.stdout.strip())
    
    r = subprocess.run('wc -c /tmp/build_hip_full.log 2>/dev/null || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print('Log size: ' + r.stdout.strip() + ' bytes')
    
    print('DONE')
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
print('\nDone')
