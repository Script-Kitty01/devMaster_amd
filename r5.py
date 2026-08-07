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

subprocess.run('pkill -9 -f gradio_app.py', shell=True)
time.sleep(2)

with open('/tmp/gradio9999.log', 'w') as f:
    p = subprocess.Popen(
        [sys.executable, '-u', 'src/ui/gradio_app.py'],
        stdout=f, stderr=subprocess.STDOUT,
        cwd=repo
    )
    print(f'Gradio PID: {p.pid}')

time.sleep(10)

r = subprocess.run(['tail', '-5', '/tmp/gradio9999.log'], capture_output=True, text=True)
print('LOG:', r.stdout.strip())

r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'http://localhost:9999'], capture_output=True, text=True)
print('HTTP:', r.stdout.strip())

r = subprocess.run(['/root/.local/bin/rc-tunnel', 'status'], capture_output=True, text=True)
print('TUNNEL:', r.stdout.strip())
"""

msg = json.dumps({
    'header': {'msg_id': 'r5', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

timeout = time.time() + 30
while time.time() < timeout:
    ws.settimeout(5)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'r5':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'r5':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'r5':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'r5':
            break
    except:
        break
ws.close()
