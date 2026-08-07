"""Final warmup: GPU benchmark + index + pipeline warmup."""
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
        ws.settimeout(60)
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
                traceback = '\n'.join(data.get('content', {}).get('traceback', []))
                print(traceback)
                output.append(traceback)
            elif data.get('msg_type') == 'status' and data.get('content', {}).get('execution_state') == 'idle':
                break
        except Exception as e:
            print(f'\n[ws: {e}]')
            break
    return ''.join(output)

# ── GPU BENCHMARK ──
print('='*60)
print('  GPU BENCHMARK')
print('='*60)
run_code("""
from llama_cpp import Llama
import time

model_path = '/workspace/template-repos/template-1005/repo/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf'

t0 = time.time()
llm = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=2048, n_batch=512, verbose=False)
load_time = time.time() - t0
print(f'Load: {load_time:.1f}s')

_ = llm('Hello', max_tokens=10)

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
    print(f'  Run {i+1}: {tokens} tok in {elapsed:.2f}s = {speed:.1f} tok/s')

avg = total_tokens / total_time
print(f'\\nGPU: AMD Radeon gfx1100 | ROCm 7.2.1 + HIP BLAS')
print(f'AVG: {avg:.1f} tok/s | Load: {load_time:.1f}s | ZERO NVIDIA')
""", 'gpu-bench', 180)

# ── INDEX REPO ──
print('\n' + '='*60)
print('  INDEX DEMO REPO')
print('='*60)
run_code("""
import sys
sys.path.insert(0, '/workspace/template-repos/template-1005/repo')

from pathlib import Path
from src.llm.rocm_service import ROCmLLM
from src.rag.chroma_store import RAGStore
from src.ingestion.repo_indexer import RepoIndexer

repo_path = '/workspace/template-repos/template-1005/repo/demo_repos/sample_app'

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
""", 'index', 120)

# ── PIPELINE WARMUP ──
print('\n' + '='*60)
print('  PIPELINE WARMUP (6 agents)')
print('='*60)
run_code("""
import sys, time
sys.path.insert(0, '/workspace/template-repos/template-1005/repo')

from pathlib import Path
from src.llm.rocm_service import ROCmLLM
from src.rag.chroma_store import RAGStore
from src.tools.tool_registry import ToolRegistry
from src.graph.workflow import KutaarWorkflow
from langchain_core.messages import HumanMessage

repo_path = '/workspace/template-repos/template-1005/repo/demo_repos/sample_app'

rocm_llm = ROCmLLM.get_instance()
rag = RAGStore(persist_dir='/workspace/template-repos/template-1005/repo/chroma_db')
rag.initialize()
tools = ToolRegistry(repo_path)

wf = KutaarWorkflow(rocm_llm, rag, tools)
app = wf.compile()
print('Workflow compiled!')

print('\\nRunning: "Find security vulnerabilities in this codebase"')
print('(Planner -> 4 specialists parallel -> Consensus debate)\\n')

t0 = time.time()
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
elapsed = time.time() - t0

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

print(f'\\nTOTAL: {total} findings in {elapsed:.1f}s')
print(f'Debate rounds: {len(result.get("debate_rounds", []))}')
print(f'Consensus score: {result.get("consensus_score", "N/A")}')
print('\\nPIPELINE WARM! Ready for demo.')
""", 'pipeline', 600)

ws.close()
print('\n' + '='*60)
print('  ALL DONE - Ready to record!')
print('='*60)
