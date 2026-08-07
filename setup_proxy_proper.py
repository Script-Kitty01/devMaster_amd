import requests, json, time
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import subprocess, os, json

# Create proper jupyter config with proxy settings
config_py = '''
c.ServerApp.allow_origin = '*'
c.ServerApp.disable_check_xsrf = True
c.ServerApp.allow_remote_access = True

# jupyter-server-proxy config
c.ServerProxy.servers = {
    'gradio': {
        'command': ['/opt/venv/bin/python', '-u', '/workspace/template-repos/template-1005/repo/src/ui/gradio_app.py'],
        'port': 7860,
        'timeout': 120,
        'launcher_entry': {
            'title': 'Kutaar Gradio',
            'icon_path': '/opt/venv/share/jupyter/labextensions/@jupyter-server/server-proxy/style/icons/python.svg'
        }
    }
}
'''

os.makedirs('/root/.jupyter', exist_ok=True)
with open('/root/.jupyter/jupyter_server_config.py', 'w') as f:
    f.write(config_py)
print('Created jupyter_server_config.py')

# Also create JSON config
config_json = {
    "ServerApp": {
        "allow_origin": "*",
        "disable_check_xsrf": True,
        "allow_remote_access": True,
        "jpserver_extensions": {
            "jupyter_server_proxy": True
        }
    }
}
with open('/root/.jupyter/jupyter_server_config.json', 'w') as f:
    json.dump(config_json, f, indent=2)
print('Created jupyter_server_config.json')

# Kill JupyterLab
result = subprocess.run(['pgrep', '-f', 'jupyter-lab'], capture_output=True, text=True)
jpid = result.stdout.strip()
print(f'Killing JupyterLab PID {jpid}')
subprocess.run(['kill', '-9', jpid], capture_output=True)

import time
time.sleep(3)

# Start JupyterLab with proxy
print('Starting JupyterLab...')
subprocess.Popen(
    ['/opt/venv/bin/jupyter-lab', '--ip=0.0.0.0', '--port=8888', '--no-browser', '--allow-root', 
     '--ServerApp.token=amd-oneclick', 
     '--ServerApp.base_url=/instances/u-14073-bcd85560/',
     '--ServerApp.allow_origin=*',
     '--ServerApp.disable_check_xsrf=True'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    cwd='/workspace/template-repos/template-1005/repo'
)

time.sleep(8)

# Verify
result = subprocess.run(['pgrep', '-f', 'jupyter-lab'], capture_output=True, text=True)
print(f'JupyterLab PID: {result.stdout.strip()}')

result = subprocess.run(['bash', '-c', 'ss -tlnp | grep 8888'], capture_output=True, text=True)
print(f'Port 8888: {result.stdout.strip()}')
"""

msg_id = 'spp'
msg = json.dumps({
    'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
    'channel': 'shell'
})
ws.send(msg)

deadline = time.time() + 45
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
            print('ERROR:', '\\n'.join(data.get('content', {}).get('traceback', [])))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
            break
    except Exception as e:
        print(f'[WS: {e}]')
        break

ws.close()
