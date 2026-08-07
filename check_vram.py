"""Check VRAM and Gradio status"""
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
import subprocess

# Check VRAM
r = subprocess.run('rocm-smi --showmeminfo vram 2>/dev/null || rocm-smi 2>/dev/null | head -30', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== ROCM-SMI ===')
print(r.stdout)

# Check Gradio process
r = subprocess.run('ps aux | grep -E "gradio|python.*app" | grep -v grep', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== GRADIO PROCESS ===')
print(r.stdout)

# Check if Gradio is responding
r = subprocess.run('curl -s -o /dev/null -w "%{http_code}" http://localhost:7860', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== GRADIO HTTP STATUS ===')
print(r.stdout)

# Check GPU processes
r = subprocess.run('fuser /dev/kfd 2>/dev/null || echo "no kfd users"', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== KFD USERS ===')
print(r.stdout)

# Check if libggml-hip.so is loaded by any process
r = subprocess.run('grep -l libggml-hip /proc/*/maps 2>/dev/null | head -5', shell=True, capture_output=True, text=True, executable='/bin/bash')
print('=== PROCESSES USING libggml-hip ===')
print(r.stdout if r.stdout else 'None yet (Gradio may lazy-load)')
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

time.sleep(5)
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
print('\nDone')
