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
