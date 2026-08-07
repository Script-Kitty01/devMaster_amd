import requests, json, time, base64
from websocket import create_connection

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

# The fix script to run on the remote server
fix_script = b"""
import os, re
os.chdir('/workspace/template-repos/template-1005/repo')

# === FIX 2: base_agent.py ===
with open('src/agents/base_agent.py', 'r') as f:
    content = f.read()

# Increase default max_tokens
content = content.replace('max_tokens: int = 1024', 'max_tokens: int = 2048')

# Add _extract_from_markdown method before _repair_truncated_json
new_markdown_method = '''
    def _extract_from_markdown(self, text: str) -> dict:
        """Extract structured findings from markdown when JSON parsing fails."""
        result = {"raw_text": text[:1000]}
        findings = []
        for match in re.finditer(r"[*\\-]\\s*\\*\\*([^*]+)\\*\\*\\s*:\\s*(.+)", text):
            title = match.group(1).strip()
            desc = match.group(2).strip()
            findings.append({"title": title, "description": desc, "severity": "medium"})
        if findings:
            result["findings"] = findings
            result["verdict"] = "Analysis extracted from markdown (JSON parse failed)"
        else:
            result["verdict"] = text[:500]
        return result
'''

# Insert the new method before _repair_truncated_json
if '_extract_from_markdown' not in content:
    insert_point = content.find('    @staticmethod')
    if insert_point > 0:
        content = content[:insert_point] + new_markdown_method + '\\n' + content[insert_point:]
        print('Added _extract_from_markdown method')

# Update the fallback in _parse_json_response
old_fallback = 'return {"error": "JSON parse failed", "raw": text[:500]}'
new_fallback = 'return self._extract_from_markdown(text)'
if old_fallback in content:
    content = content.replace(old_fallback, new_fallback)
    print('Updated JSON parse fallback')

with open('src/agents/base_agent.py', 'w') as f:
    f.write(content)
print('FIX 2: Updated base_agent.py')

# === FIX 3: workflow.py - skip debate ===
with open('src/graph/workflow.py', 'r') as f:
    content = f.read()

old_debate = '''        # Run cross-review debate
        debate_rounds = self.consensus.run_debate(
            self._specialists,
            all_findings,
            max_rounds=1,
        )

        # Synthesize final verdict'''

new_debate = '''        # Skip cross-review debate to reduce latency (CPU-only mode)
        debate_rounds = []

        # Synthesize final verdict'''

if old_debate in content:
    content = content.replace(old_debate, new_debate)
    print('Skipped debate phase')
else:
    print('WARNING: debate code not found')

with open('src/graph/workflow.py', 'w') as f:
    f.write(content)
print('FIX 3: Updated workflow.py')

# === FIX 4: consensus_agent.py - increase tokens ===
with open('src/agents/consensus_agent.py', 'r') as f:
    content = f.read()

content = content.replace('max_tokens=1536', 'max_tokens=2048')

with open('src/agents/consensus_agent.py', 'w') as f:
    f.write(content)
print('FIX 4: Updated consensus_agent.py')

print('\\nAll fixes applied successfully!')
"""

encoded = base64.b64encode(fix_script).decode()

r = requests.post(f'{base_url}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = f"""
import base64, subprocess, os
script = base64.b64decode('{encoded}')
with open('/tmp/fix_all.py', 'wb') as f:
    f.write(script)
r = subprocess.run(['/opt/venv/bin/python3.12', '/tmp/fix_all.py'], capture_output=True, text=True)
print(r.stdout)
if r.stderr:
    print('STDERR:', r.stderr)
"""

msg = json.dumps({
    'header': {'msg_id': 'fa1', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
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
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'fa1':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'fa1':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'fa1'):
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'fa1':
            break
    except:
        break
ws.close()
