import requests, base64, os

# Read local frpc binary
local_path = r'c:\Users\Aamira\Desktop\devmaster\frpc_linux_amd64_v0.3'
with open(local_path, 'rb') as f:
    data = f.read()

print(f'Local file size: {len(data)} bytes')

# Upload via Jupyter contents API
base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

# Upload to /tmp/frpc_linux_amd64_v0.3
upload_url = f'{base_url}/api/contents/tmp/frpc_linux_amd64_v0.3'
payload = {
    'content': base64.b64encode(data).decode('ascii'),
    'name': 'frpc_linux_amd64_v0.3',
    'path': 'tmp/frpc_linux_amd64_v0.3',
    'type': 'file',
    'format': 'base64'
}

print(f'Uploading to {upload_url}...')
r = requests.put(upload_url, json=payload, headers=headers, timeout=120)
print(f'Upload status: {r.status_code}')
if r.status_code in [200, 201]:
    print('Upload successful!')
else:
    print(f'Error: {r.text[:500]}')
