"""
Build llama-cpp-python with HIPBLAS on the remote instance.
Uses the Jupyter kernel API to execute commands on the remote AMD GPU instance.
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
    msg = json.loads(ws.recv())
    
    msg_id = str(uuid.uuid4())
    execute_msg = {
        'header': {
            'msg_id': msg_id,
            'username': 'user',
            'session': str(uuid.uuid4()),
            'msg_type': 'execute_request',
            'version': '5.2'
        },
        'parent_header': {},
        'metadata': {},
        'content': {
            'code': code,
            'silent': False,
            'store_history': False,
            'user_expressions': {},
            'allow_stdin': False,
            'stop_on_error': False
        },
        'channel': 'shell'
    }
    ws.send(json.dumps(execute_msg))
    
    output = []
    start = time.time()
    while time.time() - start < timeout:
        try:
            ws.settimeout(10)
            msg = json.loads(ws.recv())
            msg_type = msg.get('msg_type') or msg.get('header', {}).get('msg_type', '')
            
            if msg_type == 'stream':
                output.append(msg.get('content', {}).get('text', ''))
            elif msg_type == 'execute_result':
                output.append(msg.get('content', {}).get('data', {}).get('text/plain', ''))
            elif msg_type == 'error':
                output.append(f"ERROR: {msg.get('content', {}).get('ename', '')}: {msg.get('content', {}).get('evalue', '')}")
                break
            elif msg_type == 'status' and msg.get('content', {}).get('execution_state') == 'idle':
                break
        except Exception as e:
            if 'timed out' in str(e).lower():
                continue
            break
    
    ws.close()
    # Delete kernel
    requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
    return '\n'.join(output)

# Step 1: Check current state
print("=== Step 1: Checking current state ===")
out = exec_remote("""
import subprocess, os

# Check ROCm
print("ROCm version:")
result = subprocess.run(["cat", "/opt/rocm/.info/version"], capture_output=True, text=True)
print(result.stdout.strip())

# Check hipcc
print("\\nhipcc:")
result = subprocess.run(["which", "hipcc"], capture_output=True, text=True)
print(result.stdout.strip())

# Check cmake
print("\\ncmake:")
result = subprocess.run(["cmake", "--version"], capture_output=True, text=True)
print(result.stdout.strip().split('\\n')[0])

# Check GPU
print("\\nGPU:")
result = subprocess.run(["rocm-smi", "--showproductname"], capture_output=True, text=True)
print(result.stdout[:500])

# Check current llama-cpp-python
result = subprocess.run(["pip", "show", "llama-cpp-python"], capture_output=True, text=True)
print("\\nllama-cpp-python:", result.stdout[:500] if result.stdout else "NOT INSTALLED")
""", timeout=30)
print(out)

# Step 2: Uninstall current llama-cpp-python
print("\n=== Step 2: Uninstalling current llama-cpp-python ===")
out = exec_remote("""
import subprocess, sys
result = subprocess.run([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y"], capture_output=True, text=True)
print(result.stdout)
print(result.stderr[:500] if result.stderr else "")
print("RC:", result.returncode)
""", timeout=30)
print(out)

# Step 3: Build from source with HIPBLAS
print("\n=== Step 3: Building llama-cpp-python with HIPBLAS (this may take 5-10 min) ===")
out = exec_remote("""
import subprocess, sys, os

# Set environment for HIPBLAS build
env = os.environ.copy()
env['CMAKE_ARGS'] = '-DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100'
env['FORCE_CMAKE'] = '1'

# Install with no binary, force source build
cmd = [sys.executable, "-m", "pip", "install", "llama-cpp-python", "--no-binary", ":all:", "--no-cache-dir"]
print("Running:", " ".join(cmd))
print("CMAKE_ARGS:", env['CMAKE_ARGS'])
print()

result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)

# Print last 3000 chars of stdout
stdout = result.stdout
if len(stdout) > 3000:
    print("... (first 1000 chars) ...")
    print(stdout[:1000])
    print("... (last 2000 chars) ...")
    print(stdout[-2000:])
else:
    print(stdout)

if result.stderr:
    stderr = result.stderr
    if len(stderr) > 2000:
        print("\\nSTDERR (last 2000):")
        print(stderr[-2000:])
    else:
        print("\\nSTDERR:", stderr)

print("\\nRC:", result.returncode)
""", timeout=600)
print(out)

# Step 4: Check if HIPBLAS libs now exist
print("\n=== Step 4: Checking for HIPBLAS libs ===")
out = exec_remote("""
import subprocess

# Find all ggml libs
result = subprocess.run(["find", "/opt/venv", "-name", "libggml*"], capture_output=True, text=True)
print("All ggml libs:")
for line in sorted(result.stdout.strip().split(chr(10))):
    if line:
        print(f"  {line}")

# Check for hipblas specifically
result = subprocess.run(["find", "/opt/venv", "-name", "*hipblas*"], capture_output=True, text=True)
print(f"\\nHIPBLAS libs: {result.stdout if result.stdout.strip() else 'NONE FOUND - BUILD FAILED'}")

# Check libllama links
result = subprocess.run(["find", "/opt/venv", "-name", "libllama*"], capture_output=True, text=True)
print(f"\\nlibllama: {result.stdout[:500] if result.stdout.strip() else 'NONE'}")

# Try ldd on libllama
for lib in result.stdout.strip().split(chr(10)):
    if lib and 'libllama.so' in lib:
        r = subprocess.run(["ldd", lib], capture_output=True, text=True)
        print(f"\\nldd {lib}:")
        for line in r.stdout.strip().split(chr(10)):
            if 'hip' in line.lower() or 'rocm' in line.lower() or 'ggml' in line.lower():
                print(f"  {line}")
""", timeout=30)
print(out)
