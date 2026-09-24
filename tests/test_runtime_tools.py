"""Unit tests for P2 runtime tools (§6.2): discovery, gating, loopback, logs."""
from __future__ import annotations
import tempfile
from pathlib import Path
from src.tools.runtime_tools import (
    ServiceManager,
    constraints_block_service_start,
    discover_services,
    merge_constraints,
    parse_constraints,
    profile_command,
)
from src.tools.tool_registry import ToolRegistry
from src.tools.runtime_tools import register_runtime_tools


def _repo(tmp: Path) -> Path:
    (tmp / "app.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (tmp / "tests").mkdir(exist_ok=True)
    return tmp


def test_parse_and_merge_constraints():
    assert "readonly" in parse_constraints("Review read-only, do not modify")
    assert "no-install" in parse_constraints("without installing deps")
    assert merge_constraints(["readonly"], ["no-net", "readonly"]) == ["readonly", "no-net"]


def test_constraints_block_service_start():
    assert constraints_block_service_start(["readonly"]) is not None
    assert constraints_block_service_start(["no-service-start"]) is not None
    assert constraints_block_service_start([]) is None


def test_discover_finds_fastapi_api():
    with tempfile.TemporaryDirectory() as td:
        repo = _repo(Path(td))
        svcs = discover_services(repo)
        api = [s for s in svcs if s["name"] == "api"]
        assert api and api[0]["command"][:2] == ["uvicorn", "app:app"]
        assert "127.0.0.1" in api[0]["command"]


def test_service_start_blocked_by_constraints():
    with tempfile.TemporaryDirectory() as td:
        mgr = ServiceManager(repo_root=_repo(Path(td)))
        res = mgr.start("api", constraints=["readonly"])
        assert res["ok"] is False and "blocked" in res["error"]


def test_service_start_rejects_non_loopback_and_unknown():
    with tempfile.TemporaryDirectory() as td:
        mgr = ServiceManager(repo_root=_repo(Path(td)))
        assert mgr.start("missing")["ok"] is False
        assert mgr._validate(["uvicorn", "app:app", "--host", "0.0.0.0"]) is not None


def test_service_stop_unknown_and_health_loopback_guard():
    with tempfile.TemporaryDirectory() as td:
        mgr = ServiceManager(repo_root=_repo(Path(td)))
        assert mgr.stop("missing")["ok"] is False
        bad = mgr.health("api", url="http://example.com/")
        assert bad["ok"] is False and "loopback" in bad["error"]


def test_profile_command_policy_blocked():
    with tempfile.TemporaryDirectory() as td:
        res = profile_command(["pip", "install", "x"], cwd=td)
        assert res["ok"] is False and "policy" in res["error"]


def test_runtime_tools_registered_with_allowlist():
    with tempfile.TemporaryDirectory() as td:
        reg = ToolRegistry(str(_repo(Path(td))))
        register_runtime_tools(reg)
        for name in ("discover_services", "service_start", "service_health", "service_logs", "service_stop", "profile_command"):
            assert reg.get_tool(name) is not None
