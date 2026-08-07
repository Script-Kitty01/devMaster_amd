"""
Download llama-cpp-python source from PyPI mirror, patch CMakeLists to force HIPBLAS, build.
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
import subprocess, sys, os, shutil, re

# Step 1: Download llama-cpp-python source from PyPI mirror
print("=== Step 1: Downloading llama-cpp-python source ===")
result = subprocess.run(
    '/opt/venv/bin/pip download --no-binary :all: --no-deps -d /tmp/llama_src llama-cpp-python '
    '-i https://pypi.tuna.tsinghua.edu.cn/simple 2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)
print(result.stdout.strip())
if result.returncode != 0:
    print("STDERR:", result.stderr[-500:])
    sys.exit(1)

# Find the downloaded tar.gz
result = subprocess.run(
    'ls /tmp/llama_src/llama_cpp_python-*.tar.gz 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
tarball = result.stdout.strip()
print(f"Tarball: {tarball}")

# Extract
result = subprocess.run(
    f'cd /tmp && rm -rf llama_cpp_python_src && mkdir llama_cpp_python_src && '
    f'cd llama_cpp_python_src && tar xzf {tarball} --strip-components=1 && ls',
    shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
)
print(result.stdout)

# Step 2: Find and patch the CMake configuration
print("\\n=== Step 2: Patching for HIPBLAS ===")
src_dir = '/tmp/llama_cpp_python_src'

# Look for where GGML_HIPBLAS is set
result = subprocess.run(
    f'grep -r "GGML_HIPBLAS" {src_dir} --include="*.py" --include="*.cmake" --include="CMakeLists.txt" 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("GGML_HIPBLAS references:")
print(result.stdout[:2000])

# Look for cmake args in Python files
result = subprocess.run(
    f'grep -r "cmake" {src_dir} --include="*.py" -l 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("\\nFiles with cmake references:")
print(result.stdout)

# Look at the main build Python file
for f in ['setup.py', 'pyproject.toml', 'CMakeLists.txt']:
    path = os.path.join(src_dir, f)
    if os.path.exists(path):
        print(f"\\n--- {f} exists ---")
        with open(path) as fh:
            content = fh.read()
            if 'GGML_HIPBLAS' in content or 'HIPBLAS' in content or 'hipblas' in content:
                print("Contains HIPBLAS references!")
            else:
                print("No HIPBLAS references found")
                # Show relevant sections
                if 'cmake' in content.lower():
                    for i, line in enumerate(content.split('\\n')):
                        if 'cmake' in line.lower():
                            print(f"  Line {i}: {line.strip()[:120]}")

# Step 3: Try building with CMAKE_ARGS exported AND using pip install from source
print("\\n=== Step 3: Building from source with CMAKE_ARGS ===")
result = subprocess.run(
    f'cd {src_dir} && '
    'export CMAKE_ARGS="-DGGML_HIPBLAS=ON -DAMDGPU_TARGETS=gfx1100" && '
    'export FORCE_CMAKE=1 && '
    'export GGML_HIPBLAS=1 && '
    '/opt/venv/bin/pip install . --no-cache-dir -v 2>&1 | tail -60',
    shell=True, capture_output=True, text=True, timeout=600, executable='/bin/bash'
)
print(result.stdout[-3000:])
print(f"RC: {result.returncode}")

# Step 4: Check for HIPBLAS
print("\\n=== Step 4: Checking for HIPBLAS ===")
result = subprocess.run(
    'find /opt/venv/lib/python3.12/site-packages/llama_cpp -name "*.so" -exec sh -c "strings {} | grep -i hipblas | head -5" \\; 2>/dev/null',
    shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
)
has_hip = bool(result.stdout.strip())
print(f"HIPBLAS strings in .so: {'*** FOUND ***' if has_hip else 'NOT FOUND'}")
if has_hip:
    print(result.stdout[:500])

# Also check ldd
result = subprocess.run(
    'ldd /opt/venv/lib/python3.12/site-packages/llama_cpp/lib/libllama.so 2>/dev/null | grep -iE "hip|rocm|amd"',
    shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
)
print(f"\\nHIP/ROCm links: {'FOUND' if result.stdout.strip() else 'NONE'}")

# Step 5: If still no HIPBLAS, try modifying the pyproject.toml directly
if not has_hip:
    print("\\n=== Step 5: Direct CMakeLists.txt patch ===")
    # Find the vendored llama.cpp CMakeLists.txt
    result = subprocess.run(
        f'find {src_dir} -name "CMakeLists.txt" -path "*/llama.cpp/*" 2>/dev/null',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print("CMakeLists.txt files:", result.stdout[:500])
    
    # Try to find where the cmake options are set in the Python build code
    result = subprocess.run(
        f'grep -rn "GGML_" {src_dir}/vendor/ 2>/dev/null | head -20',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print("GGML_ in vendor:", result.stdout[:500])

print("\\n=== DONE ===")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Downloading source and patching...")
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
