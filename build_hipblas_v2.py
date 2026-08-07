"""
Build llama-cpp-python with HIPBLAS on the remote instance.
Fixed websocket message parsing.
"""
import requests, json, time, uuid, urllib3
from websocket import create_connection
urllib3.disable_warnings()

BASE = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
TOKEN = 'amd-oneclick'

def exec_remote(code, timeout=600):
    """Execute code on remote Jupyter kernel and return output."""
    r = requests.post(f'{BASE}/api/kernels', headers={'Authorization': f'token {TOKEN}'}, verify=False)
    kid = r.json()['id']
    
    ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token={TOKEN}'
    ws = create_connection(ws_url, timeout=timeout)
    msg = json.loads(ws.recv())  # initial connection msg
    
    ws.send(json.dumps({
        'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
        'parent_header': {},
        'metadata': {},
        'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
        'channel': 'shell'
    }))
    
    output = []
    start = time.time()
    while time.time() - start < timeout:
        try:
            ws.settimeout(5)
            msg = json.loads(ws.recv())
            if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
                output.append(msg['content']['text'])
            elif msg.get('msg_type') == 'error':
                output.append(f"ERROR: {msg.get('content', {}).get('ename', '')}: {msg.get('content', {}).get('evalue', '')}")
                break
            elif msg.get('msg_type') == 'status' and msg.get('content', {}).get('execution_state') == 'idle':
                # Check parent msg_id matches
                break
        except Exception as e:
            err_str = str(e)
            if 'timed out' in err_str.lower():
                continue
            break
    
    ws.close()
    requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
    return ''.join(output)

# Step 1: Check current state
print("=== Step 1: Checking current state ===")
out = exec_remote("""
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
""", timeout=30)
print(out)

# Step 2: Uninstall
print("\n=== Step 2: Uninstalling ===")
out = exec_remote("""
import subprocess, sys
result = subprocess.run([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y"], capture_output=True, text=True)
print(result.stdout)
print("RC:", result.returncode)
""", timeout=30)
print(out)

# Step 3: Build with HIPBLAS
print("\n=== Step 3: Building with HIPBLAS (5-10 min) ===")
out = exec_remote("""
import subprocess, sys, os

env = os.environ.copy()
env['CMAKE_ARGS'] = '-DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100'
env['FORCE_CMAKE'] = '1'

cmd = [sys.executable, "-m", "pip", "install", "llama-cpp-python", "--no-binary", ":all:", "--no-cache-dir"]
print("Running:", " ".join(cmd))
print("CMAKE_ARGS:", env['CMAKE_ARGS'])

result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)

stdout = result.stdout
if len(stdout) > 4000:
    print(stdout[:1000])
    print("... [middle omitted] ...")
    print(stdout[-3000:])
else:
    print(stdout)

if result.stderr:
    stderr = result.stderr
    print("\\nSTDERR (last 2000):")
    print(stderr[-2000:] if len(stderr) > 2000 else stderr)

print("\\nRC:", result.returncode)
""", timeout=600)
print(out)

# Step 4: Verify HIPBLAS
print("\n=== Step 4: Verifying HIPBLAS ===")
out = exec_remote("""
import subprocess

result = subprocess.run(["find", "/opt/venv", "-name", "libggml*"], capture_output=True, text=True)
print("All ggml libs:")
for line in sorted(result.stdout.strip().split(chr(10))):
    if line:
        print(f"  {line}")

result = subprocess.run(["find", "/opt/venv", "-name", "*hipblas*"], capture_output=True, text=True)
has_hipblas = bool(result.stdout.strip())
print(f"\\nHIPBLAS libs: {'FOUND!' if has_hipblas else 'NOT FOUND - BUILD FAILED'}")
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
""", timeout=30)
print(out)

print("\n=== DONE ===")
