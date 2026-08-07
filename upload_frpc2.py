import requests, json, time, base64
from websocket import create_connection

# Read local frpc binary
local_path = r'c:\Users\Aamira\Desktop\devmaster\frpc_linux_amd64_v0.3'
with open(local_path, 'rb') as f:
    data = f.read()

print(f'Local file size: {len(data)} bytes')

# Encode as base64
b64_data = base64.b64encode(data).decode('ascii')

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

# Write the base64 data in chunks to avoid message size limits
chunk_size = 50000
chunks = [b64_data[i:i+chunk_size] for i in range(0, len(b64_data), chunk_size)]
print(f'Sending {len(chunks)} chunks...')

code = f"""
import base64, os

b64_data = ''
"""

# Send chunks one by one
for i, chunk in enumerate(chunks):
    chunk_code = f"""
b64_data += '{chunk}'
print(f'Chunk {i+1}/{len(chunks)} received')
"""
    msg_id = f'fc{i}'
    msg = json.dumps({
        'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
        'parent_header': {}, 'metadata': {},
        'content': {'code': chunk_code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
        'channel': 'shell'
    })
    ws.send(msg)
    
    deadline = time.time() + 15
    while time.time() < deadline:
        ws.settimeout(5)
        try:
            resp = ws.recv()
            data_resp = json.loads(resp)
            pid = data_resp.get('parent_header', {}).get('msg_id', '')
            if pid != msg_id:
                continue
            if data_resp.get('msg_type') == 'stream':
                print(data_resp.get('content', {}).get('text', ''), end='', flush=True)
            elif data_resp.get('msg_type') == 'status' and data_resp.get('content', {}).get('execution_state') == 'idle':
                break
        except Exception as e:
            print(f'[WS chunk {i}: {e}]')
            break

# Final code to write the file
final_code = """
import base64, os

data = base64.b64decode(b64_data)
dest_dir = '/root/.cache/huggingface/gradio/frpc'
os.makedirs(dest_dir, exist_ok=True)
dest = f'{dest_dir}/frpc_linux_amd64_v0.3'
with open(dest, 'wb') as f:
    f.write(data)
os.chmod(dest, 0o755)
print(f'Written {len(data)} bytes to {dest}')
print(f'File exists: {os.path.exists(dest)}, Size: {os.path.getsize(dest)}')
"""

msg_id = 'ffinal'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': final_code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 15
while time.time() < deadline:
    ws.settimeout(5)
    try:
        resp = ws.recv()
        data_resp = json.loads(resp)
        pid = data_resp.get('parent_header', {}).get('msg_id', '')
        if pid != msg_id:
            continue
        if data_resp.get('msg_type') == 'stream':
            print(data_resp.get('content', {}).get('text', ''), end='', flush=True)
        elif data_resp.get('msg_type') == 'error':
            print('ERROR:', '\\n'.join(data_resp.get('content', {}).get('traceback', [])))
        elif data_resp.get('msg_type') == 'status' and data_resp.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS final: {e}]')
        break

ws.close()
print('\\nDone!')
