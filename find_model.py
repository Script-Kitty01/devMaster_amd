import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

def run_code(code, msg_id, timeout_sec=120):
    msg = json.dumps({
        'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
        'parent_header': {}, 'metadata': {},
        'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
        'channel': 'shell'
    })
    ws.send(msg)
    
    output = []
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ws.settimeout(10)
        try:
            resp = ws.recv()
            data = json.loads(resp)
            pid = data.get('parent_header', {}).get('msg_id', '')
            if pid != msg_id:
                continue
            if data.get('msg_type') == 'stream':
                text = data.get('content', {}).get('text', '')
                output.append(text)
                print(text, end='', flush=True)
            elif data.get('msg_type') == 'execute_result':
                text = data.get('content', {}).get('data', {}).get('text/plain', '')
                output.append(text)
                print(text)
            elif data.get('msg_type') == 'error':
                text = f"\nERROR: {data.get('content', {}).get('ename', '')}: {data.get('content', {}).get('evalue', '')}"
                output.append(text)
                print(text)
            elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
                break
        except:
            break
    return ''.join(output)

# Search everywhere for GGUF files
print('=== Searching for GGUF files ===')
run_code("""
import subprocess, os

# Search common locations
paths = [
    '/workspace',
    '/home',
    '/tmp',
    '/root',
]
for p in paths:
    if os.path.exists(p):
        r = subprocess.run(['find', p, '-name', '*.gguf', '-type', 'f'], capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            print(f'Found in {p}:')
            print(r.stdout)

# Also check if models dir exists
print('\\n=== Checking models directory ===')
models_dir = '/workspace/template-repos/template-1005/repo/models'
if os.path.exists(models_dir):
    print(f'{models_dir} exists, contents:')
    for f in os.listdir(models_dir):
        fp = os.path.join(models_dir, f)
        size = os.path.getsize(fp) if os.path.isfile(fp) else 'DIR'
        print(f'  {f} ({size})')
else:
    print(f'{models_dir} does NOT exist')
    # Check parent dirs
    for d in ['/workspace/template-repos/template-1005/repo', '/workspace/template-repos/template-1005', '/workspace/template-repos']:
        if os.path.exists(d):
            print(f'{d} exists: {os.listdir(d)[:20]}')
        else:
            print(f'{d} does NOT exist')

# Check disk space
print('\\n=== Disk space ===')
r = subprocess.run(['df', '-h', '/workspace'], capture_output=True, text=True)
print(r.stdout)
""", 'find1', 60)

ws.close()
print('\nDone!')
