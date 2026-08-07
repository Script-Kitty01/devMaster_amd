import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import os, subprocess, urllib.request

# Create directory
os.makedirs('/root/.cache/huggingface/gradio/frpc', exist_ok=True)

# Download frpc
url = 'https://cdn-media.huggingface.co/frpc-gradio-0.3/frpc_linux_amd64'
dest = '/root/.cache/huggingface/gradio/frpc/frpc_linux_amd64_v0.3'

print(f'Downloading {url}...')
try:
    urllib.request.urlretrieve(url, dest)
    print(f'Downloaded to {dest}')
    os.chmod(dest, 0o755)
    print('Made executable')
    print('Size:', os.path.getsize(dest))
except Exception as e:
    print(f'Download failed: {e}')
    # Try wget
    result = subprocess.run(['wget', '-O', dest, url], capture_output=True, text=True, timeout=30)
    print('wget stdout:', result.stdout[-500:])
    print('wget stderr:', result.stderr[-500:])
    if result.returncode == 0:
        os.chmod(dest, 0o755)
        print('Downloaded via wget, size:', os.path.getsize(dest))
"""

msg_id = 'frpc'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 60
while time.time() < deadline:
    ws.settimeout(15)
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
