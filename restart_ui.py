import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import subprocess, os, time, signal

# Kill old Gradio process
print('Killing old Gradio (PID 286)...')
try:
    os.kill(286, signal.SIGTERM)
    time.sleep(2)
    print('Old process killed.')
except ProcessLookupError:
    print('Process already gone.')

# Kill frpc too
r = subprocess.run(['pkill', '-f', 'frpc_linux_amd64'], capture_output=True, text=True)
print('frpc killed.')

# Start new Gradio
os.chdir('/workspace/template-repos/template-1005/repo')
print('\nStarting Gradio with share=True...')

proc = subprocess.Popen(
    ['/opt/venv/bin/python', '-u', '-c', '''
import sys
sys.path.insert(0, "/workspace/template-repos/template-1005/repo")
from src.ui.gradio_app import create_ui
ui = create_ui()
ui.launch(server_name="0.0.0.0", server_port=7860, share=True)
'''],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

# Wait for public URL
deadline = time.time() + 60
output = ''
while time.time() < deadline:
    line = proc.stdout.readline()
    if line:
        output += line
        print(line, end='')
        if 'gradio.live' in line or 'Running on public URL' in line:
            break
    else:
        time.sleep(0.5)

print('\nDone! Gradio restarted.')
"""

msg_id = 'rui'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 90
while time.time() < deadline:
    ws.settimeout(20)
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
