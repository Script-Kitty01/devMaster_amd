# -*- coding: utf-8 -*-
import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import os

os.chdir('/workspace/template-repos/template-1005/repo')

with open('src/ui/gradio_app.py') as f:
    content = f.read()

# Find the exact line with "from __future__ import annotations"
lines = content.split('\n')
target_idx = None
for i, line in enumerate(lines):
    if line.strip() == 'from __future__ import annotations':
        target_idx = i
        break

if target_idx is not None:
    # Insert sys.path fix after the __future__ import
    insert_lines = [
        '',
        'import sys',
        'from pathlib import Path',
        '',
        '# Ensure repo root is on sys.path so src module is importable',
        '_REPO_ROOT = Path(__file__).resolve().parent.parent.parent',
        'if str(_REPO_ROOT) not in sys.path:',
        '    sys.path.insert(0, str(_REPO_ROOT))',
    ]
    for j, ins in enumerate(insert_lines):
        lines.insert(target_idx + 1 + j, ins)
    
    new_content = '\n'.join(lines)
    with open('src/ui/gradio_app.py', 'w') as f:
        f.write(new_content)
    print('sys.path fix applied!')
    
    # Verify
    with open('src/ui/gradio_app.py') as f:
        verify = f.read()
    for i, line in enumerate(verify.split('\n')[:20]):
        print(f'{i+1}: {line}')
else:
    print('Could not find __future__ import line')
"""

msg_id = 'aspf2'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 15
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
            print('ERROR:', '\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
