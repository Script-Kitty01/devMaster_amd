import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print('Kernel:', kid)

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os

# Check the gradio_app.py to understand the pipeline
r = subprocess.run(['wc', '-l', '/workspace/template-repos/template-1005/repo/src/ui/gradio_app.py'], capture_output=True, text=True)
print('Lines:', r.stdout.strip())

# Check what happens on chat
r = subprocess.run(['grep', '-n', 'def.*chat|def.*respond|def.*predict|def.*generate|def.*submit|def.*send|n_ctx|n_predict|max_tokens', '/workspace/template-repos/template-1005/repo/src/ui/gradio_app.py'], capture_output=True, text=True)
print('=== Chat functions ===')
print(r.stdout[:2000])

# Check rocm_service.py for context length
r = subprocess.run(['grep', '-n', 'n_ctx|n_predict|max_tokens|context|generate|create_completion', '/workspace/template-repos/template-1005/repo/src/llm/rocm_service.py'], capture_output=True, text=True)
print('=== LLM service ===')
print(r.stdout[:2000])

# Check if there's a multi-agent pipeline
r = subprocess.run(['find', '/workspace/template-repos/template-1005/repo/src', '-name', '*.py', '-exec', 'grep', '-l', 'agent|Agent|pipeline|workflow', '{}', ';'], capture_output=True, text=True)
print('=== Agent files ===')
print(r.stdout[:1000])
"""

msg = json.dumps({
    'header': {'msg_id': 'x4', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

timeout = time.time() + 20
while time.time() < timeout:
    ws.settimeout(5)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'x4':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'x4':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'x4':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'x4':
            break
    except:
        break

ws.close()
print('---DONE---')
