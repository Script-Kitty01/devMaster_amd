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

dest = '/root/.cache/huggingface/gradio/frpc/frpc_linux_amd64_v0.3'

# Try gradio.app domain (reachable per test)
urls = [
    'https://gradio.app/frpc_linux_amd64_v0.3',
    'https://gradio.app/frpc/frpc_linux_amd64_v0.3',
    'https://gradio.app/download/frpc_linux_amd64_v0.3',
]

for url in urls:
    print(f'Trying: {url}')
    result = subprocess.run(
        ['wget', '--timeout=30', '--tries=2', '-O', dest, url],
        capture_output=True, text=True, timeout=60
    )
    print(f'rc: {result.returncode}')
    if result.returncode == 0:
        os.chmod(dest, 0o755)
        print(f'SUCCESS! Size: {os.path.getsize(dest)}')
        break
    else:
        print(f'Failed: {result.stderr[-200:]}')
else:
    print('All URLs failed')
    
    # Last resort: try pip install with frpc
    print('\\nTrying pip install gradio frpc extras...')
    result = subprocess.run(['/opt/venv/bin/pip', 'install', 'gradio[frpc]'], capture_output=True, text=True, timeout=60)
    print(result.stdout[-300:])
    print(result.stderr[-300:])
"""

msg_id = 'fa'
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
