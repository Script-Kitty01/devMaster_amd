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

os.chdir('/workspace/template-repos/template-1005/repo')

# Find all Python files with LLM-related classes
result = subprocess.run(['bash', '-c', 'grep -rl "class.*LLM\|ROCmLLM\|llama_cpp\|Llama(" --include="*.py" . 2>/dev/null | head -20'], capture_output=True, text=True)
print('Files with LLM classes:')
print(result.stdout)

# Check src directory structure
result = subprocess.run(['bash', '-c', 'find src -name "*.py" -type f 2>/dev/null | sort'], capture_output=True, text=True)
print('\\nSource files:')
print(result.stdout)

# Check gradio_app.py imports
with open('src/ui/gradio_app.py') as f:
    content = f.read()
print('\\n=== gradio_app.py imports (first 50 lines) ===')
for i, line in enumerate(content.split('\\n')[:50]):
    print(f'{i+1}: {line}')
"""

msg_id = 'fl'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 30
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
            print('ERROR:', '\\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
