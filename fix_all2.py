import requests, json, time, base64
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

# Read the fix script from a local file
with open(r'c:\Users\Aamira\Desktop\devmaster\remote_fix.py', 'rb') as f:
    fix_script = f.read()

encoded = base64.b64encode(fix_script).decode()

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = f"""
import base64, subprocess
script = base64.b64decode('{encoded}')
with open('/tmp/fix_all.py', 'wb') as f:
    f.write(script)
r = subprocess.run(['/opt/venv/bin/python3.12', '/tmp/fix_all.py'], capture_output=True, text=True)
print(r.stdout)
if r.stderr:
    print('STDERR:', r.stderr)
"""

msg = json.dumps({
    'header': {'msg_id': 'fa2', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

timeout = time.time() + 20
while time.time() < timeout:
    ws.settimeout(3)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'fa2':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'fa2':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'fa2':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'fa2':
            break
    except:
        break
ws.close()
