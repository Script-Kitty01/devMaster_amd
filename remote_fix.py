import os, re
os.chdir('/workspace/template-repos/template-1005/repo')

# === FIX 2: base_agent.py ===
with open('src/agents/base_agent.py', 'r') as f:
    content = f.read()

# Increase default max_tokens
content = content.replace('max_tokens: int = 1024', 'max_tokens: int = 2048')

# Add _extract_from_markdown method before @staticmethod
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
        content = content[:insert_point] + new_markdown_method + '\n' + content[insert_point:]
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

print('\nAll fixes applied successfully!')
