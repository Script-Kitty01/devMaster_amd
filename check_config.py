import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess, os

os.chdir('/workspace/template-repos/template-1005/repo')

# Check config
test_code = '''
import sys
sys.path.insert(0, ".")
from src.llm.rocm_service import ROCmLLM

llm = ROCmLLM.get_instance()
cfg = llm.config
print(f"model_path: {cfg.model_path}")
print(f"n_gpu_layers: {cfg.n_gpu_layers}")
print(f"n_ctx: {cfg.n_ctx}")
print(f"n_batch: {cfg.n_batch}")
print(f"verbose: {cfg.verbose}")
'''

r = subprocess.run(['/opt/venv/bin/python', '-c', test_code],
                   capture_output=True, text=True, cwd='/workspace/template-repos/template-1005/repo', timeout=30)
print(r.stdout)
if r.stderr:
    print('STDERR:', r.stderr[-500:])
"""

msg_id = 'ccfg'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 40
while time.time() < deadline:
    ws.settimeout(10)
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
