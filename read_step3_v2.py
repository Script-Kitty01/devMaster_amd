"""Read step3 output via terminal websocket."""
import requests, json
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

# Connect to terminal 2 websocket
ws_url = 'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/terminals/websocket/2?token=amd-oneclick'
print(f"Connecting...")

ws = create_connection(ws_url)

# Send cat command to read the output file
import time

# First send a newline to see current state
ws.send(json.dumps(["stdin", "\n"]))

time.sleep(1)

# Send cat command
ws.send(json.dumps(["stdin", "cat /tmp/step3_output.txt\n"]))

# Receive output
deadline = time.time() + 10
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
    except:
        break

ws.close()
print("\n=== Output ===")
print(''.join(output[-3000:]))
