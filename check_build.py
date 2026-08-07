"""
Check if the HIP build completed, copy libs, and test GPU.
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
ws = create_connection(ws_url, timeout=30)
msg = json.loads(ws.recv())

code = """
import subprocess, os, sys

BUILD_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp/build_hip'

# Check if build is still running
result = subprocess.run(
    'pgrep -f "cmake --build" > /dev/null && echo "RUNNING" || echo "DONE"',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
build_status = result.stdout.strip()
print(f"Build status: {build_status}")

# Show log tail
result = subprocess.run(
    'tail -30 /tmp/build_hip.log 2>/dev/null || echo "No log file"',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("=== Build log (last 30 lines) ===")
print(result.stdout)

# Check for errors
result = subprocess.run(
    'grep -c "error:" /tmp/build_hip.log 2>/dev/null || echo "0"',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
error_count = result.stdout.strip()
print(f"Error count in log: {error_count}")

if build_status == 'RUNNING':
    print("Build still running. Check again later.")
elif build_status == 'DONE':
    # Find built .so files
    result = subprocess.run(
        f'find {BUILD_DIR} -name "*.so" -type f 2>/dev/null | head -20',
        shell=True, capture_output=True, text=True, executable='/bin/bash'
    )
    so_files = result.stdout.strip()
    print(f"\\nBuilt .so files:\\n{so_files}")
    
    if not so_files:
        print("No .so files found! Build may have failed.")
        # Show full error log
        result = subprocess.run(
            'grep -B2 -A5 "error:" /tmp/build_hip.log 2>/dev/null | head -60',
            shell=True, capture_output=True, text=True, executable='/bin/bash'
        )
        print(result.stdout)
    else:
        # Check for HIP symbols in libllama
        result = subprocess.run(
            f'for f in $(find {BUILD_DIR}/bin -name "libllama.so" -type f 2>/dev/null); do echo "=== $f ==="; nm -D "$f" 2>/dev/null | grep -i hip | head -5; done',
            shell=True, capture_output=True, text=True, executable='/bin/bash'
        )
        print(f"\\nHIP symbols in libllama.so:\\n{result.stdout[:1000]}")
        
        # Check for hipBLAS strings
        result = subprocess.run(
            f'strings {BUILD_DIR}/bin/libllama.so 2>/dev/null | grep -i hipblas | head -5',
            shell=True, capture_output=True, text=True, executable='/bin/bash'
        )
        print(f"hipBLAS strings: {result.stdout.strip()}")
        
        # Copy to llama-cpp-python
        result = subprocess.run(
            'python3.12 -c "import llama_cpp; import os; print(os.path.dirname(llama_cpp.__file__))"',
            shell=True, capture_output=True, text=True, executable='/bin/bash'
        )
        llama_dir = result.stdout.strip()
        lib_dir = f'{llama_dir}/lib'
        print(f"\\nTarget lib dir: {lib_dir}")
        
        # Backup old libs
        subprocess.run(f'mkdir -p {lib_dir}/backup', shell=True, capture_output=True, executable='/bin/bash')
        subprocess.run(f'cp {lib_dir}/*.so* {lib_dir}/backup/ 2>/dev/null', shell=True, capture_output=True, executable='/bin/bash')
        
        # Copy new libs
        result = subprocess.run(
            f'cp -v {BUILD_DIR}/bin/*.so* {lib_dir}/ 2>&1',
            shell=True, capture_output=True, text=True, timeout=30, executable='/bin/bash'
        )
        print(f"Copy result:\\n{result.stdout}")
        
        # Verify final state
        result = subprocess.run(
            f'strings {lib_dir}/libllama.so 2>/dev/null | grep -i hipblas | head -5',
            shell=True, capture_output=True, text=True, executable='/bin/bash'
        )
        has_hip = bool(result.stdout.strip())
        print(f"\\n*** HIPBLAS in final libllama.so: {'YES!' if has_hip else 'NO - FAILED'} ***")
        
        if has_hip:
            # Test GPU model load
            print("\\n=== Testing GPU model load ===")
            test_code = '''
import os, sys
sys.path.insert(0, "/workspace/template-repos/template-1005/repo")
from llama_cpp import Llama
model_path = "/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
try:
    llm = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=2048, n_batch=512, verbose=True)
    print("\\n*** GPU LOAD SUCCESS! ***")
    result = llm("Hello, what is 2+2?", max_tokens=50)
    print(f"Response: {result['choices'][0]['text']}")
except Exception as e:
    print(f"ERROR: {e}")
'''
            result = subprocess.run(
                [sys.executable, '-c', test_code],
                capture_output=True, text=True, timeout=120
            )
            print(result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr[-1000:])

print("\\n=== CHECK COMPLETE ===")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Checking build status...")
time.sleep(5)

output = ""
ws.settimeout(60)
while True:
    try:
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            output += msg['content']['text']
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
        if msg.get('msg_type') == 'status' and msg.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        if 'timed out' in str(e).lower():
            continue
        break

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\n=== Done ===')
