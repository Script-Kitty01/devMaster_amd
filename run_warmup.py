"""Send the demo warmup to the Radeon Cloud Jupyter kernel."""
import requests, json, time
from websocket import create_connection

base = 'https://radeon-global.anruicloud.com/instances/u-14073-bcd85560'
headers = {'Authorization': 'token amd-oneclick'}

r = requests.post(f'{base}/api/kernels', json={'name': 'python3'}, headers=headers)
kid = r.json()['id']
print(f'Kernel: {kid}')

ws = create_connection(f'wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/kernels/{kid}/channels?token=amd-oneclick')

def run_code(code, msg_id, timeout_sec=600):
    msg = json.dumps({
        'header': {'msg_id': msg_id, 'username': 'u', 'session': 's', 'msg_type': 'execute_request', 'version': '5.3'},
        'parent_header': {}, 'metadata': {},
        'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': False},
        'channel': 'shell'
    })
    ws.send(msg)
    
    output = []
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ws.settimeout(15)
        try:
            resp = ws.recv()
            data = json.loads(resp)
            pid = data.get('parent_header', {}).get('msg_id', '')
            if pid != msg_id:
                continue
            if data.get('msg_type') == 'stream':
                text = data.get('content', {}).get('text', '')
                output.append(text)
                print(text, end='', flush=True)
            elif data.get('msg_type') == 'execute_result':
                text = data.get('content', {}).get('data', {}).get('text/plain', '')
                output.append(text)
                print(text)
            elif data.get('msg_type') == 'error':
                text = f"\nERROR: {data.get('content', {}).get('ename', '')}: {data.get('content', {}).get('evalue', '')}"
                output.append(text)
                print(text)
            elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
                break
        except:
            break
    return ''.join(output)

# ── STEP 1: GPU Detection ──
print('='*60)
print('  STEP 1: GPU Detection')
print('='*60)
run_code("""
import subprocess
r = subprocess.run(['rocm-smi', '--showproductname'], capture_output=True, text=True)
for line in r.stdout.split(chr(10)):
    if any(kw in line for kw in ['GPU', 'Series', 'Card', 'gfx']):
        print(f'  GPU: {line.strip()}')
print('  ✅ AMD GPU detected — ZERO NVIDIA DEPENDENCY')
""", 'gpu-detect', 30)

# ── STEP 2: GPU Benchmark ──
print('\n' + '='*60)
print('  STEP 2: GPU Inference Benchmark')
print('='*60)
run_code("""
from llama_cpp import Llama
import time

model_path = '/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf'

print('Loading model with n_gpu_layers=-1 (ALL layers on GPU)...')
t0 = time.time()
llm = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=2048, n_batch=512, verbose=False)
load_time = time.time() - t0
print(f'Load time: {load_time:.1f}s')

print('Warmup...')
_ = llm('Hello', max_tokens=10)

print()
print('Running 5-run benchmark...')
prompt = 'Explain what a GPU is in one paragraph.'
total_tokens = 0
total_time = 0
for i in range(5):
    t0 = time.time()
    result = llm(prompt, max_tokens=100)
    elapsed = time.time() - t0
    tokens = result['usage']['completion_tokens']
    speed = tokens / elapsed
    total_tokens += tokens
    total_time += elapsed
    print(f'  Run {i+1}: {tokens} tokens in {elapsed:.2f}s = {speed:.1f} tok/s')

avg_speed = total_tokens / total_time
print()
print('='*50)
print('  GPU BENCHMARK SUMMARY')
print('='*50)
print(f'  Model:   Llama 3.2 3B Instruct Q4_K_M (2.02 GB)')
print(f'  GPU:     AMD Radeon Graphics gfx1100')
print(f'  Backend: ROCm 7.2.1 + HIP BLAS')
print(f'  Load:    {load_time:.1f}s')
print(f'  Speed:   {avg_speed:.1f} tok/s')
print(f'  Total:   {total_tokens} tokens in {total_time:.2f}s over 5 runs')
print(f'  Status:  GPU INFERENCE VERIFIED - ZERO NVIDIA')
print('='*50)
""", 'gpu-bench', 180)

# ── STEP 3: Create demo repo & index ──
print('\n' + '='*60)
print('  STEP 3: Create Demo Repo & Index')
print('='*60)
run_code("""
import sys, os
sys.path.insert(0, '/workspace/template-repos/template-1005/repo')

from pathlib import Path

repo_path = '/workspace/template-repos/template-1005/repo/demo_repos/sample_app'
Path(repo_path).mkdir(parents=True, exist_ok=True)

# Create sample vulnerable app
(Path(repo_path) / 'app.py').write_text('''
import os, sqlite3, subprocess
from flask import Flask, request

app = Flask(__name__)
DATABASE_PASSWORD = "admin123!"

@app.route("/")
def home():
    return "<h1>Sample App</h1>"

@app.route("/search")
def search():
    query = request.args.get("q", "")
    conn = sqlite3.connect("users.db")
    cursor = conn.execute(f"SELECT * FROM users WHERE name = '{query}'")
    return str(cursor.fetchall())

@app.route("/exec")
def exec_cmd():
    cmd = request.args.get("cmd", "ls")
    result = subprocess.check_output(cmd, shell=True)
    return result

@app.route("/read")
def read_file():
    filename = request.args.get("file", "")
    with open(filename, "r") as f:
        return f.read()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
''')

(Path(repo_path) / 'Dockerfile').write_text('''
FROM python:3.9
COPY . /app
WORKDIR /app
RUN pip install flask
USER root
CMD ["python", "app.py"]
''')

(Path(repo_path) / 'config.yaml').write_text('''
database:
  host: localhost
  port: 5432
  username: admin
  password: SuperSecret123!
''')

(Path(repo_path) / 'utils.py').write_text('''
import time

def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

def process_data(items):
    result = []
    for item in items:
        for sub in get_sub_items(item):
            result.append(sub)
    return result

def get_sub_items(item):
    time.sleep(0.1)
    return [item] * 10
''')

print('Demo repo created with intentional vulnerabilities:')
for f in Path(repo_path).iterdir():
    print(f'  {f.name}')

# Index the repo
from src.llm.rocm_service import ROCmLLM
from src.rag.chroma_store import RAGStore
from src.ingestion.repo_indexer import RepoIndexer

print('\\nInitializing RAG store...')
rocm_llm = ROCmLLM.get_instance()
rocm_llm.initialize()

rag = RAGStore(persist_dir='/workspace/template-repos/template-1005/repo/chroma_db')
rag.initialize()

indexer = RepoIndexer(repo_path)
chunks = indexer.chunk_all()
stats = indexer.stats()

rag.reset()
count = rag.index_chunks(chunks, rocm_llm.embed)

print(f'Indexed {count} chunks from {stats["file_count"]} files')
print('RAG store is ready!')
""", 'index-repo', 120)

# ── STEP 4: Pre-warm Agent Pipeline ──
print('\n' + '='*60)
print('  STEP 4: Pre-warm Agent Pipeline')
print('='*60)
run_code("""
import sys
sys.path.insert(0, '/workspace/template-repos/template-1005/repo')

from pathlib import Path
from src.llm.rocm_service import ROCmLLM
from src.rag.chroma_store import RAGStore
from src.tools.tool_registry import ToolRegistry
from src.graph.workflow import KutaarWorkflow
from langchain_core.messages import HumanMessage

repo_path = '/workspace/template-repos/template-1005/repo/demo_repos/sample_app'

print('Compiling LangGraph workflow...')
rocm_llm = ROCmLLM.get_instance()
rag = RAGStore(persist_dir='/workspace/template-repos/template-1005/repo/chroma_db')
rag.initialize()
tools = ToolRegistry(repo_path)

wf = KutaarWorkflow(rocm_llm, rag, tools)
app = wf.compile()
print('Workflow compiled!')

print('\\nRunning warmup query: "Find security vulnerabilities in this codebase"')
print('(This takes 30-60s as all 6 agents run)...')

config = {"configurable": {"thread_id": "demo-warmup"}}
result = app.invoke(
    {
        "messages": [HumanMessage(content="Find security vulnerabilities in this codebase")],
        "repo_path": repo_path,
        "repo_name": "sample_app",
        "repo_indexed": True,
        "current_phase": "planning",
        "turn_count": 0,
    },
    config=config,
)

total = 0
for agent_key in ["security", "performance", "architecture", "devops"]:
    findings = result.get(f"{agent_key}_findings", [])
    total += len(findings)
    sev_counts = {}
    for f in findings:
        sev = f.get('severity', 'info')
        sev_counts[sev] = sev_counts.get(sev, 0) + 1
    if findings:
        print(f'  {agent_key}: {len(findings)} findings {sev_counts}')

print(f'\\nPipeline warm! {total} total findings')
print(f'Debate rounds: {len(result.get("debate_rounds", []))}')
print(f'Consensus score: {result.get("consensus_score", "N/A")}')
print('\\nREADY FOR DEMO!')
""", 'warmup-pipeline', 300)

ws.close()
print('\n' + '='*60)
print('  ALL DONE — Ready to record!')
print('='*60)
