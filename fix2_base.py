import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = r"""
import os
os.chdir('/workspace/template-repos/template-1005/repo')

with open('src/agents/base_agent.py', 'r') as f:
    content = f.read()

# Increase default max_tokens
content = content.replace('max_tokens: int = 1024', 'max_tokens: int = 2048')

# Replace the _parse_json_response method to add markdown fallback
old_method = '''    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Extract JSON from an LLM response (may be wrapped in markdown)."""
        # Try to find JSON block
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            text = json_match.group(1)

        # Try to find bare JSON object
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            text = json_match.group(0)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Attempt to repair truncated JSON by closing unclosed braces/brackets
            repaired = self._repair_truncated_json(text)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON from LLM response: %s", text[:200])
                return {"error": "JSON parse failed", "raw": text[:500]}'''

new_method = '''    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Extract JSON from an LLM response (may be wrapped in markdown)."""
        # Try to find JSON block
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            text = json_match.group(1)

        # Try to find bare JSON object
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            text = json_match.group(0)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Attempt to repair truncated JSON by closing unclosed braces/brackets
            repaired = self._repair_truncated_json(text)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON from LLM response: %s", text[:200])
                # Fallback: extract meaningful content from markdown
                return self._extract_from_markdown(text)

    def _extract_from_markdown(self, text: str) -> dict[str, Any]:
        """Extract structured findings from markdown when JSON parsing fails."""
        result = {"raw_text": text[:1000]}
        findings = []
        for match in re.finditer(r'[*\\-]\s*\*\*([^*]+)\*\*\s*:\s*(.+)', text):
            title = match.group(1).strip()
            desc = match.group(2).strip()
            findings.append({"title": title, "description": desc, "severity": "medium"})
        if findings:
            result["findings"] = findings
            result["verdict"] = "Analysis extracted from markdown (JSON parse failed)"
        else:
            result["verdict"] = text[:500]
        return result'''

if old_method in content:
    content = content.replace(old_method, new_method)
    print('Replaced _parse_json_response method')
else:
    print('WARNING: old_method not found!')

with open('src/agents/base_agent.py', 'w') as f:
    f.write(content)
print('FIX 2: Updated base_agent.py')
"""

msg = json.dumps({
    'header': {'msg_id': 'f2', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
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
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'f2':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'f2':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'f2':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'f2':
            break
    except:
        break
ws.close()
