import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os

# Check JupyterLab
result = subprocess.run(['pgrep', '-f', 'jupyter-lab'], capture_output=True, text=True)
print('JupyterLab PID:', result.stdout.strip())

# Check Gradio
result = subprocess.run(['pgrep', '-f', 'gradio_app'], capture_output=True, text=True)
print('Gradio PID:', result.stdout.strip())

# Try downloading frpc with wget --retry
os.makedirs('/root/.cache/huggingface/gradio/frpc', exist_ok=True)
dest = '/root/.cache/huggingface/gradio/frpc/frpc_linux_amd64_v0.3'

# Try multiple URLs
urls = [
    'https://cdn-media.huggingface.co/frpc-gradio-0.3/frpc_linux_amd64',
    'https://gradio.app/frpc_linux_amd64_v0.3',
]

for url in urls:
    print(f'Trying: {url}')
    result = subprocess.run(
        ['wget', '--timeout=60', '--tries=3', '--retry-connrefused', '-O', dest, url],
        capture_output=True, text=True, timeout=120
    )
    print(f'rc: {result.returncode}')
    if result.returncode == 0:
        os.chmod(dest, 0o755)
        print(f'SUCCESS! Size: {os.path.getsize(dest)}')
        break
    else:
        print(f'Failed: {result.stderr[-300:]}')
else:
    print('All URLs failed')
"""

msg_id = 'dl2'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 180
while time.time() < deadline:
    ws.settimeout(20)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        pid = data.get('parent_header', {}).get('msg_id', '')
        if pid != msg_id:
            continue
        if data.get('msg_type') == 'stream':
            print(data.get('content', {}).get('text', ''), end='', flush=True)
        elif data.get('msg_type') == 'error':
            print('ERROR:', '\\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
