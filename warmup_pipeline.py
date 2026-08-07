"""Re-run indexing + pipeline warmup now that deps are installed."""
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
        ws.settimeout(30)
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

# ── STEP 3: Index Demo Repo ──
print('='*60)
print('  STEP 3: Index Demo Repo with ChromaDB')
print('='*60)
run_code("""
import sys
sys.path.insert(0, '/workspace/template-repos/template-1005/repo')

from pathlib import Path
from src.llm.rocm_service import ROCmLLM
from src.rag.chroma_store import RAGStore
from src.ingestion.repo_indexer import RepoIndexer

repo_path = '/workspace/template-repos/template-1005/repo/demo_repos/sample_app'

print('Initializing ROCm LLM...')
rocm_llm = ROCmLLM.get_instance()
rocm_llm.initialize()
print('LLM ready!')

print('\\nInitializing ChromaDB RAG store...')
rag = RAGStore(persist_dir='/workspace/template-repos/template-1005/repo/chroma_db')
rag.initialize()
print('RAG store ready!')

print(f'\\nIndexing: {repo_path}')
indexer = RepoIndexer(repo_path)
chunks = indexer.chunk_all()
stats = indexer.stats()
print(f'  Files found: {stats["file_count"]}')
print(f'  Chunks created: {len(chunks)}')

rag.reset()
count = rag.index_chunks(chunks, rocm_llm.embed)
print(f'\\n  Indexed {count} chunks into ChromaDB!')
print('  RAG store is READY for demo!')
""", 'index-repo', 180)

# ── STEP 4: Pre-warm Agent Pipeline ──
print('\n' + '='*60)
print('  STEP 4: Pre-warm Agent Pipeline (6 agents)')
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

print('Loading components...')
rocm_llm = ROCmLLM.get_instance()
rag = RAGStore(persist_dir='/workspace/template-repos/template-1005/repo/chroma_db')
rag.initialize()
tools = ToolRegistry(repo_path)

print('Compiling LangGraph workflow (6 agents)...')
wf = KutaarWorkflow(rocm_llm, rag, tools)
app = wf.compile()
print('Workflow compiled!')

print('\\n' + '='*50)
print('Running warmup query:')
print('  "Find security vulnerabilities in this codebase"')
print('='*50)
print('(This runs Planner -> 4 specialists in parallel -> Consensus debate)')
print()

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

print(f'\\nPipeline completed in {elapsed:.1f}s')
print()

# Count findings by agent
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

print(f'\\n  TOTAL: {total} findings')
print(f'  Debate rounds: {len(result.get("debate_rounds", []))}')
print(f'  Consensus score: {result.get("consensus_score", "N/A")}')

# Show a few findings
print('\\n  Sample findings:')
for agent_key in ["security", "performance", "architecture", "devops"]:
    findings = result.get(f"{agent_key}_findings", [])
    for f in findings[:2]:
        sev = f.get('severity', 'info')
        title = f.get('title', '?')
        print(f'    [{sev.upper()}] {title}')

print('\\n' + '='*50)
print('  PIPELINE IS WARM AND READY FOR DEMO!')
print('='*50)
""", 'warmup-pipeline', 600)

ws.close()
print('\nDone!')
