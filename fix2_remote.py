import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

# Write the fix script to a file on the remote server, then execute it
code = """
import os
os.chdir('/workspace/template-repos/template-1005/repo')

# Write the fix script
script = '''
import re

with open("src/agents/base_agent.py", "r") as f:
    content = f.read()

# Increase default max_tokens
content = content.replace("max_tokens: int = 1024", "max_tokens: int = 2048")

# Find the _parse_json_response method and add fallback
old_end = 'logger.warning("Failed to parse JSON from LLM response: %s", text[:200])\\n                return {"error": "JSON parse failed", "raw": text[:500]}'

new_end = '''logger.warning("Failed to parse JSON from LLM response: %s", text[:200])
                # Fallback: extract meaningful content from markdown
                return self._extract_from_markdown(text)

    def _extract_from_markdown(self, text: str) -> dict:
        """Extract structured findings from markdown when JSON parsing fails."""
        result = {"raw_text": text[:1000]}
        findings = []
        for match in re.finditer(r"[*\\\\-]\\\\s*\\\\*\\\\*([^*]+)\\\\*\\\\*\\\\s*:\\\\s*(.+)", text):
            title = match.group(1).strip()
            desc = match.group(2).strip()
            findings.append({"title": title, "description": desc, "severity": "medium"})
        if findings:
            result["findings"] = findings
            result["verdict"] = "Analysis extracted from markdown (JSON parse failed)"
        else:
            result["verdict"] = text[:500]
        return result'''

if old_end in content:
    content = content.replace(old_end, new_end)
    print("Replaced parse_json fallback")
else:
    print("WARNING: old_end not found in base_agent.py")

with open("src/agents/base_agent.py", "w") as f:
    f.write(content)
print("FIX 2: Updated base_agent.py")
'''

with open('/tmp/fix2.py', 'w') as f:
    f.write(script)

import subprocess
r = subprocess.run(['/opt/venv/bin/python3.12', '/tmp/fix2.py'], capture_output=True, text=True)
print(r.stdout)
if r.stderr:
    print('STDERR:', r.stderr)
"""

msg = json.dumps({
    'header': {'msg_id': 'f2r', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {}, 'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True},
    'channel': 'shell'
})
ws.send(msg)

timeout = time.time() + 15
while time.time() < timeout:
    ws.settimeout(3)
    try:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'f2r':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'f2r':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'f2r':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'f2r':
            break
    except:
        break
ws.close()
