import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os, signal

# 1. Kill Gradio
r = subprocess.run(['pgrep', '-f', 'gradio_app.py'], capture_output=True, text=True)
for pid in r.stdout.strip().split():
    os.kill(int(pid), signal.SIGKILL)
    print(f'Killed Gradio PID {pid}')

# 2. Kill rc-tunnel (FRPC)
r = subprocess.run(['pgrep', '-f', 'rc-tunnel'], capture_output=True, text=True)
for pid in r.stdout.strip().split():
    os.kill(int(pid), signal.SIGKILL)
    print(f'Killed rc-tunnel PID {pid}')

# 3. Kill any remaining frpc processes
r = subprocess.run(['pgrep', '-f', 'frpc'], capture_output=True, text=True)
for pid in r.stdout.strip().split():
    os.kill(int(pid), signal.SIGKILL)
    print(f'Killed frpc PID {pid}')

# 4. Kill llama.cpp if running
r = subprocess.run(['pgrep', '-f', 'llama'], capture_output=True, text=True)
for pid in r.stdout.strip().split():
    os.kill(int(pid), signal.SIGKILL)
    print(f'Killed llama PID {pid}')

time.sleep(2)

# Verify everything is dead
print('\\n=== Remaining processes ===')
r = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in r.stdout.split(chr(10)):
    if any(x in line.lower() for x in ['gradio', 'frpc', 'rc-tunnel', 'llama']) and 'grep' not in line:
        print('STILL RUNNING:', line.strip())

print('\\n=== Port check ===')
r = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True)
for line in r.stdout.split(chr(10)):
    if ':9999' in line or ':7000' in line:
        print(line.strip())

print('\\n✅ Shutdown complete. No more credit usage from Kutaar.')
"""

msg = json.dumps({
    'header': {'msg_id': 'sd1', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
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
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'sd1':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'sd1':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'sd1':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'sd1':
            break
    except:
        break
ws.close()
