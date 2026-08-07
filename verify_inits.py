"""Verify __init__ signatures of ROCmLLM, RAGStore, ToolRegistry."""
import requests, json
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = '''
import inspect, sys
sys.path.insert(0, "/workspace/template-repos/template-1005/repo")

from src.llm.rocm_service import ROCmLLM
from src.rag.chroma_store import RAGStore
from src.tools.tool_registry import ToolRegistry

print("=== ROCmLLM.__init__ ===")
print(inspect.signature(ROCmLLM.__init__))
print()

print("=== RAGStore.__init__ ===")
print(inspect.signature(RAGStore.__init__))
print()

print("=== ToolRegistry.__init__ ===")
print(inspect.signature(ToolRegistry.__init__))
print()

# Also check KutaarWorkflow.invoke signature
from src.graph.workflow import KutaarWorkflow
print("=== KutaarWorkflow.__init__ ===")
print(inspect.signature(KutaarWorkflow.__init__))
'''

msg_id = 'verify-inits'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

import time
deadline = time.time() + 20
while time.time() < deadline:
    ws.settimeout(5)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        pid = data.get('parent_header', {}).get('msg_id', '')
        if pid != msg_id:
            continue
        if data.get('msg_type') == 'stream':
            print(data.get('content', {}).get('text', ''), end='', flush=True)
        elif data.get('msg_type') == 'error':
            print('\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'\n[{e}]')
        break

ws.close()
