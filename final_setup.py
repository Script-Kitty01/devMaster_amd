import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os, time, socket

# Step 1: Install gradio
print('=== Installing Gradio ===')
result = subprocess.run(['/opt/venv/bin/pip', 'install', 'gradio'], capture_output=True, text=True, timeout=120)
print('Gradio install rc:', result.returncode)

# Step 2: Try to download frpc using Python requests with streaming
import requests as req
dest = '/root/.cache/huggingface/gradio/frpc/frpc_linux_amd64_v0.3'
os.makedirs('/root/.cache/huggingface/gradio/frpc', exist_ok=True)

# Remove any existing 0-byte file
if os.path.exists(dest):
    os.remove(dest)

# Try multiple URLs
urls = [
    'https://cdn-media.huggingface.co/frpc-gradio-0.3/frpc_linux_amd64',
    'https://github.com/fatedier/frp/releases/download/v0.61.1/frp_0.61.1_linux_amd64.tar.gz',
]

for url in urls:
    print(f'\\nTrying: {url}')
    try:
        r = req.get(url, timeout=180, stream=True)
        print(f'Status: {r.status_code}, Length: {r.headers.get("content-length", "unknown")}')
        if r.status_code == 200:
            with open(dest, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
            os.chmod(dest, 0o755)
            size = os.path.getsize(dest)
            print(f'SUCCESS! Downloaded {size} bytes')
            if size > 100000:
                break
            else:
                print('File too small, trying next URL')
                os.remove(dest)
    except Exception as e:
        print(f'Failed: {e}')

# Check result
if os.path.exists(dest):
    print(f'\\nFinal frpc size: {os.path.getsize(dest)}')
else:
    print('\\nfrpc not downloaded')

# Step 3: Start Gradio
print('\\n=== Starting Gradio ===')
os.chdir('/workspace/template-repos/template-1005/repo')
proc = subprocess.Popen(
    ['/opt/venv/bin/python', '-u', 'src/ui/gradio_app.py'],
    stdout=open('/tmp/gradio_final_out.txt', 'w', buffering=1),
    stderr=open('/tmp/gradio_final_err.txt', 'w', buffering=1),
    env={**os.environ, 'PYTHONUNBUFFERED': '1'},
    cwd='/workspace/template-repos/template-1005/repo'
)
print(f'Gradio PID: {proc.pid}')

# Wait for port
for i in range(30):
    time.sleep(2)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    if s.connect_ex(('127.0.0.1', 7860)) == 0:
        print(f'Port 7860 OPEN after {(i+1)*2}s')
        s.close()
        break
    s.close()
else:
    print('Port 7860 did not open')

# Show output
with open('/tmp/gradio_final_out.txt') as f:
    print('Gradio stdout:', f.read()[-500:])
with open('/tmp/gradio_final_err.txt') as f:
    err = f.read()
    if err:
        print('Gradio stderr:', err[-500:])
"""

msg_id = 'fs'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 300
while time.time() < deadline:
    ws.settimeout(30)
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
