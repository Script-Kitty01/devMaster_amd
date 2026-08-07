"""
Build llama-cpp-python with HIPBLAS on remote - v3 with correct websocket parsing.
"""
import requests, json, time, uuid, urllib3
from websocket import create_connection
urllib3.disable_warnings()

BASE = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
TOKEN = 'amd-oneclick'

# Step 1: Check current state
print("=== Step 1: Check ===")
r = requests.post(f'{BASE}/api/kernels', headers={'Authorization': f'token {TOKEN}'}, verify=False)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token={TOKEN}'
ws = create_connection(ws_url, timeout=120)
msg = json.loads(ws.recv())

code = """
import subprocess, os

print("ROCm version:")
result = subprocess.run(["cat", "/opt/rocm/.info/version"], capture_output=True, text=True)
print(result.stdout.strip())

print("\\nhipcc:")
result = subprocess.run(["which", "hipcc"], capture_output=True, text=True)
print(result.stdout.strip())

print("\\ncmake:")
result = subprocess.run(["cmake", "--version"], capture_output=True, text=True)
print(result.stdout.strip().split('\\n')[0])

print("\\nGPU:")
result = subprocess.run(["rocm-smi", "--showproductname"], capture_output=True, text=True)
print(result.stdout[:500])

print("\\nllama-cpp-python:")
result = subprocess.run(["pip", "show", "llama-cpp-python"], capture_output=True, text=True)
print(result.stdout[:500] if result.stdout else "NOT INSTALLED")

print("\\nExisting ggml libs:")
result = subprocess.run(["find", "/opt/venv", "-name", "libggml*"], capture_output=True, text=True)
for line in sorted(result.stdout.strip().split(chr(10))):
    if line:
        print(f"  {line}")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(3)
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

# Step 2: Uninstall + Build + Verify in ONE long-running command
print("\n\n=== Step 2: Uninstall + Build with HIPBLAS + Verify ===")
print("(This will take 5-10 minutes for the build...)")

r = requests.post(f'{BASE}/api/kernels', headers={'Authorization': f'token {TOKEN}'}, verify=False)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token={TOKEN}'
ws = create_connection(ws_url, timeout=900)
msg = json.loads(ws.recv())

code = """
import subprocess, sys, os

# Uninstall
print("Uninstalling llama-cpp-python...")
result = subprocess.run([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y"], capture_output=True, text=True)
print(result.stdout.strip())
print("Uninstall RC:", result.returncode)

# Build with HIPBLAS
print("\\nBuilding llama-cpp-python with HIPBLAS...")
env = os.environ.copy()
env['CMAKE_ARGS'] = '-DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100'
env['FORCE_CMAKE'] = '1'

cmd = [sys.executable, "-m", "pip", "install", "llama-cpp-python", "--no-binary", ":all:", "--no-cache-dir"]
print("CMD:", " ".join(cmd))
print("CMAKE_ARGS:", env['CMAKE_ARGS'])
print()

result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)

stdout = result.stdout
if len(stdout) > 5000:
    print(stdout[:1500])
    print("\\n... [middle omitted] ...\\n")
    print(stdout[-3500:])
else:
    print(stdout)

if result.stderr:
    stderr = result.stderr
    print("\\nSTDERR (last 3000):")
    print(stderr[-3000:] if len(stderr) > 3000 else stderr)

print("\\nBuild RC:", result.returncode)

# Verify
print("\\n=== VERIFICATION ===")
result = subprocess.run(["find", "/opt/venv", "-name", "libggml*"], capture_output=True, text=True)
print("All ggml libs:")
for line in sorted(result.stdout.strip().split(chr(10))):
    if line:
        print(f"  {line}")

result = subprocess.run(["find", "/opt/venv", "-name", "*hipblas*"], capture_output=True, text=True)
has_hipblas = bool(result.stdout.strip())
print(f"\\nHIPBLAS libs: {'*** FOUND! ***' if has_hipblas else '*** NOT FOUND - BUILD FAILED ***'}")
if has_hipblas:
    print(result.stdout)

# Check libllama links
result = subprocess.run(["find", "/opt/venv", "-name", "libllama.so"], capture_output=True, text=True)
for lib in result.stdout.strip().split(chr(10)):
    if lib:
        r = subprocess.run(["ldd", lib], capture_output=True, text=True)
        print(f"\\nldd {lib}:")
        for line in r.stdout.strip().split(chr(10)):
            if 'hip' in line.lower() or 'rocm' in line.lower() or 'ggml' in line.lower():
                print(f"  {line}")

print("\\n=== DONE ===")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

# Wait for build - long timeout
print("Waiting for build to complete...")
time.sleep(10)
while True:
    try:
        ws.settimeout(10)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
    except Exception as e:
        err = str(e)
        if 'timed out' in err.lower():
            continue
        break

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\n\n=== ALL DONE ===')
