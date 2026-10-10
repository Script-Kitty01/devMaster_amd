"""Tests for plan.md Phase 3 — explicit backend selection & diagnostics."""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

# Ensure src is importable when pytest runs from repo root.
pytest_plugins = []  # noqa: WPS410


def test_llm_config_env_selects_backend(monkeypatch):
    from src.llm.rocm_service import LLMConfig

    monkeypatch.setenv("KUTAAR_LLM_BACKEND", "llama_cpp")
    monkeypatch.setenv("KUTAAR_MODEL", "/tmp/test.gguf")
    monkeypatch.setenv("KUTAAR_GPU_LAYERS", "0")
    monkeypatch.setenv("KUTAAR_ALLOW_CPU_FALLBACK", "0")

    cfg = LLMConfig.from_env()
    assert cfg.backend == "llama_cpp"
    assert cfg.model_path == "/tmp/test.gguf"
    assert cfg.n_gpu_layers == 0
    assert cfg.allow_cpu_fallback is False


def test_llm_config_defaults_to_ollama(monkeypatch):
    from src.llm.rocm_service import LLMConfig

    monkeypatch.delenv("KUTAAR_LLM_BACKEND", raising=False)

    cfg = LLMConfig.from_env()
    assert cfg.backend == "ollama"
    assert cfg.model_path == "gemma2:2b"
    assert cfg.allow_cpu_fallback is True


def test_diagnostics_reports_backend_and_model(monkeypatch):
    from src.llm.rocm_service import ROCmLLM

    with mock.patch.dict(os.environ, {"KUTAAR_LLM_BACKEND": "ollama", "KUTAAR_MODEL": "gemma2:2b"}):
        llm = ROCmLLM()
        # We don't call initialize, so diagnostics reflect pre-init state.
        diag = llm.diagnostics()
        assert diag["configured_backend"] == "ollama"
        assert diag["model"] == "gemma2:2b"
        assert diag["ready"] is False
        assert "fallback_reason" in diag


def test_llama_cpp_backend_fails_hard_without_model(monkeypatch):
    from src.llm.rocm_service import ROCmLLM

    with mock.patch.dict(
        os.environ,
        {
            "KUTAAR_LLM_BACKEND": "llama_cpp",
            "KUTAAR_MODEL": str(Path("/tmp/does_not_exist.gguf")),
            "KUTAAR_ALLOW_CPU_FALLBACK": "0",
        },
    ):
        llm = ROCmLLM()
        ok = llm.initialize()
        assert ok is False
        assert llm.backend == "cpu"
        assert "not found" in llm.fallback_reason


def test_generate_still_returns_non_empty_text_when_model_is_missing(tmp_path, monkeypatch):
    """plan.md Phase 5: a failed inference must still render a response."""
    from src.llm.rocm_service import ROCmLLM

    monkeypatch.setenv("KUTAAR_LLM_BACKEND", "llama_cpp")
    monkeypatch.setenv("KUTAAR_MODEL", str(tmp_path / "missing.gguf"))
    monkeypatch.setenv("KUTAAR_ALLOW_CPU_FALLBACK", "0")

    llm = ROCmLLM()
    assert llm.initialize() is False

    result = llm.generate("Reply with exactly: rocm smoke", max_tokens=16)
    assert result.text.strip(), "generate() must never return empty text"
    assert result.backend == "cpu"
    assert result.tokens_generated == 0
    assert result.tokens_per_second == 0.0


def test_diagnostics_reports_runtime_evidence(monkeypatch, tmp_path):
    """plan.md Phase 3 item 6: report backend, model, layers, runtime, GPU, reason."""
    from src.llm.rocm_service import ROCmLLM

    monkeypatch.setenv("KUTAAR_LLM_BACKEND", "llama_cpp")
    monkeypatch.setenv("KUTAAR_MODEL", str(tmp_path / "missing.gguf"))

    llm = ROCmLLM()
    llm.initialize()
    diag = llm.diagnostics()

    for key in (
        "configured_backend",
        "active_backend",
        "backend_verified",
        "model",
        "gpu_offload_layers",
        "runtime",
        "runtime_evidence",
        "gpu_backend_library",
        "detected_gpu",
        "hip_version",
        "fallback_reason",
    ):
        assert key in diag

    assert diag["gpu_offload_layers"] == -1
    # "not-checked" is the honest state before the backend was probed.
    assert diag["runtime"] in ("rocm", "cuda", "vulkan", "cpu", "unknown", "not-checked")
    assert diag["fallback_reason"], "a missing model must always be explained"


def test_rocm_is_never_claimed_without_runtime_evidence():
    """plan.md Phase 3 item 3: the class name must not imply a ROCm backend."""
    from src.llm.rocm_service import ROCmLLM

    llm = ROCmLLM()
    llm._backend = "rocm"  # pretend something labelled it ROCm ...
    llm._runtime_info = {}  # ... without any detected backend library

    diag = llm.diagnostics()
    assert diag["backend_verified"] is False
    assert "unverified" in llm.status_line()

