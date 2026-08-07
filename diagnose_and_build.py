"""
Diagnose HIP/ROCm setup, then build with proper paths.
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

# Step 1: Diagnose HIP/ROCm
print("=== Step 1: HIP/ROCm Diagnosis ===")

# Find HIP
result = subprocess.run('which hipcc 2>/dev/null; hipcc --version 2>&1 | head -3', 
                       shell=True, capture_output=True, text=True, executable='/bin/bash')
print("hipcc:", result.stdout.strip())

# Find ROCm
result = subprocess.run('find /opt/rocm* -maxdepth 0 -type d 2>/dev/null; ls /opt/rocm*/lib/libamdhip64* 2>/dev/null; ls /opt/rocm*/lib/librocblas* 2>/dev/null',
                       shell=True, capture_output=True, text=True, executable='/bin/bash')
print("ROCm libs:", result.stdout.strip())

# Find HIP headers
result = subprocess.run('find /opt/rocm*/include -name "hip_runtime_api.h" 2>/dev/null',
                       shell=True, capture_output=True, text=True, executable='/bin/bash')
print("HIP headers:", result.stdout.strip())

# Check cmake can find HIP
result = subprocess.run(
    'cmake --find-package -DNAME=hip -DCOMPILER_ID=GNU -DLANGUAGE=CXX -DMODE=EXIST 2>&1 || echo "cmake find_package failed"',
    shell=True, capture_output=True, text=True, executable='/bin/bash')
print("cmake find HIP:", result.stdout.strip()[:500])

# Check for HIP cmake config files
result = subprocess.run(
    'find /opt/rocm* -name "hip-config.cmake" -o -name "HIPConfig.cmake" 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash')
print("HIP cmake config:", result.stdout.strip())

# Check ROCm version
result = subprocess.run('cat /opt/rocm*/.info/version 2>/dev/null || apt list --installed 2>/dev/null | grep rocm',
                       shell=True, capture_output=True, text=True, executable='/bin/bash')
print("ROCm version:", result.stdout.strip()[:500])

# Step 2: Try building with explicit CMAKE_PREFIX_PATH
print("\\n=== Step 2: Building with CMAKE_PREFIX_PATH ===")
LLAMA_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp'
BUILD_DIR = f'{LLAMA_DIR}/build_hipblas2'

# Clean
subprocess.run(f'rm -rf {BUILD_DIR}', shell=True, capture_output=True, text=True, executable='/bin/bash')
os.makedirs(BUILD_DIR, exist_ok=True)

# Find ROCm path
result = subprocess.run('ls -d /opt/rocm* 2>/dev/null | head -1', shell=True, capture_output=True, text=True, executable='/bin/bash')
rocm_path = result.stdout.strip()
print(f"ROCm path: {rocm_path}")

# Configure with explicit paths
cmake_cmd = (
    f'cd {BUILD_DIR} && '
    f'CMAKE_PREFIX_PATH="{rocm_path}" '
    f'cmake .. '
    f'-DGGML_HIPBLAS=ON '
    f'-DAMDGPU_TARGETS=gfx1100 '
    f'-DCMAKE_BUILD_TYPE=Release '
    f'-DBUILD_SHARED_LIBS=ON '
    f'-DCMAKE_C_COMPILER=/usr/bin/hipcc '
    f'-DCMAKE_CXX_COMPILER=/usr/bin/hipcc '
    f'2>&1'
)
print(f"CMD: {cmake_cmd[:200]}...")

result = subprocess.run(cmake_cmd, shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash')
print(result.stdout[-3000:])

# Check for HIPBLAS in output
hipblas_found = 'GGML_HIPBLAS' in result.stdout and ('HIP found' in result.stdout or 'hipblas' in result.stdout.lower())
print(f"\\nHIPBLAS in cmake: {'*** YES ***' if hipblas_found else 'NO'}")

# Check for key indicators
for line in result.stdout.split('\\n'):
    if any(kw in line.lower() for kw in ['hip', 'rocm', 'amd', 'blas', 'gpu', 'backend']):
        print(f"  >> {line.strip()[:150]}")

if result.returncode != 0:
    print(f"CMAKE FAILED (rc={result.returncode})")
    print("STDERR:", result.stderr[-2000:])
    sys.exit(1)

# Step 3: Build if HIPBLAS found
if hipblas_found:
    print("\\n=== Step 3: Building ===")
    result = subprocess.run(
        f'cd {BUILD_DIR} && cmake --build . --config Release -j$(nproc) 2>&1 | tail -40',
        shell=True, capture_output=True, text=True, timeout=600, executable='/bin/bash'
    )
    print(result.stdout[-3000:])
    print(f"Build RC: {result.returncode}")
    
    if result.returncode == 0:
        # Find and copy libs
        print("\\n=== Step 4: Installing libs ===")
        result = subprocess.run(
            f'find {BUILD_DIR} -name "*.so" -type f',
            shell=True, capture_output=True, text=True, executable='/bin/bash'
        )
        print("Built libs:", result.stdout[:1000])
        
        # Copy to llama-cpp-python
        result = subprocess.run(
            'python3.12 -c "import llama_cpp; import os; print(os.path.dirname(llama_cpp.__file__))"',
            shell=True, capture_output=True, text=True, executable='/bin/bash'
        )
        llama_dir = result.stdout.strip()
        lib_dir = f'{llama_dir}/lib'
        
        result = subprocess.run(
            f'cp -v {BUILD_DIR}/bin/*.so* {lib_dir}/ 2>&1 && echo "COPIED"',
            shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
        )
        print(result.stdout)
        
        # Verify
        result = subprocess.run(
            f'strings {lib_dir}/libllama.so 2>/dev/null | grep -i hipblas | head -5',
            shell=True, capture_output=True, text=True, executable='/bin/bash'
        )
        print(f"HIPBLAS in lib: {'*** YES ***' if result.stdout.strip() else 'NO'}")
else:
    print("\\nHIPBLAS not found by cmake. Trying alternative approach...")
    # Maybe the vendored llama.cpp is too old? Check its CMakeLists
    result = subprocess.run(
        f'grep -n "GGML_HIPBLAS\\|hipblas\\|HIP" {LLAMA_DIR}/CMakeLists.txt | head -20',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print("GGML_HIPBLAS in llama.cpp CMakeLists:", result.stdout[:500])
    
    result = subprocess.run(
        f'grep -rn "GGML_HIPBLAS" {LLAMA_DIR}/ggml/ 2>/dev/null | head -10',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    print("GGML_HIPBLAS in ggml:", result.stdout[:500])

print("\\n=== DONE ===")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Diagnosing HIP/ROCm and building...")
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
