"""Read terminal output via Jupyter terminal websocket."""
import requests, json
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

# Get terminal 2 (the active one)
r = requests.get(f'{base_url}/api/terminals', headers=headers)
terminals = r.json()
print("Terminals:", [t['name'] for t in terminals])

# Connect to terminal 2 websocket
term_name = '2'
ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/terminals/websocket/2'
print(f"Connecting to {ws_url}")

ws = create_connection(ws_url + '?token=amd-oneclick')

# Receive some data
import time
deadline = time.time() + 5
output = []
while time.time() < deadline:
    ws.settimeout(2)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    output.append(item)
        elif isinstance(data, str):
            output.append(data)
    except Exception as e:
        break

ws.close()
print("\n=== Terminal Output ===")
print(''.join(output[-2000:]))
