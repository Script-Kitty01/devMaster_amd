# Kutaar Evaluation (§12) — measure before claiming repair reliability

> Do not claim autonomous repair reliability until these values are measured
> and published in the repository. — plan-updrage.md §12

## Fixtures

| Fixture | Intent | Expected behaviour |
|---|---|---|
| `tests/fixtures/python-auth-bug` | change (auth flaw) | evidence-linked finding → approval gate → worktree patch → `pytest -q` passes |

## How to run

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_tools.py tests/test_task_workflow.py tests/test_core_regressions.py tests/test_backend_selection.py -q
.venv\Scripts\python.exe tests/integration/test_repair_loop.py
```

The integration script needs no LLM: it mirrors the workflow nodes with a
simulated approval, applies the repair only in a `kutaar/eval-*` worktree,
runs the allowlisted `pytest -q` via `CheckRunner`, and cleans up.

## Metrics (record every run)

| Metric | Definition | Last run 2026-09-24 (Windows, CPU-only) |
|---|---|---|
| Precision on fixtures | valid findings / reported findings | `1.00` (1/1 evidence-linked) |
| Repair success | patches passing all mandatory checks / attempted | `1/1` on `python-auth-bug` |
| Regression safety | unrelated fixture tests still passing | ✅ `test_auth.py` passes |
| Resource use | time, tool calls, tokens, GPU/CPU fallback | `~2-5s`, `4` tool-equivalents, `0` LLM tokens (scripted), CPU fallback |

## Constraints honoured

Intake merges `task_constraints` (Streamlit checkboxes / CLI confirms) with
free-text hints (`read-only`, `without installing`, `offline`,
`do not start services`). `service_start` is denied with an explicit reason
when `readonly`, `no-net`, or `no-service-start` is active.

## Service observability (P2)

`discover_services` is read-only. `service_start` binds loopback only and
rejects `--host 0.0.0.0`. `service_health` probes loopback URLs with a short
timeout. `service_logs` returns a capped, secret-scrubbed tail
(`service_stop`/`stop_all` terminate everything; nothing is deployed).
`profile_command` records `exit_code`, `elapsed_ms`, RSS, and `rocm-smi`
VRAM delta (zeros when ROCm is absent, e.g. this Windows host).
