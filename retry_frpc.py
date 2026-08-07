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

# Remove the 0-byte file
os.remove('/root/.cache/huggingface/gradio/frpc/frpc_linux_amd64_v0.3')
print('Removed 0-byte frpc')

# Try downloading with Python requests (more reliable than wget)
import urllib.request
import ssl

dest = '/root/.cache/huggingface/gradio/frpc/frpc_linux_amd64_v0.3'
url = 'https://cdn-media.huggingface.co/frpc-gradio-0.3/frpc_linux_amd64'

print(f'Downloading {url}...')
ctx = ssl.create_default_context()
try:
    with urllib.request.urlopen(url, context=ctx, timeout=120) as resp:
        data = resp.read()
        with open(dest, 'wb') as f:
            f.write(data)
        os.chmod(dest, 0o755)
        print(f'SUCCESS! Downloaded {len(data)} bytes')
except Exception as e:
    print(f'urllib failed: {e}')
    
    # Try with requests
    import requests as req
    try:
        r = req.get(url, timeout=120, stream=True)
        r.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        os.chmod(dest, 0o755)
        print(f'SUCCESS via requests! Size: {os.path.getsize(dest)}')
    except Exception as e2:
        print(f'requests failed: {e2}')

# Check result
if os.path.exists(dest):
    print(f'Final size: {os.path.getsize(dest)}')
else:
    print('File does not exist')
"""

msg_id = 'rf'
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
