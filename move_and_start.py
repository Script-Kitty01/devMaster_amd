import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os, shutil, time, socket

# Move frpc to gradio cache
src = '/workspace/template-repos/template-1005/repo/frpc_linux_amd64_v0.3'
dest_dir = '/root/.cache/huggingface/gradio/frpc'
dest = f'{dest_dir}/frpc_linux_amd64_v0.3'

os.makedirs(dest_dir, exist_ok=True)
shutil.move(src, dest)
os.chmod(dest, 0o755)
print(f'Moved frpc: {os.path.getsize(dest)} bytes')

# Kill any existing gradio
subprocess.run(['pkill', '-f', 'gradio_app'], capture_output=True)
time.sleep(2)

# Start Gradio with share=True
print('Starting Gradio with share=True...')
os.chdir('/workspace/template-repos/template-1005/repo')

proc = subprocess.Popen(
    ['/opt/venv/bin/python', '-u', '-c', '''
import sys
sys.path.insert(0, '/workspace/template-repos/template-1005/repo')
from src.ui.gradio_app import demo
demo.launch(server_name="0.0.0.0", server_port=7860, share=True, show_error=True)
'''],
    stdout=open('/tmp/gradio_share_final_out.txt', 'w', buffering=1),
    stderr=open('/tmp/gradio_share_final_err.txt', 'w', buffering=1),
    env={**os.environ, 'PYTHONUNBUFFERED': '1'},
    cwd='/workspace/template-repos/template-1005/repo'
)
print(f'Gradio PID: {proc.pid}')

# Wait for port and share link
for i in range(45):
    time.sleep(2)
    # Check port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    port_open = s.connect_ex(('127.0.0.1', 7860)) == 0
    s.close()
    
    # Check output for share link
    with open('/tmp/gradio_share_final_out.txt') as f:
        out = f.read()
    with open('/tmp/gradio_share_final_err.txt') as f:
        err = f.read()
    
    if port_open:
        print(f'Port 7860 OPEN after {(i+1)*2}s')
    
    if 'Running on public URL' in out or 'gradio.live' in out:
        print(f'SHARE LINK FOUND after {(i+1)*2}s!')
        break
    
    if i % 5 == 0:
        print(f'... waiting ({i*2}s), port_open={port_open}')

# Show final output
print('\\n=== STDOUT ===')
with open('/tmp/gradio_share_final_out.txt') as f:
    print(f.read())
print('\\n=== STDERR ===')
with open('/tmp/gradio_share_final_err.txt') as f:
    err = f.read()
    if err:
        print(err)
"""

msg_id = 'mas'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 150
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
