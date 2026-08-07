import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

# Create a terminal
r = requests.post(f'{base}/api/terminals', headers=headers)
term_name = r.json()['name']
print(f'Terminal: {term_name}')

# Connect to terminal websocket
ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/terminals/websocket/{term_name}?token=amd-oneclick')

def send_cmd(cmd):
    ws.send(json.dumps(['stdin', cmd + '\r\n']))

def read_output(timeout_sec=10):
    output = []
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ws.settimeout(3)
        try:
            resp = ws.recv()
            data = json.loads(resp)
            if data[0] == 'stdout':
                output.append(data[1])
        except:
            break
    return ''.join(output)

# Wait for prompt
time.sleep(2)
print(read_output(3))

# Check ROCm
send_cmd('which hipcc && hipcc --version 2>&1 | head -3')
time.sleep(2)
print(read_output(5))

# Install llama-cpp-python with ROCm
print('\n=== Installing llama-cpp-python with HIP BLAS (this takes ~5-10 min) ===')
send_cmd('cd /workspace/template-repos/template-1005/repo && CMAKE_ARGS="-DGGML_HIPBLAS=on -DCMAKE_C_COMPILER=/opt/rocm/bin/hipcc -DCMAKE_CXX_COMPILER=/opt/rocm/bin/hipcc -DAMDGPU_TARGETS=gfx1100" pip install llama-cpp-python --force-reinstall --no-cache-dir --break-system-packages 2>&1')

# Wait for install to complete
time.sleep(30)
out = read_output(30)
print(out[-500:] if len(out) > 500 else out)

# Keep reading until we see a prompt
for i in range(20):
    time.sleep(15)
    out = read_output(15)
    if out:
        print(out[-300:] if len(out) > 300 else out)
    if '$' in out or '#' in out:
        print('\n=== Install complete! ===')
        break

# Verify
send_cmd('python3 -c "from llama_cpp import Llama; print(\'llama-cpp-python installed!\'); l=Llama(model_path=\'/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf\', n_gpu_layers=-1, n_ctx=2048, verbose=False); print(\'GPU layers:\', l.n_gpu_layers)"')
time.sleep(5)
print(read_output(10))

ws.close()
print('\nDone!')
