import requests, json, urllib3
urllib3.disable_warnings()
base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels'
token = 'amd-oneclick'
r = requests.get(base, params={'token': token}, verify=False)
kernels = r.json()
kid = kernels[0]['id']
print(f'Kernel: {kid}')
code = "with open('/tmp/step3_output.txt') as f:\n    content = f.read()\nprint(content[-5000:])\nprint('---TOTAL LENGTH:', len(content))"
r = requests.post(f'{base}/{kid}/execute', json={'code': code}, params={'token': token}, verify=False)
print(r.text[:8000])
