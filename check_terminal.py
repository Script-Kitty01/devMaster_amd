"""Check terminal output via Jupyter API."""
import requests

base_url = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

# List terminals
r = requests.get(f'{base_url}/api/terminals', headers=headers)
print("Terminals:", r.json())

# List kernels
r = requests.get(f'{base_url}/api/kernels', headers=headers)
kernels = r.json()
print(f"\n{len(kernels)} kernels running")
