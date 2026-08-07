"""
Search for HIPBLAS in vendored llama.cpp, and try downloading full llama.cpp from gitee mirror.
"""
import requests, json, time, uuid, urllib3
from websocket import create_connection
urllib3.disable_warnings()

BASE = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
TOKEN = 'amd-oneclick'

r = requests.post(f'{BASE}/api/kernels', headers={'Authorization': f'token {TOKEN}'}, verify=False)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws_url = f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token={TOKEN}'
ws = create_connection(ws_url, timeout=900)
msg = json.loads(ws.recv())

code = """
import subprocess, sys, os

LLAMA_DIR = '/tmp/llama_cpp_python_src/vendor/llama.cpp'

# Search broadly for HIPBLAS
print("=== Searching for HIPBLAS in vendored llama.cpp ===")
result = subprocess.run(
    f'grep -rn "GGML_HIPBLAS\\|HIPBLAS\\|hipblas" {LLAMA_DIR} --include="*.cmake" --include="*.txt" --include="CMakeLists.txt" 2>/dev/null | head -30',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("HIPBLAS references:", result.stdout if result.stdout.strip() else "*** NONE FOUND ***")

# Search for GGML_ options
result = subprocess.run(
    f'grep -rn "option(GGML_" {LLAMA_DIR} --include="*.cmake" --include="*.txt" --include="CMakeLists.txt" 2>/dev/null | head -30',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("\\nGGML_ options:", result.stdout[:2000] if result.stdout.strip() else "NONE")

# Check what backends are available
result = subprocess.run(
    f'grep -rn "GGML_CUDA\\|GGML_METAL\\|GGML_VULKAN\\|GGML_SYCL\\|GGML_HIP" {LLAMA_DIR} --include="*.cmake" --include="*.txt" --include="CMakeLists.txt" 2>/dev/null | head -20',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("\\nBackend options:", result.stdout[:2000] if result.stdout.strip() else "NONE")

# Check the ggml CMakeLists.txt
result = subprocess.run(
    f'cat {LLAMA_DIR}/ggml/CMakeLists.txt 2>/dev/null | head -100',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("\\nggml/CMakeLists.txt (first 100 lines):")
print(result.stdout[:2000])

# Check ggml/src directory
result = subprocess.run(
    f'ls {LLAMA_DIR}/ggml/src/ 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("\\nggml/src/ contents:", result.stdout)

# Try downloading full llama.cpp from gitee mirror
print("\\n=== Trying gitee mirror ===")
result = subprocess.run(
    'curl -skL --connect-timeout 10 --max-time 30 '
    '-o /tmp/llama_gitee.tar.gz '
    'https://gitee.com/mirrors/llama.cpp/repository/archive/master.tar.gz '
    '2>&1 && echo "DOWNLOAD OK" || echo "DOWNLOAD FAILED"',
    shell=True, capture_output=True, text=True, timeout=60, executable='/bin/bash'
)
print(result.stdout.strip())

# Also try jsDelivr CDN (GitHub mirror)
if 'FAILED' in result.stdout:
    print("\\n=== Trying jsDelivr CDN ===")
    result = subprocess.run(
        'curl -skL --connect-timeout 10 --max-time 30 '
        '-o /tmp/llama_jsdelivr.tar.gz '
        'https://cdn.jsdelivr.net/gh/ggerganov/llama.cpp@master.tar.gz '
        '2>&1 && echo "DOWNLOAD OK" || echo "DOWNLOAD FAILED"',
        shell=True, capture_output=True, text=True, timeout=60, executable='/bin/bash'
    )
    print(result.stdout.strip())

# Try fastgit mirror
if 'FAILED' in result.stdout:
    print("\\n=== Trying fastgit mirror ===")
    result = subprocess.run(
        'curl -skL --connect-timeout 10 --max-time 30 '
        '-o /tmp/llama_fastgit.tar.gz '
        'https://hub.fastgit.xyz/ggerganov/llama.cpp/archive/refs/heads/master.tar.gz '
        '2>&1 && echo "DOWNLOAD OK" || echo "DOWNLOAD FAILED"',
        shell=True, capture_output=True, text=True, timeout=60, executable='/bin/bash'
    )
    print(result.stdout.strip())

# Check if any download succeeded
result = subprocess.run(
    'ls -la /tmp/llama_*.tar.gz 2>/dev/null',
    shell=True, capture_output=True, text=True, executable='/bin/bash'
)
print("\\nDownloaded files:", result.stdout if result.stdout.strip() else "NONE")

print("\\n=== DONE ===")
"""

ws.send(json.dumps({
    'header': {'msg_id': str(uuid.uuid4()), 'username': 'test', 'session': kid, 'msg_type': 'execute_request', 'version': '5.3'},
    'parent_header': {},
    'metadata': {},
    'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False},
    'channel': 'shell'
}))

print("Searching for HIPBLAS and trying mirrors...")
time.sleep(10)
while True:
    try:
        ws.settimeout(10)
        msg = json.loads(ws.recv())
        if msg.get('msg_type') == 'stream' and msg.get('content', {}).get('name') == 'stdout':
            print(msg['content']['text'], end='')
        if msg.get('msg_type') == 'error':
            print(f'ERROR: {msg}')
    except Exception as e:
        if 'timed out' in str(e).lower():
            continue
        break

ws.close()
requests.delete(f'{BASE}/api/kernels/{kid}', headers={'Authorization': f'token {TOKEN}'}, verify=False)
print('\n\n=== ALL DONE ===')
