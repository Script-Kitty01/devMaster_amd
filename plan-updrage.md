# Kutaar Upgrade Plan: From Code Reviewer to Verified Engineering Team

## 1. Purpose

This plan evolves Kutaar from its current fixed review workflow into an evidence-driven engineering assistant that can investigate a repository, coordinate a selected team of specialists, propose changes, and verify the result in an isolated workspace.

The goal is not to maximize the number of agents. The goal is to make a small team reliably complete a real engineering loop:

```text
Understand task → investigate with tools → record evidence → plan change
→ implement in isolation → test and scan → review → report or retry
```

The existing project is a good starting point:

- `src/graph/workflow.py` already coordinates Planner, RAG, four specialists, and Consensus with LangGraph.
- `src/agents/` has role-specific prompts and structured findings.
- `src/tools/tool_registry.py` provides local repository tools and security scanners.
- `src/ingestion/` and `src/rag/` provide local repository indexing and semantic retrieval.
- `src/ui/chat_app.py` provides the Streamlit entry point.

## 2. Product Boundary and Success Definition

### Target user promise

> Point Kutaar at a local repository, describe a review, bug, or scoped change, and receive an evidence-backed, verified result without sending source code to an external service by default.

### First release supported tasks

1. Review a repository or a focused subsystem.
2. Investigate a reproducible bug and produce a diagnosis.
3. Propose a patch and apply it only in an isolated worktree.
4. Run the repository's safe, explicit checks: tests, linting, build, and static security scans.
5. Return a final report containing evidence, the patch diff, and verification results.

### Explicit non-goals for the first release

- Automatic production deployment, infrastructure changes, package publishing, or issue/PR submission.
- Unlimited autonomous retries or unrestricted shell access.
- A catalog of 20+ independently implemented agents.
- Support for every language, test runner, or deployment platform.

## 3. Proposed Architecture

```text
User / Streamlit workspace
          │
          ▼
Task Manager ──► Team Builder ──► LangGraph task workflow
                                      │
                ┌─────────────────────┼──────────────────────┐
                ▼                     ▼                      ▼
         Repository tools       Shared artifacts       Repository index
         (read/search/test/     (evidence, plans,      (RAG is one
          static analysis)       decisions, patch)      retrieval tool)
                │                     │
                └────────────► Specialist agents ◄─────┘
                                      │
                                      ▼
                              Review / consensus gate
                                      │
                           approval required to modify
                                      ▼
                       Isolated worktree + patch executor
                                      │
                                      ▼
                       Test, build, lint, scan verifier
                                      │
                                pass / bounded retry
                                      ▼
                                 Final report
```

### Core design rules

- **Evidence first:** An agent cannot report a high-impact finding without a file, line range, tool output, or otherwise explicit evidence source.
- **Least privilege:** Every role has an allowlist of tools. File and command tools remain repository-scoped.
- **Read-only by default:** Investigation and planning never modify the repository.
- **Human approval before mutation:** Creating a branch/worktree and applying a patch requires an explicit user confirmation in the UI.
- **Isolated execution:** Changes and checks run in a temporary Git worktree; the original checkout remains untouched.
- **Bounded autonomy:** A task has maximum tool calls, time limit, patch retries, and output size.
- **Deterministic gates:** Tests, linting, build, and scanners determine verification status; LLM prose never substitutes for a passing check.

## 4. Agent Model

Start with six real roles. Existing Security, Architecture, Performance, DevOps, Planner, and Consensus behavior can be reused or merged into these capabilities.

| Role                 | Responsibility                                                  | Initial tool permissions                         | Deliverable                          |
| -------------------- | --------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------ |
| Task Manager         | Validate request, scope, constraints, and approval requirements | repository summary, read-only task metadata      | `TaskBrief`                          |
| Investigator         | Explore repository structure, trace code, collect evidence      | search, read, AST/import graph, Git history, RAG | `Evidence` records                   |
| Security Reviewer    | Identify security and dependency risks                          | read/search, Bandit, Semgrep, dependency audit   | verified security findings           |
| Implementation Agent | Propose a minimal patch after approval                          | read/search, diff, patch in worktree             | `PatchProposal`                      |
| Verification Agent   | Discover and run approved checks                                | test discovery, test/lint/build/scan commands    | `VerificationResult`                 |
| Review Agent         | Review the patch and all verification evidence                  | read/diff/findings/results                       | approve, reject, or request revision |

### Capability profiles, not agent proliferation

Frontend, backend, database, DevOps, performance, and architecture should initially be capability profiles selected by the Team Builder. For example:

```text
Security audit       → Investigator + Security Reviewer + Review Agent
FastAPI bug          → Investigator + Implementation + Verification + Review
Docker readiness     → Investigator(DevOps profile) + Security + Review
Performance review   → Investigator(performance profile) + Verification + Review
```

Create a separate agent class only once its tool use, artifacts, or workflow differs materially.

## 5. Shared State and Artifacts

Replace prose-only handoffs with typed artifacts. Extend `ConversationState` or introduce a `TaskState` TypedDict that is passed through the new workflow.

```python
class Evidence(TypedDict):
    id: str
    source: str                 # tool name, RAG, or user-provided
    file_path: str
    line_start: int
    line_end: int
    excerpt: str
    command: str | None
    observed_at: str
    confidence: float

class TaskBrief(TypedDict):
    task_id: str
    user_request: str
    intent: Literal["review", "diagnose", "change"]
    scope_paths: list[str]
    constraints: list[str]
    selected_profiles: list[str]
    approval_required: bool

class PatchProposal(TypedDict):
    id: str
    summary: str
    rationale: str
    files_changed: list[str]
    unified_diff: str
    linked_evidence_ids: list[str]
    risk_level: Literal["low", "medium", "high"]

class VerificationResult(TypedDict):
    check_id: str
    name: str
    command: list[str]
    status: Literal["passed", "failed", "skipped", "blocked"]
    exit_code: int | None
    summary: str
    output_path: str
```

`AgentFinding` should gain `evidence_ids`, `verification_status`, and `requires_fix`. High and critical findings without evidence should be downgraded to an explicitly labeled hypothesis.

## 6. Tooling Upgrade

### 6.1 Keep and harden existing tools

Refactor `src/tools/tool_registry.py` into a tool layer with a shared safety policy:

- Preserve the repository boundary enforcement for all filesystem tools.
- Validate all paths with `Path.resolve()` plus `relative_to(repo_root)`.
- Give every call a timeout, output cap, structured result, and audit log.
- Avoid passing user/LLM strings through a shell; use argument lists only.
- Exclude `.git`, virtual environments, dependency folders, secrets files, and generated build output by default.

### 6.2 Add tools in this order

| Priority | Tool group              | First functions                                                                    |
| -------- | ----------------------- | ---------------------------------------------------------------------------------- |
| P0       | Repository intelligence | `list_files`, `read_file`, `search_code`, `find_definition`, `find_references`     |
| P0       | Safe diagnostics        | `discover_checks`, `run_test`, `run_linter`, `run_build`, `git_diff`, `git_status` |
| P1       | Structural analysis     | Python AST summary, import graph, complexity calculation, API route discovery      |
| P1       | Dependency analysis     | lockfile parsing, outdated/dependency audit, manifest summary                      |
| P1       | Security                | preserve Bandit/Semgrep; add secret detection with redacted output                 |
| P2       | Runtime diagnosis       | controlled service start, health check, log collection, profiler integration       |

### 6.3 RAG's role

Keep `RAGStore` as `semantic_search(query)`, not as the only way agents understand a repository. RAG is valuable for broad natural-language retrieval; exact search, symbol reference lookup, AST structure, Git history, and test output are stronger evidence for implementation work.

## 7. Workflow Implementation

Implement a second workflow first; do not destabilize the existing review graph. Add a `TaskWorkflow` that can later replace or wrap `KutaarWorkflow`.

```text
intake
  → repository reconnaissance
  → team recommendation / user selection
  → investigation loop
  → evidence review and implementation plan
  → WAIT FOR USER APPROVAL
  → create isolated worktree
  → patch proposal and application
  → verification
  → review
  → final report

verification failed and retries remain
  → debugger/investigator
  → revised patch
  → verification
```

### Investigation loop

Each specialist receives a bounded observation budget, for example 8 tool calls and 60 seconds per phase. It can request an action using a strict schema:

```json
{
  "decision": "tool_call",
  "tool": "read_file",
  "arguments": { "file_path": "src/auth.py", "start_line": 1, "end_line": 200 },
  "reason": "Verify the JWT validation path before reporting a vulnerability."
}
```

The orchestrator, not the LLM, validates the selected tool against the agent profile and task limits, executes it, saves its structured observation, and returns a concise result to the agent. The loop ends when the agent returns `final_artifact`, exhausts its budget, or encounters a policy block.

### Dynamic routing

Use the Task Manager's validated `TaskBrief` and a static routing table at first. Do not let free-form model output generate arbitrary LangGraph nodes. The Team Builder may recommend profiles; the user accepts, removes, or adds from a small supported set.

## 8. Isolated Implementation and Verification

### Approval boundary

Before an implementation action, show the user:

- the proposed files and a summary of changes;
- linked evidence and expected risk;
- planned verification commands;
- any package installation or service startup request.

Only then create a worktree with a name such as `kutaar/<task-id>` and apply the patch there. Do not commit, push, deploy, open a pull request, or modify the original branch automatically.

### Sandbox executor

Create an executor abstraction with two implementations:

1. `LocalWorktreeExecutor` for the first MVP. It runs only an allowlist of discovered commands under the worktree, with timeouts and captured output.
2. `ContainerExecutor` later, for stronger isolation of untrusted projects and dependency installation.

Verification must record exactly what ran, where it ran, the exit code, and a bounded output excerpt. A passing final result requires all mandatory checks to pass; missing prerequisites are `blocked`, never silently treated as success.

### Retry policy

- Maximum two patch revisions by default.
- A failure must produce a diagnosis artifact tied to test/build output.
- Stop and request user direction when failures require external credentials, a database, production-like infrastructure, broad dependency upgrades, or a task-scope change.

## 9. UI Upgrade

Extend `src/ui/chat_app.py` gradually rather than replacing Streamlit.

### Workspace intake

- Repository path and index status.
- Task text plus task type: Review, Diagnose, or Change.
- Recommended team profiles with checkboxes for user selection.
- A short list of constraints: read-only, no dependency installs, no network, or limited paths.

### Execution view

- A phase timeline: Intake → Investigating → Plan ready → Waiting for approval → Implementing → Verifying → Complete.
- Per-agent status and latest evidence, rather than hidden background activity.
- Finding cards that link to source evidence and distinguish `verified`, `hypothesis`, `fixed`, and `blocked`.
- Diff preview and explicit approval control before mutation.
- Verification table listing check name, command, exit status, and concise output.

The UI must never imply that a patch is applied to the original repository when it exists only in an isolated worktree.

## 10. File-Level Delivery Plan

| Milestone          | New or changed files                                                                  | Result                                                                       |
| ------------------ | ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| M0: Baseline       | `tests/`, `pyproject.toml`, existing modules                                          | Repeatable tests for indexer, tools, state, and workflow smoke paths         |
| M1: Contracts      | `src/state/task_state.py`, `src/models/artifacts.py`                                  | Typed `TaskBrief`, `Evidence`, `PatchProposal`, `VerificationResult`         |
| M2: Registry       | `src/agents/agent_registry.py`, `src/agents/profiles.py`, `src/tools/policy.py`       | Capability profiles and tool permission enforcement                          |
| M3: Investigation  | `src/graph/task_workflow.py`, `src/agents/investigator_agent.py`, tool additions      | Bounded tool-observation investigation loop                                  |
| M4: Verification   | `src/execution/worktree.py`, `src/execution/executor.py`, `src/tools/check_runner.py` | Worktree creation, test/lint/build execution, structured results             |
| M5: Implementation | `src/agents/implementation_agent.py`, `src/agents/review_agent.py`, patch utility     | Approval-gated patch proposal, apply, review, and retry                      |
| M6: UI             | `src/ui/chat_app.py` or `src/ui/workspace_app.py`                                     | Team selection, progress timeline, approval, diff, verification presentation |
| M7: Evaluation     | `tests/fixtures/`, `tests/integration/`, `docs/evaluation.md`                         | Measured reliability on intentionally flawed sample repositories             |

## 11. Milestones and Acceptance Criteria

### M0 — Stabilize the current system

**Scope:** Correctness before new capabilities.

- Add tests for tool results, RAG index/query behavior, graph state, and agents using a fake LLM.
- Ensure every tool returns a structured failure instead of raising into the workflow.
- Persist tool logs and inference timing through returned LangGraph state updates rather than in-place mutation.
- Ensure repository indexing is per-repository and never leaks vectors across projects.

**Acceptance:** A clean environment can run `python -m unittest discover -s tests -v`; the workflow can produce a review with a fake LLM and fake tools.

### M1 — Structured task and evidence artifacts

**Scope:** Add typed contracts and observable state.

- Implement `TaskState` and artifact dataclasses/TypedDicts.
- Attach evidence IDs to findings.
- Store every tool invocation result in an append-only task log.
- Add validation at all LLM-to-system boundaries.

**Acceptance:** The UI can display a finding, its evidence source, and its verification status without parsing prose.

### M2 — Capability-based team selection

**Scope:** Add user-controlled routing without building many agents.

- Implement `AgentProfile` with role, allowed tools, artifact types, and limits.
- Build a Team Builder recommendation function from task intent, repository metadata, and supported profiles.
- Add UI checkboxes for supported profiles and persist the selection in `TaskBrief`.
- Route selected profiles using a fixed, testable map.

**Acceptance:** A security task invokes only the selected security-oriented profiles; a narrow task does not automatically run every existing specialist.

### M3 — Autonomous, bounded investigation

**Scope:** Give agents an actual observation loop.

- Implement repository reconnaissance: tree, manifests, language counts, test locations, and Git summary.
- Implement `ToolCallRequest` validation and an orchestrator-controlled tool loop.
- Add exact source lookup and basic Python AST/import-graph tools.
- Keep RAG as an optional semantic-search tool.

**Acceptance:** Given a fixture bug, the Investigator produces an evidence trail showing the relevant file and path before it proposes a diagnosis.

### M4 — Verification executor

**Scope:** Safely prove changes work.

- Discover project checks from allowlisted markers (`pyproject.toml`, `package.json`, `Makefile`, etc.).
- Implement a local Git worktree lifecycle and command runner with no shell interpolation.
- Add test, lint, build, Bandit, and Semgrep verification adapters.
- Record outputs to a task-local artifact directory excluded from Git.

**Acceptance:** A known test failure is correctly reported as failed; a passing fixture produces an auditable check report.

### M5 — Approval-gated implementation loop

**Scope:** Make scoped repairs safely.

- Generate a patch proposal tied to evidence and accepted plan.
- Render the diff and obtain user approval.
- Apply only to the isolated worktree.
- Run verification, invoke review, and permit at most two diagnosis/revision cycles.

**Acceptance:** On a fixture with a known one-file bug, Kutaar proposes a minimal diff, applies it only after approval, and marks completion only after mandatory checks pass.

### M6 — Evidence-first workspace UX

**Scope:** Make operation understandable and demonstrable.

- Add phase timeline, agent status, team editor, evidence links, diff review, and verification report.
- Clearly label the current directory, worktree branch, approval status, and blocked state.
- Support export of a final Markdown report.

**Acceptance:** A demo viewer can follow why the system made a change and reproduce the verification commands from the UI/report.

## 12. Testing and Evaluation Strategy

### Unit tests

- Path policy and command construction.
- Artifact schema validation.
- Tool authorization by profile.
- Indexing behavior, repository isolation, and incremental updates.
- Worktree lifecycle cleanup on failures.
- Agent decision parsing with malformed model output.

### Integration fixtures

Create small repositories under `tests/fixtures/` containing controlled issues:

| Fixture            | Expected result                                    |
| ------------------ | -------------------------------------------------- |
| `python-auth-bug`  | Evidence-backed auth diagnosis and a passing patch |
| `insecure-config`  | Bandit/Semgrep finding with correct file/line      |
| `broken-test`      | Test failure surfaced without a fabricated fix     |
| `docker-misconfig` | Docker findings with actionable evidence           |
| `multi-module-app` | Correct routing and import/reference discovery     |

### Evaluation measures

- Evidence coverage: percentage of high/critical findings linked to a primary source.
- Precision on fixtures: valid findings divided by reported findings.
- Repair success: patches that pass all mandatory checks divided by attempted repairs.
- Regression safety: unrelated fixture tests remain passing after the repair.
- Resource use: time, tool calls, model tokens, and GPU/CPU fallback status per task.

Do not claim autonomous repair reliability until these values are measured and published in the repository.

## 13. Dependency and Deployment Choices

- Preserve the local-first ROCm/llama-cpp path as the default.
- Make cloud generation an explicit optional backend, never a silent fallback for repository content.
- Add lightweight parsing dependencies only when backed by tests. Start with Python's built-in `ast`; introduce tree-sitter only when cross-language support is needed.
- Keep the first executor local and worktree-based. Add a container backend only after command policies and artifact collection are reliable.
- Never include real credentials, models, vector indexes, worktree artifacts, or scanner output containing secrets in version control.

## 14. Risks and Mitigations

| Risk                                | Mitigation                                                                                   |
| ----------------------------------- | -------------------------------------------------------------------------------------------- |
| Overbuilding agent personas         | Build capability profiles and six core roles first                                           |
| Hallucinated diagnosis or patch     | Require evidence links; verification gates completion                                        |
| Unsafe execution                    | Worktrees, allowlisted command adapters, timeouts, no shell interpolation, approval boundary |
| Runaway retries/cost                | Fixed tool budgets, maximum two patch revisions, explicit blocked state                      |
| Cross-repository data leakage       | Per-repository index namespace and task-local artifacts                                      |
| Existing projects have custom setup | Treat undiscoverable commands as blocked and ask the user rather than guessing               |
| UI hides autonomous actions         | Render phase, evidence, planned commands, worktree, and approval state explicitly            |

## 15. Recommended First Two Weeks

### Week 1

1. Complete M0 tests and remove state mutation from workflow nodes.
2. Add `TaskState`, `Evidence`, `TaskBrief`, and validation helpers.
3. Implement `AgentProfile`, `ToolPolicy`, and a static team-routing table.
4. Add reconnaissance plus `find_definition`/basic Python AST inspection.

### Week 2

1. Implement local worktree creation and cleanup.
2. Add allowlisted test/lint/build adapters with structured results.
3. Add the approval-gated patch proposal flow for one Python fixture.
4. Update Streamlit with task type, selected profiles, phase progress, and verification display.

At the end of these two weeks, Kutaar should be able to complete one narrow repair end-to-end. Expand its catalog and language support only after that loop is reliable.

## 16. Resume-Ready Milestone

The first credible resume claim is:

> Built Kutaar, a local-first multi-agent software engineering assistant using LangGraph and AMD ROCm. It routes tasks to capability-based specialists, gathers evidence through repository and static-analysis tools, proposes approval-gated patches in isolated Git worktrees, and verifies repairs with automated checks.

That claim is strong only when the fixture suite, isolated worktree flow, evidence records, and verification reports genuinely exist.
