"""Build with UI/tools disabled to avoid HF download hang"""
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
BUILD_DIR = LLAMA_DIR + '/build_hip'

# Clean
subprocess.run('rm -rf ' + BUILD_DIR, shell=True, capture_output=True, text=True, executable='/bin/bash')
os.makedirs(BUILD_DIR, exist_ok=True)

# Configure - DISABLE UI and tools to avoid HF download
result = subprocess.run(
    'cd ' + BUILD_DIR + ' && cmake .. '
    '-DGGML_HIP=ON '
    '-DAMDGPU_TARGETS=gfx1100 '
    '-DCMAKE_BUILD_TYPE=Release '
    '-DBUILD_SHARED_LIBS=ON '
    '-DLLAMA_BUILD_TESTS=OFF '
    '-DLLAMA_BUILD_EXAMPLES=OFF '
    '-DLLAMA_BUILD_SERVER=OFF '
    '2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)

if 'Including HIP backend' not in result.stdout:
    print('FATAL: HIP backend not configured!')
    print(result.stdout[-1000:])
else:
    print('HIP_CONFIGURED: YES')
    
    # Check what targets are available
    r = subprocess.run('cd ' + BUILD_DIR + ' && cmake --build . --target help 2>&1 | grep -E "ggml|llama" | head -20', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print('Targets:')
    print(r.stdout[:500])
    
    # Build just the essential targets: ggml and llama
    print('Building ggml + llama (HIP)...')
    result = subprocess.run(
        'cd ' + BUILD_DIR + ' && cmake --build . --config Release --target ggml llama -j$(nproc) 2>&1',
        shell=True, capture_output=True, text=True, timeout=900, executable='/bin/bash'
    )
    
    # Show last 30 lines
    lines = result.stdout.split('\\n')
    print('\\n'.join(lines[-30:]))
    
    if result.returncode != 0:
        print('BUILD FAILED with code: ' + str(result.returncode))
        # Show errors
        for line in lines:
            if 'error:' in line.lower():
                print('ERROR: ' + line)
    else:
        print('BUILD_SUCCESS: rc=' + str(result.returncode))
        
        # Check for .so files
        r = subprocess.run('find ' + BUILD_DIR + ' -name "*.so" -type f | head -20', shell=True, capture_output=True, text=True, executable='/bin/bash')
        print('\\n.so files:')
        print(r.stdout)
        
        # Check HIP symbols
        r = subprocess.run('nm -D ' + BUILD_DIR + '/bin/libggml.so 2>/dev/null | grep -c hip || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
        print('HIP symbols in libggml.so: ' + r.stdout.strip())
        
        r = subprocess.run('nm -D ' + BUILD_DIR + '/bin/libllama.so 2>/dev/null | grep -c hip || echo "0"', shell=True, capture_output=True, text=True, executable='/bin/bash')
        print('HIP symbols in libllama.so: ' + r.stdout.strip())
        
        # Check hipBLAS strings
        r = subprocess.run('strings ' + BUILD_DIR + '/bin/libllama.so 2>/dev/null | grep -i hipblas | head -5', shell=True, capture_output=True, text=True, executable='/bin/bash')
        print('hipBLAS strings: ' + (r.stdout.strip() or 'NONE'))
        
        if r.stdout.strip():
            print('\\n*** HIPBLAS BUILD SUCCESSFUL! ***')
            
            # Copy to llama-cpp-python
            r = subprocess.run('python3.12 -c "import llama_cpp; import os; print(os.path.dirname(llama_cpp.__file__))"', shell=True, capture_output=True, text=True, executable='/bin/bash')
            llama_dir = r.stdout.strip()
            lib_dir = llama_dir + '/lib'
            
            # Backup
            subprocess.run('mkdir -p ' + lib_dir + '/backup', shell=True, capture_output=True, executable='/bin/bash')
            subprocess.run('cp ' + lib_dir + '/*.so* ' + lib_dir + '/backup/ 2>/dev/null', shell=True, capture_output=True, executable='/bin/bash')
            
            # Copy new libs
            r = subprocess.run('cp -v ' + BUILD_DIR + '/bin/*.so* ' + lib_dir + '/ 2>&1', shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash')
            print('\\nCopy result:')
            print(r.stdout)
            
            # Verify final
            r = subprocess.run('strings ' + lib_dir + '/libllama.so 2>/dev/null | grep -i hipblas | head -5', shell=True, capture_output=True, text=True, executable='/bin/bash')
            print('Final hipBLAS check: ' + ('YES!' if r.stdout.strip() else 'FAILED'))
            
            # Test GPU load
            if r.stdout.strip():
                print('\\n=== Testing GPU model load ===')
                test_code = 'import os, sys\\nsys.path.insert(0, "/workspace/template-repos/template-1005/repo")\\nfrom llama_cpp import Llama\\nmodel_path = "/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"\\ntry:\\n    llm = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=2048, n_batch=512, verbose=True)\\n    print("\\\\n*** GPU LOAD SUCCESS! ***")\\n    result = llm("Hello, what is 2+2?", max_tokens=50)\\n    print(f"Response: {result[\\'choices\\'][0][\\'text\\']}")\\nexcept Exception as e:\\n    print(f"ERROR: {e}")'
                r = subprocess.run(['python3.12', '-c', test_code], capture_output=True, text=True, timeout=120)
                print(r.stdout)
                if r.stderr:
                    print('STDERR:', r.stderr[-1000:])

print('\\n=== DONE ===')
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Building with UI disabled (900s timeout)...")
time.sleep(10)

output = ""
while True:
    try:
        ws.settimeout(10)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            output += msg['content']['text']
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
        if msg.get('msg_type') == 'status' and msg.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        if 'DONE' in output:
            break
        if 'timed out' in str(e).lower():
            continue
        break

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\n=== Complete ===')
