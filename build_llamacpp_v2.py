"""
Build llama.cpp with HIPBLAS using Python urllib (bypasses curl SSL issues),
then set LLAMA_CPP_LIB to use the HIPBLAS-enabled lib.
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
import subprocess, sys, os, urllib.request, ssl, tarfile, io, shutil

# Step 1: Download llama.cpp using Python (bypasses curl SSL issues)
print("=== Step 1: Downloading llama.cpp via Python ===")
url = "https://github.com/ggerganov/llama.cpp/archive/refs/heads/master.tar.gz"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

print(f"Downloading from {url}...")
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    resp = urllib.request.urlopen(req, context=ctx, timeout=120)
    data = resp.read()
    print(f"Downloaded {len(data)} bytes")
    
    # Extract
    print("Extracting...")
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(path='/tmp/')
    
    # Find extracted dir
    for d in os.listdir('/tmp/'):
        if d.startswith('llama.cpp-'):
            src = f'/tmp/{d}'
            if os.path.exists('/tmp/llama.cpp'):
                shutil.rmtree('/tmp/llama.cpp')
            shutil.move(src, '/tmp/llama.cpp')
            print(f"Moved {src} -> /tmp/llama.cpp")
            break
    print("DOWNLOAD OK")
except Exception as e:
    print(f"DOWNLOAD FAILED: {e}")
    sys.exit(1)

# Step 2: Build llama.cpp with HIPBLAS
print("\\n=== Step 2: Building llama.cpp with HIPBLAS ===")
build_dir = '/tmp/llama.cpp/build'
os.makedirs(build_dir, exist_ok=True)

# Configure
print("Configuring cmake...")
result = subprocess.run(
    f'cd {build_dir} && cmake .. '
    '-DGGML_HIPBLAS=ON '
    '-DAMDGPU_TARGETS=gfx1100 '
    '-DCMAKE_BUILD_TYPE=Release '
    '2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)
print(result.stdout[-2000:])
if result.stderr:
    print("STDERR:", result.stderr[-1000:])
if result.returncode != 0:
    print(f"CMAKE CONFIGURE FAILED (rc={result.returncode})")
    sys.exit(1)

# Check if HIPBLAS was detected
if 'HIPBLAS' in result.stdout or 'hipblas' in result.stdout.lower():
    print("\\n*** HIPBLAS DETECTED in cmake output ***")
else:
    print("\\nWARNING: HIPBLAS not mentioned in cmake output")

# Build
print("\\nBuilding (this will take several minutes)...")
result = subprocess.run(
    f'cd {build_dir} && cmake --build . --config Release -j$(nproc) 2>&1 | tail -50',
    shell=True, capture_output=True, text=True, timeout=600, executable='/bin/bash'
)
print(result.stdout[-3000:])
print(f"Build RC: {result.returncode}")

# Step 3: Find built libs
print("\\n=== Step 3: Finding built libs ===")
result = subprocess.run(
    f'find {build_dir} -name "libllama.so" -o -name "libggml*.so" 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("Built libs:")
print(result.stdout)

# Check for HIPBLAS symbols
result = subprocess.run(
    f'find {build_dir} -name "libggml*.so" -exec sh -c "nm -D {{}} | grep -i hip | head -10" \\; 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
has_hip = bool(result.stdout.strip())
print(f"\\nHIP symbols in libs: {'*** FOUND ***' if has_hip else 'NOT FOUND'}")
if has_hip:
    print(result.stdout[:500])

# Step 4: Set up LLAMA_CPP_LIB
if has_hip:
    print("\\n=== Step 4: Setting LLAMA_CPP_LIB ===")
    lib_path = f'{build_dir}/bin/libllama.so'
    if not os.path.exists(lib_path):
        # Try src directory
        result = subprocess.run(f'find {build_dir} -name "libllama.so" -type f', shell=True, capture_output=True, text=True, executable='/bin/bash')
        lib_path = result.stdout.strip().split('\\n')[0] if result.stdout.strip() else ''
    
    if lib_path:
        print(f"Using lib: {lib_path}")
        
        # Test with LLAMA_CPP_LIB
        test_code = f'''
import os, sys
os.environ["LLAMA_CPP_LIB"] = "{lib_path}"
sys.path.insert(0, "/workspace/template-repos/template-1005/repo")
from llama_cpp import Llama

model_path = "/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
print(f"Model: {{model_path}}")
print(f"LLAMA_CPP_LIB: {{os.environ.get('LLAMA_CPP_LIB')}}")

try:
    llm = Llama(
        model_path=model_path,
        n_gpu_layers=-1,
        n_ctx=2048,
        n_batch=512,
        verbose=True
    )
    print("\\n*** GPU LOAD SUCCESS! ***")
    result = llm("Hello, what is 2+2?", max_tokens=50)
    print(f"Response: {{result['choices'][0]['text']}}")
except Exception as e:
    print(f"ERROR: {{e}}")
    import traceback
    traceback.print_exc()
'''
        result = subprocess.run(
            [sys.executable, '-c', test_code],
            capture_output=True, text=True, timeout=120
        )
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr[-1000:])
    else:
        print("Could not find libllama.so!")
else:
    print("\\nNo HIPBLAS libs built. Trying alternative...")

print("\\n=== DONE ===")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Building llama.cpp with HIPBLAS via Python download...")
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
