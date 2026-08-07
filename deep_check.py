import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os

# Check all log files
for f in ['/tmp/gradio9999.log', '/tmp/kutaar.log', '/var/log/kutaar.log']:
    if os.path.exists(f):
        r = subprocess.run(['wc', '-l', f], capture_output=True, text=True)
        print(f'LOG {f}: {r.stdout.strip()} lines')

# Check for any new log files
r = subprocess.run(['find', '/tmp', '-name', '*.log', '-mmin', '-30'], capture_output=True, text=True)
print('Recent logs in /tmp:')
print(r.stdout[:500])

# Check if process is stuck - look at threads
r = subprocess.run(['cat', '/proc/8348/status'], capture_output=True, text=True)
for line in r.stdout.split(chr(10)):
    if 'State' in line or 'Threads' in line:
        print(line.strip())

# Check open files of gradio process
r = subprocess.run(['ls', '-la', '/proc/8348/fd/'], capture_output=True, text=True)
print('Open FDs:')
print(r.stdout[:1000])

# Check if there's a stderr log
r = subprocess.run(['cat', '/proc/8348/fd/2'], capture_output=True, text=True)
print('STDERR (last 500 chars):')
print(r.stdout[-500:])
"""

msg = json.dumps({
    'header': {'msg_id': 'dc1', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
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
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'dc1':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'dc1':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'dc1':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'dc1':
            break
    except:
        break
ws.close()
