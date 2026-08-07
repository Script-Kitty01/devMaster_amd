import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os, time

# Check stdout
try:
    with open('/tmp/gradio_stdout.txt') as f:
        out = f.read()
    print('STDOUT:', out[-3000:] if len(out) > 3000 else out)
except Exception as e:
    print('STDOUT error:', e)

# Check stderr
try:
    with open('/tmp/gradio_stderr.txt') as f:
        err = f.read()
    print('STDERR:', err[-3000:] if len(err) > 3000 else err)
except Exception as e:
    print('STDERR error:', e)

# Check port with netstat
result = subprocess.run(['netstat', '-tlnp'], capture_output=True, text=True)
for line in result.stdout.split('\\n'):
    if '7860' in line:
        print('PORT:', line.strip())

# Also try lsof
try:
    result2 = subprocess.run(['lsof', '-i', ':7860'], capture_output=True, text=True)
    print('LSOF:', result2.stdout[:1000])
except:
    pass

# Check process
result3 = subprocess.run(['ps', '-p', '37923', '-o', 'pid,stat,etime,rss'], capture_output=True, text=True)
print('PROC:', result3.stdout)
"""

msg_id = 'port'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 60
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
