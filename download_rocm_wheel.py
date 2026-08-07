"""
Download pre-built ROCm wheel from GitHub releases.
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
ws = create_connection(ws_url, timeout=300)
msg = json.loads(ws.recv())

code = """
import subprocess, sys, os

# First, check what wheels are available on the ROCm index
print("=== Checking ROCm wheel index ===")
result = subprocess.run(
    [sys.executable, "-m", "pip", "index", "versions", "llama-cpp-python", "--index-url", "https://abetlen.github.io/llama-cpp-python/whl/rocm"],
    capture_output=True, text=True, timeout=30
)
print(result.stdout[:2000])
print(result.stderr[:1000] if result.stderr else "")

# Try to find the exact wheel URL
print("\\n=== Trying to find ROCm wheel URL ===")
# The ROCm wheels are at: https://github.com/abetlen/llama-cpp-python/releases
# Let's try to download directly
import urllib.request
import ssl

# Create unverified context for SSL issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Try multiple possible wheel URLs
wheel_urls = [
    "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.34/llama_cpp_python-0.3.34-cp312-cp312-manylinux_2_28_x86_64.whl",
    "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.33/llama_cpp_python-0.3.33-cp312-cp312-manylinux_2_28_x86_64.whl",
]

for url in wheel_urls:
    print(f"\\nTrying: {url}")
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        print(f"  Status: {resp.status}")
        if resp.status == 200:
            # Download the wheel
            wheel_data = resp.read()
            wheel_name = url.split("/")[-1]
            wheel_path = f"/tmp/{wheel_name}"
            with open(wheel_path, "wb") as f:
                f.write(wheel_data)
            print(f"  Downloaded: {wheel_path} ({len(wheel_data)} bytes)")
            
            # Install it
            print(f"  Installing...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", wheel_path, "--force-reinstall", "--no-deps"],
                capture_output=True, text=True, timeout=60
            )
            print(result.stdout[-1000:])
            if result.returncode == 0:
                print("  INSTALL SUCCESS!")
                break
    except Exception as e:
        print(f"  Failed: {e}")

# Check for HIPBLAS
print("\\n=== Checking for HIPBLAS ===")
result = subprocess.run(["find", "/opt/venv", "-name", "*hipblas*"], capture_output=True, text=True)
has = bool(result.stdout.strip())
print(f"HIPBLAS: {'*** FOUND! ***' if has else 'NOT FOUND'}")
if has:
    print(result.stdout)

# Also try pip install with --index-url directly
if not has:
    print("\\n=== Trying pip install with ROCm index URL ===")
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y"], capture_output=True)
    result = subprocess.run([
        sys.executable, "-m", "pip", "install", "llama-cpp-python",
        "--index-url", "https://abetlen.github.io/llama-cpp-python/whl/rocm",
        "--no-cache-dir"
    ], capture_output=True, text=True, timeout=120)
    print(result.stdout[-2000:])
    print(result.stderr[-1000:] if result.stderr else "")
    
    result = subprocess.run(["find", "/opt/venv", "-name", "*hipblas*"], capture_output=True, text=True)
    has = bool(result.stdout.strip())
    print(f"HIPBLAS: {'*** FOUND! ***' if has else 'NOT FOUND'}")

# Final check
print("\\n=== Final lib check ===")
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

print("Running...")
time.sleep(5)
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
print('\n\n=== DONE ===')
