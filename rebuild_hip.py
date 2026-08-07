"""Clean rebuild with GGML_HIP=ON, proper logging, verify HIP symbols"""
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

# Kill all old cmake builds
subprocess.run('pkill -9 -f "cmake --build" 2>/dev/null; sleep 1; echo "killed"', shell=True, capture_output=True, text=True, executable='/bin/bash')

# Clean build dir
subprocess.run(f'rm -rf {BUILD_DIR}', shell=True, capture_output=True, text=True, executable='/bin/bash')
os.makedirs(BUILD_DIR, exist_ok=True)

# Check what's in the current libllama.so (from build_hip)
r = subprocess.run(f'nm -D {BUILD_DIR}/bin/libggml.so 2>/dev/null | grep -i "ggml_backend_hip\\|ggml_backend_cpu" | head -10', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"Old libggml backends: {r.stdout.strip()[:500]}")

# Configure with verbose output
print("\\n=== Configuring cmake ===")
result = subprocess.run(
    f'cd {BUILD_DIR} && cmake .. '
    f'-DGGML_HIP=ON '
    f'-DAMDGPU_TARGETS=gfx1100 '
    f'-DCMAKE_BUILD_TYPE=Release '
    f'-DBUILD_SHARED_LIBS=ON '
    f'2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)

# Show key lines
for line in result.stdout.split('\\n'):
    if any(k in line for k in ['HIP', 'hip', 'GPU', 'backend', 'ggml', 'BLAS', 'Error', 'error', 'Found']):
        print(f"  {line}")

if 'Including HIP backend' in result.stdout:
    print("\\nHIP_BACKEND_CONFIGURED: YES")
else:
    print("\\nHIP_BACKEND_CONFIGURED: NO - ABORTING")
    raise SystemExit(1)

# Check what targets will be built
r = subprocess.run(f'cd {BUILD_DIR} && cmake --build . --target help 2>&1 | grep -i "ggml\\|llama" | head -20', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\nTargets:\\n{r.stdout.strip()[:500]}")

# Build just ggml first to verify HIP
print("\\n=== Building ggml (HIP) ===")
result = subprocess.run(
    f'cd {BUILD_DIR} && cmake --build . --config Release --target ggml -j$(nproc) 2>&1 | tail -30',
    shell=True, capture_output=True, text=True, timeout=600, executable='/bin/bash'
)
print(result.stdout[-2000:])

# Check if ggml HIP was built
r = subprocess.run(f'find {BUILD_DIR} -name "*.o" | xargs -I{{}} basename {{}} | grep -i hip | head -10', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\nHIP .o files: {r.stdout.strip() or 'NONE'}")

r = subprocess.run(f'find {BUILD_DIR} -name "*.o" | wc -l', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"Total .o files: {r.stdout.strip()}")

# Check for ggml-hip .o files specifically
r = subprocess.run(f'find {BUILD_DIR} -path "*/ggml-hip/*" -name "*.o" | head -10', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"ggml-hip .o files: {r.stdout.strip() or 'NONE'}")

# Check if libggml.so was built
r = subprocess.run(f'ls -la {BUILD_DIR}/bin/libggml.so 2>/dev/null || echo "NOT FOUND"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"\\nlibggml.so: {r.stdout.strip()}")

# Check HIP symbols
r = subprocess.run(f'nm -D {BUILD_DIR}/bin/libggml.so 2>/dev/null | grep -i hip | head -10', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"HIP symbols in libggml.so: {r.stdout.strip() or 'NONE'}")

r = subprocess.run(f'nm -D {BUILD_DIR}/bin/libggml.so 2>/dev/null | grep "ggml_backend" | head -10', shell=True, capture_output=True, text=True, executable='/bin/bash')
print(f"Backend symbols: {r.stdout.strip()[:500]}")

print("\\n=== DONE ===")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Rebuilding with HIP...")
time.sleep(5)

output = ""
while True:
    try:
        ws.settimeout(5)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            output += msg['content']['text']
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
        if msg.get('msg_type') == 'status' and msg.get('content', {}).get('execution_state') == 'idle':
            break
    except:
        if 'HIP_BACKEND' in output or 'DONE' in output:
            break
        continue

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\n=== Complete ===')
