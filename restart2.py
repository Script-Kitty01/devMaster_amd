import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, sys, os, time

repo = '/workspace/template-repos/template-1005/repo'
os.chdir(repo)

# Kill old
subprocess.run('pkill -9 -f gradio_app.py', shell=True)
time.sleep(2)

# Restart tunnel
subprocess.run('pkill -9 -f rc-tunnel', shell=True)
time.sleep(1)
subprocess.Popen(['/root/.local/bin/rc-tunnel', 'expose', '-port', '9999'],
    stdout=open('/tmp/rc-tunnel.log','w'), stderr=subprocess.STDOUT)
time.sleep(3)

# Start gradio
with open('/tmp/gradio9999.log', 'w') as f:
    p = subprocess.Popen(
        [sys.executable, '-u', 'src/ui/gradio_app.py'],
        stdout=f, stderr=subprocess.STDOUT,
        cwd=repo
    )
    print(f'Gradio PID: {p.pid}')

time.sleep(8)

# Verify
r = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in r.stdout.split(chr(10)):
    if 'gradio' in line.lower() and 'grep' not in line:
        print('GRADIO:', line.strip())

r = subprocess.run(['tail', '-15', '/tmp/gradio9999.log'], capture_output=True, text=True)
print('=== LOG ===')
print(r.stdout)

r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'http://localhost:9999'], capture_output=True, text=True)
print('HTTP:', r.stdout.strip())

r = subprocess.run(['/root/.local/bin/rc-tunnel', 'status'], capture_output=True, text=True)
print('TUNNEL:', r.stdout.strip())
"""

msg = json.dumps({
    'header': {'msg_id': 'x11', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

timeout = time.time() + 40
while time.time() < timeout:
    ws.settimeout(5)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'x11':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'x11':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'x11':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'x11':
            break
    except:
        break
ws.close()
