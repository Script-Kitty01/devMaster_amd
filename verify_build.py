"""Verify build results"""
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

B = '/tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip'

# Status
r = subprocess.run('cat /tmp/build_hip_status.txt', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== STATUS ===')
print(r.stdout)

# Check if build actually finished
r = subprocess.run('tail -5 /tmp/build_hip_full.log', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== LOG TAIL ===')
print(r.stdout)

# Check for errors in log
r = subprocess.run('grep -i "error" /tmp/build_hip_full.log | tail -10', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== ERRORS ===')
print(r.stdout)

# Check HIP linking
r = subprocess.run('grep -iE "hipblas|ggml.hip|hip library|hip::" /tmp/build_hip_full.log | tail -20', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== HIP LINK ===')
print(r.stdout)

# Check the actual .so files
r = subprocess.run('ls -la ' + B + '/bin/*.so*', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== .so FILES ===')
print(r.stdout)

# Check libggml.so for HIP symbols with nm
r = subprocess.run('nm -D ' + B + '/bin/libggml.so 2>/dev/null | grep -i hip | head -20', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== nm libggml.so HIP ===')
print(r.stdout if r.stdout else 'EMPTY')

# Check libllama.so for HIP symbols
r = subprocess.run('nm -D ' + B + '/bin/libllama.so 2>/dev/null | grep -i hip | head -20', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== nm libllama.so HIP ===')
print(r.stdout if r.stdout else 'EMPTY')

# Check for ggml_hip symbols
r = subprocess.run('nm -D ' + B + '/bin/libggml.so 2>/dev/null | grep -iE "ggml_hip|ggml_cuda|hip_malloc|hip_free" | head -20', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== nm libggml.so ggml_hip ===')
print(r.stdout if r.stdout else 'EMPTY')

# Check if ggml-hip was built as separate lib
r = subprocess.run('find ' + B + ' -name "*.so" -o -name "*.a" 2>/dev/null', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== ALL LIBS ===')
print(r.stdout)

# Check cmake cache
r = subprocess.run('grep -E "GGML_HIP|HIP_FOUND|AMDGPU" ' + B + '/CMakeCache.txt | head -10', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== CMAKE CACHE ===')
print(r.stdout)

# Check if ggml-hip backend is compiled into ggml
r = subprocess.run('strings ' + B + '/bin/libggml.so | grep -iE "hip|rocm|gfx1100" | head -20', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== strings libggml.so HIP ===')
print(r.stdout if r.stdout else 'EMPTY')

# Check libllama.so strings
r = subprocess.run('strings ' + B + '/bin/libllama.so | grep -iE "hip|rocm|gfx1100" | head -20', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== strings libllama.so HIP ===')
print(r.stdout if r.stdout else 'EMPTY')
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
print('\nDone')
