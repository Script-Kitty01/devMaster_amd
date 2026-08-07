import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess, time, os, sys

print('Reinstalling llama-cpp-python with HIP/ROCm BLAS...')

# Set CMAKE_ARGS for HIP
env = os.environ.copy()
env['CMAKE_ARGS'] = '-DGGML_HIPBLAS=ON -DCMAKE_C_COMPILER=/opt/rocm/llvm/bin/clang -DCMAKE_CXX_COMPILER=/opt/rocm/llvm/bin/clang++ -DAMDGPU_TARGETS=gfx1100'
env['FORCE_CMAKE'] = '1'

r = subprocess.run(
    ['/opt/venv/bin/pip', 'install', '--force-reinstall', '--no-cache-dir', 'llama-cpp-python'],
    capture_output=True, text=True, timeout=300, env=env
)
print(r.stdout[-1000:] if len(r.stdout) > 1000 else r.stdout)
if r.returncode != 0:
    print('STDERR:', r.stderr[-1000:])
    print('\nTrying with GGML_HIPBLAS=on (lowercase)...')
    env['CMAKE_ARGS'] = '-DGGML_HIPBLAS=on -DAMDGPU_TARGETS=gfx1100'
    r = subprocess.run(
        ['/opt/venv/bin/pip', 'install', '--force-reinstall', '--no-cache-dir', 'llama-cpp-python'],
        capture_output=True, text=True, timeout=300, env=env
    )
    print(r.stdout[-1000:] if len(r.stdout) > 1000 else r.stdout)
    if r.returncode != 0:
        print('STDERR:', r.stderr[-1000:])
"""

msg_id = 'bh'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 360
while time.time() < deadline:
    ws.settimeout(60)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        pid = data.get('parent_header', {}).get('msg_id', '')
        if pid != msg_id:
            continue
        if data.get('msg_type') == 'stream':
            print(data.get('content', {}).get('text', ''), end='', flush=True)
        elif data.get('msg_type') == 'error':
            print('ERROR:', '\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
