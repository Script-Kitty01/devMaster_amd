"""Install deps with full output visibility."""
import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

def run_code(code, msg_id, timeout_sec=300):
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
        ws.settimeout(30)
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
                traceback = '\n'.join(data.get('content', {}).get('traceback', []))
                print(traceback)
                output.append(traceback)
            elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
                break
        except Exception as e:
            print(f'\n[ws timeout/error: {e}]')
            break
    return ''.join(output)

# First check Python and pip
print('=== Checking environment ===')
run_code("""
import sys, subprocess
print(f'Python: {sys.version}')
print(f'Executable: {sys.executable}')
r = subprocess.run([sys.executable, '-m', 'pip', '--version'], capture_output=True, text=True)
print(f'pip: {r.stdout.strip()}')
""", 'env-check', 30)

# Install one at a time with verbose output
print('\n=== Installing chromadb ===')
run_code("""
import subprocess, sys
r = subprocess.run(
    [sys.executable, '-m', 'pip', 'install', 'chromadb', '-v'],
    capture_output=True, text=True, timeout=180
)
# Print last 100 lines of stdout
lines = r.stdout.split(chr(10))
for line in lines[-100:]:
    print(line)
if r.stderr:
    stderr_lines = r.stderr.split(chr(10))
    print('---STDERR---')
    for line in stderr_lines[-30:]:
        print(line)
print(f'\\nReturn code: {r.returncode}')
""", 'install-chromadb', 240)

print('\n=== Installing langgraph + langchain ===')
run_code("""
import subprocess, sys
for pkg in ['langgraph', 'langchain-core', 'langchain-community']:
    print(f'\\n--- Installing {pkg} ---')
    r = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', pkg],
        capture_output=True, text=True, timeout=180
    )
    lines = r.stdout.split(chr(10))
    for line in lines[-30:]:
        print(line)
    if r.returncode != 0:
        print(f'FAILED with code {r.returncode}')
        if r.stderr:
            for line in r.stderr.split(chr(10))[-20:]:
                print(line)
""", 'install-langgraph', 300)

print('\n=== Verifying ===')
run_code("""
import importlib
for mod in ['chromadb', 'langgraph', 'langchain_core', 'langchain_community']:
    try:
        m = importlib.import_module(mod)
        v = getattr(m, '__version__', '?')
        print(f'  {mod}: {v} OK')
    except Exception as e:
        print(f'  {mod}: MISSING - {e}')
""", 'verify2', 30)

ws.close()
print('\nDone!')
