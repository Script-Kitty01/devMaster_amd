"""Use base64 to avoid all escaping issues"""
import requests, json, time, uuid, urllib3, base64
from websocket import create_connection
urllib3.disable_warnings()

BASE = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
TOKEN = 'amd-oneclick'

# The build script (as a regular Python string)
build_script = """#!/bin/bash
set -e
cd /tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip
echo "Build started at $(date)" > /tmp/build_hip_status.txt
cmake --build . --config Release --target ggml llama -j$(nproc) >> /tmp/build_hip_full.log 2>&1
RC=$?
echo "Build exit code: $RC" >> /tmp/build_hip_status.txt
echo "Build finished at $(date)" >> /tmp/build_hip_status.txt
if [ $RC -eq 0 ]; then
    LLAMA_DIR=$(python3.12 -c "import llama_cpp; import os; print(os.path.dirname(llama_cpp.__file__))")
    LIB_DIR="$LLAMA_DIR/lib"
    mkdir -p "$LIB_DIR/backup"
    cp "$LIB_DIR"/*.so* "$LIB_DIR/backup/" 2>/dev/null || true
    cp -v /tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip/bin/*.so* "$LIB_DIR/" >> /tmp/build_hip_status.txt 2>&1
    strings "$LIB_DIR/libllama.so" | grep -i hipblas >> /tmp/build_hip_status.txt 2>&1
    echo "COPY_DONE" >> /tmp/build_hip_status.txt
fi
"""

b64_script = base64.b64encode(build_script.encode()).decode()

r = requests.post(f'{BASE}/api/kernels', headers={'Authorization': f'token {TOKEN}'}, verify=False)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token={TOKEN}'
ws = create_connection(ws_url)
msg = json.loads(ws.recv())

code = f"""import subprocess, os, base64

LLAMA_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp'
BUILD_DIR = LLAMA_DIR + '/build_hip'

# Clean
subprocess.run('rm -rf ' + BUILD_DIR, shell=True, capture_output=True, text=True, executable='/bin/bash')
os.makedirs(BUILD_DIR, exist_ok=True)

# Configure
result = subprocess.run(
    'cd ' + BUILD_DIR + ' && cmake .. -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100 -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=OFF 2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)

if 'Including HIP backend' not in result.stdout:
    print('FATAL: HIP not configured')
    print(result.stdout[-500:])
else:
    print('HIP_CONFIGURED: YES')
    
    # Decode and write build script
    script = base64.b64decode('{b64_script}').decode()
    with open('/tmp/build_hip_final.sh', 'w') as f:
        f.write(script)
    subprocess.run('chmod +x /tmp/build_hip_final.sh', shell=True, executable='/bin/bash', capture_output=True, timeout=5)
    
    # Show script
    r = subprocess.run('head -5 /tmp/build_hip_final.sh', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print('Script start:')
    print(r.stdout)
    
    # Launch with setsid
    subprocess.Popen(
        ['/tmp/build_hip_final.sh'],
        start_new_session=True,
        close_fds=True
    )
    
    import time
    time.sleep(3)
    
    r = subprocess.run('pgrep -f build_hip_final || echo "NOT_RUNNING"', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print('Script PID: ' + r.stdout.strip())
    
    r = subprocess.run('cat /tmp/build_hip_status.txt 2>/dev/null || echo "No status"', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print('Status: ' + r.stdout.strip())
    
    print('LAUNCHED: True')
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
