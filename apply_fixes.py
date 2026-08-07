import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

code = """
import os
os.chdir('/workspace/template-repos/template-1005/repo')

# ============================================================
# FIX 1: Increase max_tokens in rocm_service.py (256 -> 512)
# ============================================================
with open('src/llm/rocm_service.py', 'r') as f:
    content = f.read()

# Fix default max_tokens
content = content.replace('max_tokens: int = 256', 'max_tokens: int = 512')
# Also fix the generate method's default
content = content.replace('max_tokens=256', 'max_tokens=512')

with open('src/llm/rocm_service.py', 'w') as f:
    f.write(content)
print('FIX 1: Increased max_tokens to 512 in rocm_service.py')

# ============================================================
# FIX 2: Increase default max_tokens in base_agent _call_llm
# ============================================================
with open('src/agents/base_agent.py', 'r') as f:
    content = f.read()

# Increase default max_tokens from 1024 to 2048
content = content.replace(
    'def _call_llm(self, prompt: str, *, max_tokens: int = 1024) -> str:',
    'def _call_llm(self, prompt: str, *, max_tokens: int = 2048) -> str:'
)

# Improve _parse_json_response to handle markdown output
old_parse = '''    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Extract JSON from an LLM response (may be wrapped in markdown)."""
        # Try to find JSON block
        json_match = re.search(r"```(?:json)?\\s*([\\s\\S]*?)```", text)
        if json_match:
            text = json_match.group(1)

        # Try to find bare JSON object
        json_match = re.search(r"\\{[\\s\\S]*\\}", text)
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

new_parse = '''    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Extract JSON from an LLM response (may be wrapped in markdown)."""
        # Try to find JSON block
        json_match = re.search(r"```(?:json)?\\s*([\\s\\S]*?)```", text)
        if json_match:
            text = json_match.group(1)

        # Try to find bare JSON object
        json_match = re.search(r"\\{[\\s\\S]*\\}", text)
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
        # Try to find bullet points with key findings
        import re as _re
        for match in _re.finditer(r'[*\\-]\\s*\\*\\*([^*]+)\\*\\*\\s*:\\s*(.+)', text):
            title = match.group(1).strip()
            desc = match.group(2).strip()
            findings.append({"title": title, "description": desc, "severity": "medium"})
        if findings:
            result["findings"] = findings
            result["verdict"] = "Analysis extracted from markdown (JSON parse failed)"
        else:
            result["verdict"] = text[:500]
        return result'''

content = content.replace(old_parse, new_parse)

with open('src/agents/base_agent.py', 'w') as f:
    f.write(content)
print('FIX 2: Increased max_tokens and improved JSON parsing in base_agent.py')

# ============================================================
# FIX 3: Skip debate phase in workflow.py (set max_rounds=0)
# ============================================================
with open('src/graph/workflow.py', 'r') as f:
    content = f.read()

# Skip debate by not calling run_debate
old_consensus = '''        # Run cross-review debate
        debate_rounds = self.consensus.run_debate(
            self._specialists,
            all_findings,
            max_rounds=1,
        )

        # Synthesize final verdict
        consensus = self.consensus.synthesize(all_findings, user_query)'''

new_consensus = '''        # Skip cross-review debate to reduce latency (CPU-only mode)
        debate_rounds = []

        # Synthesize final verdict
        consensus = self.consensus.synthesize(all_findings, user_query)'''

content = content.replace(old_consensus, new_consensus)

with open('src/graph/workflow.py', 'w') as f:
    f.write(content)
print('FIX 3: Skipped debate phase in workflow.py')

# ============================================================
# FIX 4: Increase consensus synthesize max_tokens
# ============================================================
with open('src/agents/consensus_agent.py', 'r') as f:
    content = f.read()

content = content.replace(
    'response = self._call_llm(prompt, max_tokens=1536)',
    'response = self._call_llm(prompt, max_tokens=2048)'
)

with open('src/agents/consensus_agent.py', 'w') as f:
    f.write(content)
print('FIX 4: Increased consensus max_tokens to 2048')

print('\\nAll fixes applied!')
"""

msg = json.dumps({
    'header': {'msg_id': 'af1', 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
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
        if data.get('msg_type') == 'stream' and data.get('parent_header', {}).get('msg_id') == 'af1':
            print(data.get('content', {}).get('text', ''), end='')
        elif data.get('msg_type') == 'execute_result' and data.get('parent_header', {}).get('msg_id') == 'af1':
            print(data.get('content', {}).get('data', {}).get('text/plain', ''))
        elif data.get('msg_type') == 'error' and data.get('parent_header', {}).get('msg_id') == 'af1':
            print('ERROR:', data.get('content', {}).get('ename', ''), data.get('content', {}).get('evalue', ''))
        elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle' and data.get('parent_header', {}).get('msg_id') == 'af1':
            break
    except:
        break
ws.close()
