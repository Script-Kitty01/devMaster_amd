"""Launch HIP build - write script with echo, launch with nohup"""
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

code = "import subprocess, os\\n\\nLLAMA_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp'\\nBUILD_DIR = LLAMA_DIR + '/build_hip'\\n\\n# Clean\\nsubprocess.run('rm -rf ' + BUILD_DIR, shell=True, capture_output=True, text=True, executable='/bin/bash')\\nos.makedirs(BUILD_DIR, exist_ok=True)\\n\\n# Configure\\nresult = subprocess.run('cd ' + BUILD_DIR + ' && cmake .. -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100 -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON 2>&1', shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash')\\n\\nif 'Including HIP backend' not in result.stdout:\\n    print('FATAL: HIP backend not configured!')\\n    print(result.stdout[-1000:])\\nelse:\\n    print('HIP_CONFIGURED: YES')\\n    \\n    # Write build script using echo\\n    cmds = [\\n        'echo \\\"#!/bin/bash\\\" > /tmp/build_hip.sh',\\n        'echo \\\"cd ' + BUILD_DIR + '\\\" >> /tmp/build_hip.sh',\\n        'echo \\\"echo Build started at \\\\\\\\$(date) >> /tmp/build_hip_status.txt\\\" >> /tmp/build_hip.sh',\\n        'echo \\\"cmake --build . --config Release -j\\\\\\\\$(nproc) >> /tmp/build_hip_full.log 2>&1\\\" >> /tmp/build_hip.sh',\\n        'echo \\\"echo Build exit code: \\\\\\\\$? >> /tmp/build_hip_status.txt\\\" >> /tmp/build_hip.sh',\\n        'echo \\\"echo Build finished at \\\\\\\\$(date) >> /tmp/build_hip_status.txt\\\" >> /tmp/build_hip.sh',\\n        'chmod +x /tmp/build_hip.sh',\\n    ]\\n    for cmd in cmds:\\n        subprocess.run(cmd, shell=True, executable='/bin/bash', capture_output=True, timeout=5)\\n    \\n    # Show the script\\n    r = subprocess.run('cat /tmp/build_hip.sh', shell=True, capture_output=True, text=True, executable='/bin/bash')\\n    print('Build script:')\\n    print(r.stdout)\\n    \\n    # Launch with nohup\\n    subprocess.run('nohup /tmp/build_hip.sh > /dev/null 2>&1 &', shell=True, executable='/bin/bash', capture_output=True, timeout=5)\\n    \\n    import time\\n    time.sleep(3)\\n    \\n    # Verify\\n    r = subprocess.run('pgrep -fc \\\"cmake --build\\\" || echo \\\"0\\\"', shell=True, capture_output=True, text=True, executable='/bin/bash')\\n    print('Build processes: ' + r.stdout.strip())\\n    \\n    r = subprocess.run('cat /tmp/build_hip_status.txt 2>/dev/null || echo \\\"No status yet\\\"', shell=True, capture_output=True, text=True, executable='/bin/bash')\\n    print('Status: ' + r.stdout.strip())\\n    \\n    print('BUILD_LAUNCHED: True')"

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
