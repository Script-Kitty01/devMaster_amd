"""
Build llama-cpp-python with HIPBLAS - v5: use scikit-build-core config-settings.
"""
import requests, json, time, uuid, urllib3
from websocket import create_connection
urllib3.disable_warnings()

BASE = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
TOKEN = 'amd-oneclick'

r = requests.post(f'{BASE}/api/kernels', headers={'Authorization': f'token {TOKEN}'}, verify=False)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token={TOKEN}'
ws = create_connection(ws_url, timeout=900)
msg = json.loads(ws.recv())

code = """
import subprocess, sys, os

# Uninstall
print("=== Uninstalling ===")
subprocess.run([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y"], capture_output=True)

# Try scikit-build-core config settings
print("\\n=== Building with scikit-build-core config-settings ===")
cmd = [
    sys.executable, "-m", "pip", "install", "llama-cpp-python",
    "--no-binary", ":all:", "--no-cache-dir",
    "--config-settings=cmake.define.GGML_HIPBLAS=ON",
    "--config-settings=cmake.define.AMDGPU_TARGETS=gfx1100",
    "-v"
]
print("CMD:", " ".join(cmd))

result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
stdout = result.stdout
# Look for HIPBLAS in the output
if 'HIPBLAS' in stdout or 'hipblas' in stdout.lower():
    for line in stdout.split(chr(10)):
        if 'hipblas' in line.lower() or 'HIPBLAS' in line:
            print(f"  >>> {line}")
else:
    print("(no HIPBLAS mention in build output)")

print("\\nLast 2000 chars of stdout:")
print(stdout[-2000:] if len(stdout) > 2000 else stdout)
print("\\nRC:", result.returncode)

# Check
print("\\n=== Checking for HIPBLAS ===")
result = subprocess.run(["find", "/opt/venv", "-name", "*hipblas*"], capture_output=True, text=True)
has = bool(result.stdout.strip())
print(f"HIPBLAS: {'*** FOUND! ***' if has else 'NOT FOUND'}")
if has:
    print(result.stdout)

# Check all ggml libs
result = subprocess.run(["find", "/opt/venv", "-name", "libggml*"], capture_output=True, text=True)
print("\\nAll ggml libs:")
for line in sorted(result.stdout.strip().split(chr(10))):
    if line:
        print(f"  {line}")

# If still no HIPBLAS, try the old setuptools approach
if not has:
    print("\\n=== Trying SETUPTOOLS approach ===")
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y"], capture_output=True)
    
    # Set env vars AND use --config-settings
    env = os.environ.copy()
    env['CMAKE_ARGS'] = '-DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100'
    env['FORCE_CMAKE'] = '1'
    env['LLAMA_HIPBLAS'] = 'ON'
    
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "llama-cpp-python", "--no-binary", ":all:", "--no-cache-dir", "-v"],
        capture_output=True, text=True, timeout=600, env=env
    )
    print("Last 2000 chars:")
    print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    print("RC:", result.returncode)
    
    result = subprocess.run(["find", "/opt/venv", "-name", "*hipblas*"], capture_output=True, text=True)
    has = bool(result.stdout.strip())
    print(f"HIPBLAS: {'*** FOUND! ***' if has else 'NOT FOUND'}")

# If STILL no HIPBLAS, try downloading tarball and building manually
if not has:
    print("\\n=== Trying manual build from tarball ===")
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y"], capture_output=True)
    
    # Download source tarball with curl (which handles SSL better)
    script = '''
cd /tmp
rm -rf llama-cpp-python-build
mkdir llama-cpp-python-build && cd llama-cpp-python-build
curl -skL -o source.tar.gz https://github.com/abetlen/llama-cpp-python/archive/refs/tags/v0.3.34.tar.gz
tar xzf source.tar.gz --strip-components=1
CMAKE_ARGS="-DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100" FORCE_CMAKE=1 /opt/venv/bin/pip install . --no-cache-dir -v 2>&1 | tail -40
'''
    result = subprocess.run(script, shell=True, capture_output=True, text=True, timeout=300, executable='/bin/bash')
    print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
    print("RC:", result.returncode)
    
    result = subprocess.run(["find", "/opt/venv", "-name", "*hipblas*"], capture_output=True, text=True)
    has = bool(result.stdout.strip())
    print(f"HIPBLAS: {'*** FOUND! ***' if has else 'NOT FOUND'}")

print("\\n=== DONE ===")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Waiting for build...")
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
        if 'timed out' in str(e).lower():
            continue
        break

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\n\n=== ALL DONE ===')
