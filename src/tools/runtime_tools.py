"""Runtime Tools - P2 service start/health/logs/profiler (plan-updrage 6.2)."""
from __future__ import annotations
import json, logging, subprocess, time, urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from src.models.artifacts import scrub_secret_text
from src.tools.policy import CommandPolicy
from src.tools.tool_registry import ToolDef, ToolRegistry, ToolResult
logger = logging.getLogger(__name__)
CONSTRAINT_READONLY = "readonly"
CONSTRAINT_NO_INSTALL = "no-install"
CONSTRAINT_NO_NET = "no-net"
CONSTRAINT_NO_SERVICE_START = "no-service-start"
ALL_CONSTRAINTS = (CONSTRAINT_READONLY, CONSTRAINT_NO_INSTALL, CONSTRAINT_NO_NET, CONSTRAINT_NO_SERVICE_START)
_HINTS = (("read-only", CONSTRAINT_READONLY), ("readonly", CONSTRAINT_READONLY), ("do not modify", CONSTRAINT_READONLY), ("do not install", CONSTRAINT_NO_INSTALL), ("no install", CONSTRAINT_NO_INSTALL), ("without installing", CONSTRAINT_NO_INSTALL), ("no network", CONSTRAINT_NO_NET), ("offline", CONSTRAINT_NO_NET), ("no internet", CONSTRAINT_NO_NET), ("do not start", CONSTRAINT_NO_SERVICE_START), ("no services", CONSTRAINT_NO_SERVICE_START), ("no service start", CONSTRAINT_NO_SERVICE_START))
def parse_constraints(task_text: str) -> list[str]:
    low = (task_text or "").lower()
    found: list[str] = []
    for hint, c in _HINTS:
        if hint in low and c not in found:
            found.append(c)
    return found
def merge_constraints(*groups) -> list[str]:
    merged: list[str] = []
    for g in groups:
        for i in g or []:
            if i not in merged:
                merged.append(i)
    return merged
def constraints_block_service_start(constraints) -> Optional[str]:
    active = set(constraints or [])
    if CONSTRAINT_READONLY in active:
        return "readonly constraint: repo must not be modified/executed persistently"
    if CONSTRAINT_NO_SERVICE_START in active:
        return "no-service-start constraint: start declined by request"
    if CONSTRAINT_NO_NET in active:
        return "no-net constraint: start needs local networking"
    return None
def discover_services(repo_path) -> list[dict[str, Any]]:
    root = Path(repo_path).resolve()
    found: list[dict[str, Any]] = []
    for cand in [root / "app.py", root / "main.py", root / "app" / "main.py"]:
        if cand.is_file():
            try:
                text = cand.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "FastAPI" in text:
                rel = cand.relative_to(root).as_posix()
                mod = rel[:-3].replace("/", ".")
                found.append({"name": "api", "kind": "api", "command": ["uvicorn", f"{mod}:app", "--host", "127.0.0.1", "--port", "8000"], "cwd": str(root), "description": f"FastAPI at {rel} (loopback)"})
                break
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8", errors="replace")).get("scripts", {})
        except Exception:
            scripts = {}
        if isinstance(scripts, dict) and isinstance(scripts.get("dev"), str):
            found.append({"name": "frontend", "kind": "frontend", "command": ["npm", "run", "dev", "--", "--host", "127.0.0.1"], "cwd": str(root), "description": "npm run dev (loopback)"})
    compose = root / "docker-compose.yml"
    if not compose.is_file():
        compose = root / "compose.yaml"
    if compose.is_file():
        found.append({"name": "db", "kind": "database", "command": ["docker", "compose", "up", "--wait"], "cwd": str(root), "description": "compose (explicit start only)"})
    if (root / "tests").is_dir() and not found:
        found.append({"name": "pytest", "kind": "check", "command": ["pytest", "-q"], "cwd": str(root), "description": "pytest suite (one-shot)"})
    return found
def _is_loopback_url(url: str) -> bool:
    low = url.lower()
    return low.startswith("http://127.0.0.1") or low.startswith("http://localhost")
@dataclass
class RunningService:
    name: str
    command: list[str]
    cwd: str
    process: Any = None
    log_path: str = ""
    started_at: float = 0.0
    port: Optional[int] = None
@dataclass
class ServiceManager:
    """Owns ephemeral loopback services for one task run."""
    repo_root: str | Path
    popen_factory: Callable[..., Any] = subprocess.Popen
    services: dict[str, RunningService] = field(default_factory=dict)
    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root).resolve()
    def start(self, name: str, *, constraints=None, port: int = 8000) -> dict[str, Any]:
        blocked = constraints_block_service_start(constraints)
        if blocked:
            return {"ok": False, "error": f"service start blocked: {blocked}"}
        spec = {s["name"]: s for s in discover_services(self.repo_root)}.get(name)
        if spec is None:
            return {"ok": False, "error": f"unknown service: {name}"}
        command = list(spec["command"])
        if "--port" in command:
            command[command.index("--port") + 1] = str(port)
        bad = self._validate(command)
        if bad:
            return {"ok": False, "error": f"service start blocked: {bad}"}
        if name in self.services and self._alive(self.services[name]):
            return {"ok": True, "name": name, "already_running": True, "port": self.services[name].port}
        log_path = str(Path(self.repo_root) / f".kutaar-{name}.log")
        try:
            fh = open(log_path, "ab")
            proc = self.popen_factory(command, cwd=spec.get("cwd") or str(self.repo_root), stdout=fh, stderr=subprocess.STDOUT)
        except FileNotFoundError:
            return {"ok": False, "error": f"command not found: {command[0]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:300]}
        self.services[name] = RunningService(name, command, spec.get("cwd") or str(self.repo_root), proc, log_path, time.perf_counter(), port if "--port" in spec["command"] else None)
        return {"ok": True, "name": name, "command": command, "log_path": log_path, "port": port}
    def health(self, name: str, *, url: str = "", timeout: float = 5.0) -> dict[str, Any]:
        svc = self.services.get(name)
        target = url or (f"http://127.0.0.1:{svc.port}/" if svc and svc.port else "")
        if not target:
            return {"ok": False, "error": "no health URL known"}
        if not _is_loopback_url(target):
            return {"ok": False, "error": f"non-loopback URL blocked: {target}"}
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(target, timeout=timeout) as resp:
                status = getattr(resp, "status", 200)
                body = resp.read(4096).decode("utf-8", errors="replace")
        except Exception as exc:
            return {"ok": False, "name": name, "url": target, "error": str(exc)[:300]}
        return {"ok": 200 <= status < 500, "name": name, "url": target, "status": status, "body_excerpt": scrub_secret_text(body[:1000]), "elapsed_ms": (time.perf_counter() - t0) * 1000, "alive": self._alive(svc)}
    def logs(self, name: str, *, tail: int = 200, max_chars: int = 50000) -> dict[str, Any]:
        svc = self.services.get(name)
        if svc is None:
            return {"ok": False, "error": f"unknown service: {name}"}
        try:
            text = Path(svc.log_path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"ok": False, "error": f"cannot read log: {exc}"}
        excerpt = scrub_secret_text("\n".join(text.splitlines()[-max(1, tail):]))[-max_chars:]
        return {"ok": True, "name": name, "log_path": svc.log_path, "excerpt": excerpt}
    def stop(self, name: str) -> dict[str, Any]:
        svc = self.services.pop(name, None)
        if svc is None:
            return {"ok": False, "error": f"unknown service: {name}"}
        try:
            if self._alive(svc):
                svc.process.terminate()
                try:
                    svc.process.wait(timeout=10)
                except Exception:
                    try:
                        svc.process.kill()
                    except Exception:
                        pass
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:300]}
        return {"ok": True, "name": name, "stopped": True}
    def stop_all(self) -> dict[str, Any]:
        stopped = [n for n in list(self.services) if self.stop(n).get("ok")]
        return {"ok": True, "stopped": stopped}
    @staticmethod
    def _alive(svc) -> bool:
        try:
            return svc is not None and svc.process is not None and svc.process.poll() is None
        except Exception:
            return False
    @staticmethod
    def _validate(command: list[str]) -> Optional[str]:
        v = CommandPolicy().validate(command)
        if v is not None:
            return f"{v.reason}: {v.detail}"
        if "0.0.0.0" in " ".join(str(c) for c in command):
            return "non-loopback bind not allowed (use 127.0.0.1)"
        return None
def profile_command(argv: list[str], *, cwd, timeout: float = 300.0, max_chars: int = 20000) -> dict[str, Any]:
    v = CommandPolicy().validate(argv)
    if v is not None:
        return {"ok": False, "error": f"policy blocked: {v.reason}"}
    gpu_before = _gpu_mb()
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
        ms = (time.perf_counter() - t0) * 1000
        return {"ok": True, "command": argv, "exit_code": proc.returncode, "elapsed_ms": ms, "rss_mb_after": _rss_mb(), "gpu_mem_mb_before": gpu_before, "gpu_mem_mb_after": _gpu_mb(), "stdout_tail": scrub_secret_text((proc.stdout or "")[-max_chars:]), "stderr_tail": scrub_secret_text((proc.stderr or "")[-max_chars:])}
    except subprocess.TimeoutExpired:
        return {"ok": False, "command": argv, "error": f"timed out after {timeout:.0f}s"}
    except FileNotFoundError:
        return {"ok": False, "command": argv, "error": f"command not found: {argv[0]}"}
    except Exception as exc:
        return {"ok": False, "command": argv, "error": str(exc)[:300]}
def _gpu_mb() -> float:
    try:
        proc = subprocess.run(["rocm-smi", "--showmeminfo", "vram"], capture_output=True, text=True, timeout=5)
    except Exception:
        return 0.0
    import re as _re
    nums = _re.findall(r"(\d+(?:\.\d+)?)\s*MB", proc.stdout or "")
    try:
        return float(nums[0]) if nums else 0.0
    except ValueError:
        return 0.0
def _rss_mb() -> float:
    try:
        import psutil
        return float(psutil.Process().memory_info().rss) / (1024 * 1024)
    except Exception:
        return 0.0
def register_runtime_tools(registry: ToolRegistry, manager: ServiceManager | None = None) -> ServiceManager:
    bound = manager or ServiceManager(repo_root=registry.repo_path)
    bound.repo_root = Path(registry.repo_path).resolve()
    def _discover(repo_path: str, **_: Any) -> ToolResult:
        t0 = time.perf_counter()
        svcs = discover_services(repo_path)
        return ToolResult("discover_services", True, f"discovered {len(svcs)} service(s)", svcs, elapsed_ms=(time.perf_counter() - t0) * 1000)
    def _start(repo_path: str, *, name: str = "api", port: int = 8000, constraints: Any = None, **_: Any) -> ToolResult:
        t0 = time.perf_counter()
        res = bound.start(name, constraints=list(constraints or []), port=int(port))
        return ToolResult("service_start", bool(res.get("ok")), res.get("error", f"service {name} started"), [res], elapsed_ms=(time.perf_counter() - t0) * 1000)
    def _health(repo_path: str, *, name: str = "api", url: str = "", **_: Any) -> ToolResult:
        t0 = time.perf_counter()
        res = bound.health(name, url=url)
        return ToolResult("service_health", bool(res.get("ok")), res.get("error", f"health {res.get('status', '?')}"), [res], elapsed_ms=(time.perf_counter() - t0) * 1000)
    def _logs(repo_path: str, *, name: str = "api", tail: int = 200, **_: Any) -> ToolResult:
        t0 = time.perf_counter()
        res = bound.logs(name, tail=int(tail))
        return ToolResult("service_logs", bool(res.get("ok")), res.get("error", "log tail"), [res], raw_output=str(res.get("excerpt", ""))[:20000], elapsed_ms=(time.perf_counter() - t0) * 1000)
    def _stop(repo_path: str, *, name: str = "api", **_: Any) -> ToolResult:
        res = bound.stop(name)
        return ToolResult("service_stop", bool(res.get("ok")), res.get("error", f"service {name} stopped"), [res])
    def _profile(repo_path: str, *, command: Any = None, timeout: float = 120.0, **_: Any) -> ToolResult:
        t0 = time.perf_counter()
        res = profile_command(list(command or []), cwd=repo_path, timeout=float(timeout))
        return ToolResult("profile_command", bool(res.get("ok")), res.get("error", f"exit={res.get('exit_code')}"), [res], elapsed_ms=(time.perf_counter() - t0) * 1000)
    registry.register(ToolDef("discover_services", "Discover runnable local services (no start)", "devops", _discover))
    registry.register(ToolDef("service_start", "Start discovered service on loopback (constraint-gated)", "devops", _start))
    registry.register(ToolDef("service_health", "Probe service health URL (loopback only)", "devops", _health))
    registry.register(ToolDef("service_logs", "Read bounded redacted service log tail", "devops", _logs))
    registry.register(ToolDef("service_stop", "Stop a running service", "devops", _stop))
    registry.register(ToolDef("profile_command", "Run command with time/RSS/GPU sampling", "performance", _profile))
    return bound

