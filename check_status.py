import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

# Write a script to the server
script = '''
import subprocess, sys
print('=== Gradio Status ===')
r = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in r.stdout.split(chr(10)):
    if 'gradio' in line.lower() and 'grep' not in line:
        print(line)
print('=== HTTP Check ===')
r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'http://localhost:9999'], capture_output=True, text=True)
print('HTTP:', r.stdout.strip())
print('=== Tunnel Status ===')
r = subprocess.run(['/root/.local/bin/rc-tunnel', 'status'], capture_output=True, text=True)
print('TUNNEL stdout:', r.stdout.strip())
print('TUNNEL stderr:', r.stderr.strip())
print('=== Starting Tunnel ===')
r = subprocess.run(['nohup', '/root/.local/bin/rc-tunnel', 'expose', '-port', '9999'], capture_output=True, text=True)
print('START stdout:', r.stdout.strip())
print('START stderr:', r.stderr.strip())
print('DONE')
'''

# Write to file
r = requests.put(f'{base}/api/contents/check_status.py', json={'content': script, 'type': 'file', 'format': 'text'}, headers=headers)
print('Write:', r.status_code)

# Create kernel
r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print('Kernel:', kid)

# Execute via kernel
ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code_to_run = "exec(open('/workspace/template-repos/template-1005/repo/check_status.py').read())"

msg = json.dumps({
    'header': {'msg_id': 'x1', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code_to_run, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

# Receive responses
timeout = time.time() + 30
while time.time() < timeout:
    ws.settimeout(5)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'x1':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'x1':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'x1':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'x1':
            break
    except:
        break

ws.close()
print('---DONE---')
