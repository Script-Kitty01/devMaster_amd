import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print('Kernel:', kid)

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess, os

repo = '/workspace/template-repos/template-1005/repo'

# 1. Optimize rocm_service.py - smaller context, more threads, fewer tokens
rocm_path = f'{repo}/src/llm/rocm_service.py'
with open(rocm_path, 'r') as f:
    content = f.read()

# Replace config defaults for CPU speed
replacements = [
    ('n_ctx: int = 4096', 'n_ctx: int = 2048'),
    ('n_batch: int = 4', 'n_batch: int = 1'),
    ('max_tokens: int = 1024', 'max_tokens: int = 256'),
    ('n_threads=4,', 'n_threads=8,'),
]

for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        print(f'Replaced: {old} -> {new}')
    else:
        print(f'NOT FOUND: {old}')

with open(rocm_path, 'w') as f:
    f.write(content)
print('rocm_service.py updated')

# 2. Optimize gradio_app.py - add fast path for simple queries
gradio_path = f'{repo}/src/ui/gradio_app.py'
with open(gradio_path, 'r') as f:
    content = f.read()

# Add a fast path check before the workflow
old_chat = '''    try:
        from langchain_core.messages import HumanMessage
        from src.graph.workflow import KutaarWorkflow

        _init_components(repo_path)

        if _workflow is None:
            wf = KutaarWorkflow(_llm, _rag_store, _tool_registry)
            _workflow = wf.compile()

        config = {"configurable": {"thread_id": _thread_id}}
        result = _workflow.invoke('''

new_chat = '''    try:
        from langchain_core.messages import HumanMessage
        from src.graph.workflow import KutaarWorkflow

        _init_components(repo_path)

        # Fast path: simple queries bypass the multi-agent pipeline
        simple_keywords = ['hello', 'hi', 'hey', 'what can you do', 'who are you', 'help', 'thanks', 'thank you']
        is_simple = any(kw in message.lower() for kw in simple_keywords)

        if is_simple and not _repo_indexed:
            # Direct LLM response for simple queries
            result = _llm.generate(
                message,
                system_prompt="You are Kutaar, a multi-agent AI engineering assistant powered by AMD ROCm. You help analyze code for security, performance, architecture, and DevOps. Keep responses brief and helpful.",
                max_tokens=128,
            )
            response_text = result.text
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": response_text})
            return "", history

        if _workflow is None:
            wf = KutaarWorkflow(_llm, _rag_store, _tool_registry)
            _workflow = wf.compile()

        config = {"configurable": {"thread_id": _thread_id}}
        result = _workflow.invoke('''

if old_chat in content:
    content = content.replace(old_chat, new_chat)
    print('gradio_app.py: Added fast path')
else:
    print('WARNING: Could not find chat block in gradio_app.py')

with open(gradio_path, 'w') as f:
    f.write(content)
print('gradio_app.py updated')

# 3. Optimize workflow.py - reduce debate rounds from 2 to 1
workflow_path = f'{repo}/src/graph/workflow.py'
with open(workflow_path, 'r') as f:
    content = f.read()

if 'max_rounds=2' in content:
    content = content.replace('max_rounds=2', 'max_rounds=1')
    print('workflow.py: Reduced debate rounds 2->1')
else:
    print('WARNING: max_rounds=2 not found in workflow.py')

with open(workflow_path, 'w') as f:
    f.write(content)
print('workflow.py updated')

print('=== ALL OPTIMIZATIONS APPLIED ===')
"""

msg = json.dumps({
    'header': {'msg_id': 'x7', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
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
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'x7':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'x7':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'x7':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
            trace = data.get('content', {}).get('traceback', [])
            for t in trace[:5]:
                print('  ', t)
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'x7':
            break
    except:
        break

ws.close()
print('---DONE---')
