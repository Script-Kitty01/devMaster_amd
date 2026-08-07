"""Write build script to remote, launch with setsid, return immediately"""
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

# Configure
result = subprocess.run(
    'cd ' + BUILD_DIR + ' && cmake .. -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100 -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=OFF 2>&1',
    shell=True, capture_output=True, text=True, timeout=120, executable='/bin/bash'
)

if 'Including HIP backend' not in result.stdout:
    print('FATAL: HIP not configured')
    print(result.stdout[-500:])
else:
    print('HIP_CONFIGURED: YES')
    
    # Write a standalone Python build script
    build_py = '''import subprocess, os, sys
BUILD_DIR = "''' + BUILD_DIR + '''"
print("Build starting in: " + BUILD_DIR, flush=True)
result = subprocess.run(
    "cd " + BUILD_DIR + " && cmake --build . --config Release --target ggml llama -j$(nproc) 2>&1",
    shell=True, capture_output=True, text=True, timeout=3600, executable="/bin/bash"
)
with open("/tmp/build_hip_result.txt", "w") as f:
    f.write("RC=" + str(result.returncode) + "\\n")
    f.write(result.stdout[-5000:])
    if result.stderr:
        f.write("\\nSTDERR:\\n" + result.stderr[-2000:])
print("Build done, rc=" + str(result.returncode), flush=True)

# If success, copy libs
if result.returncode == 0:
    import subprocess as sp
    r = sp.run("python3.12 -c \\"import llama_cpp; import os; print(os.path.dirname(llama_cpp.__file__))\\"", shell=True, capture_output=True, text=True, executable="/bin/bash")
    llama_dir = r.stdout.strip()
    lib_dir = llama_dir + "/lib"
    sp.run("mkdir -p " + lib_dir + "/backup", shell=True, capture_output=True, executable="/bin/bash")
    sp.run("cp " + lib_dir + "/*.so* " + lib_dir + "/backup/ 2>/dev/null", shell=True, capture_output=True, executable="/bin/bash")
    r = sp.run("cp -v " + BUILD_DIR + "/bin/*.so* " + lib_dir + "/ 2>&1", shell=True, capture_output=True, text=True, timeout=30, executable="/bin/bash")
    with open("/tmp/build_hip_result.txt", "a") as f:
        f.write("\\nCOPY:\\n" + r.stdout)
    
    # Check HIP symbols
    r = sp.run("strings " + lib_dir + "/libllama.so 2>/dev/null | grep -i hipblas | head -5", shell=True, capture_output=True, text=True, executable="/bin/bash")
    with open("/tmp/build_hip_result.txt", "a") as f:
        f.write("\\nHIPBLAS_CHECK: " + ("YES" if r.stdout.strip() else "NO"))
    
    # Test GPU load
    test_code = "import os, sys\\nsys.path.insert(0, \\"/workspace/template-repos/template-1005/repo\\")\\nfrom llama_cpp import Llama\\nmodel_path = \\"/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf\\"\\ntry:\\n    llm = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=2048, n_batch=512, verbose=True)\\n    print(\\"\\\\n*** GPU LOAD SUCCESS! ***\\")\\n    result = llm(\\"Hello\\", max_tokens=20)\\n    print(result[\\"choices\\"][0][\\"text\\"])\\nexcept Exception as e:\\n    print(f\\"ERROR: {e}\\")"
    r = sp.run(["python3.12", "-c", test_code], capture_output=True, text=True, timeout=120)
    with open("/tmp/build_hip_result.txt", "a") as f:
        f.write("\\nGPU_TEST:\\n" + r.stdout)
        if r.stderr:
            f.write("\\nSTDERR:\\n" + r.stderr[-1000:])
'''
    
    with open('/tmp/run_build.py', 'w') as f:
        f.write(build_py)
    
    # Launch with setsid for full detachment
    subprocess.Popen(
        ['python3.12', '/tmp/run_build.py'],
        stdout=open('/tmp/build_hip_detached.log', 'w'),
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True
    )
    
    import time
    time.sleep(3)
    
    # Verify
    r = subprocess.run('pgrep -f run_build.py || echo "NOT_RUNNING"', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print('Build script PID: ' + r.stdout.strip())
    
    r = subprocess.run('cat /tmp/build_hip_detached.log 2>/dev/null || echo "No log yet"', shell=True, capture_output=True, text=True, executable='/bin/bash')
    print('Log: ' + r.stdout.strip()[:200])
    
    print('DETACHED_BUILD_LAUNCHED: True')
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(10)
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
print('\nDone - detached build launched')
