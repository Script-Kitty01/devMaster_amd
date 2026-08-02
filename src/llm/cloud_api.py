"""
Radeon Cloud API Integration (Bonus) — compares local ROCm inference against
AMD Radeon cloud-hosted models with quantization/distillation analysis.

This module provides:
- Cloud API client for AMD Radeon cloud inference
- Quantization comparison (Q4 vs Q8 vs FP16)
- Distillation quality assessment
- Latency/throughput benchmarking between local and cloud
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class CloudModelInfo:
    """Metadata about a cloud-hosted model."""
    model_id: str
    quantization: str  # "Q4_K_M", "Q8_0", "FP16", etc.
    max_tokens: int
    supports_streaming: bool = False


@dataclass
class ComparisonResult:
    """Side-by-side comparison of local vs cloud inference."""
    prompt: str
    local_text: str
    local_tps: float
    local_latency_ms: float
    cloud_text: str
    cloud_tps: float
    cloud_latency_ms: float
    cloud_model: str
    speedup: float  # cloud_tps / local_tps
    quality_notes: str = ""


class RadeonCloudClient:
    """
    Client for AMD Radeon Cloud API inference.

    Usage:
        client = RadeonCloudClient(api_url="https://api.radeon.amd.com/v1", api_key="...")
        result = client.generate("Explain code review best practices.")
        comparison = client.compare_with_local(llm, "What is dependency injection?")
    """

    def __init__(
        self,
        api_url: str,
        api_key: str = "",
        *,
        timeout: int = 120,
        default_model: str = "llama-3.2-3b-instruct",
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.default_model = default_model
        self._available_models: list[CloudModelInfo] = []

    # ------------------------------------------------------------------
    # API Methods
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 512,
        stream: bool = False,
    ) -> dict[str, Any]:
        """
        Call the Radeon Cloud API for text generation.

        Returns dict with keys: text, tokens_generated, tokens_per_second, model.
        """
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": model or self.default_model,
            "messages": [],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        payload["messages"].append({"role": "user", "content": prompt})

        t0 = time.perf_counter()

        try:
            resp = requests.post(
                f"{self.api_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            elapsed = time.perf_counter() - t0
            resp.raise_for_status()
            data = resp.json()

            choice = data.get("choices", [{}])[0]
            text = choice.get("message", {}).get("content", "")
            usage = data.get("usage", {})
            tokens = usage.get("completion_tokens", len(text.split()))
            tps = tokens / elapsed if elapsed > 0 else 0.0

            return {
                "text": text.strip(),
                "tokens_generated": tokens,
                "tokens_per_second": tps,
                "model": data.get("model", model or self.default_model),
                "latency_ms": elapsed * 1000,
            }

        except requests.exceptions.RequestException as exc:
            logger.error("Cloud API request failed: %s", exc)
            return {
                "text": f"[Cloud API Error: {exc}]",
                "tokens_generated": 0,
                "tokens_per_second": 0.0,
                "model": model or self.default_model,
                "latency_ms": (time.perf_counter() - t0) * 1000,
                "error": str(exc),
            }

    def list_models(self) -> list[CloudModelInfo]:
        """Fetch available models from the cloud API."""
        if self._available_models:
            return self._available_models

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = requests.get(
                f"{self.api_url}/models",
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for m in data.get("data", []):
                self._available_models.append(
                    CloudModelInfo(
                        model_id=m.get("id", ""),
                        quantization=m.get("quantization", "unknown"),
                        max_tokens=m.get("max_tokens", 4096),
                        supports_streaming=m.get("supports_streaming", False),
                    )
                )
        except Exception as exc:
            logger.warning("Failed to fetch cloud models: %s", exc)

        return self._available_models

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def compare_with_local(
        self,
        llm: Any,  # ROCmLLM
        prompt: str,
        *,
        system_prompt: str = "",
        max_tokens: int = 256,
    ) -> ComparisonResult:
        """
        Run the same prompt on local ROCm and cloud, compare results.

        Returns ComparisonResult with side-by-side metrics.
        """
        # Local inference
        t0 = time.perf_counter()
        local_result = llm.generate(
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )
        local_latency = (time.perf_counter() - t0) * 1000

        # Cloud inference
        cloud_result = self.generate(
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )

        speedup = (
            cloud_result["tokens_per_second"] / local_result.tokens_per_second
            if local_result.tokens_per_second > 0
            else 0.0
        )

        return ComparisonResult(
            prompt=prompt[:100],
            local_text=local_result.text[:500],
            local_tps=local_result.tokens_per_second,
            local_latency_ms=local_latency,
            cloud_text=cloud_result["text"][:500],
            cloud_tps=cloud_result["tokens_per_second"],
            cloud_latency_ms=cloud_result["latency_ms"],
            cloud_model=cloud_result["model"],
            speedup=speedup,
            quality_notes=self._assess_quality(local_result.text, cloud_result["text"]),
        )

    def compare_quantizations(
        self,
        prompt: str,
        *,
        quantizations: Optional[list[str]] = None,
        max_tokens: int = 256,
    ) -> list[dict[str, Any]]:
        """
        Compare inference across different quantization levels on the cloud.

        Args:
            prompt: The test prompt.
            quantizations: List of quantization levels to test (e.g., ["Q4_K_M", "Q8_0", "FP16"]).
            max_tokens: Max tokens per generation.

        Returns:
            List of dicts with quantization, tps, latency, and text for each level.
        """
        if quantizations is None:
            quantizations = ["Q4_K_M", "Q5_K_M", "Q8_0"]

        results: list[dict[str, Any]] = []

        for q in quantizations:
            model_name = f"{self.default_model}-{q.lower()}"
            logger.info("Testing quantization: %s", q)

            result = self.generate(
                prompt,
                model=model_name,
                max_tokens=max_tokens,
            )

            results.append(
                {
                    "quantization": q,
                    "model": model_name,
                    "tokens_per_second": result["tokens_per_second"],
                    "latency_ms": result["latency_ms"],
                    "tokens": result["tokens_generated"],
                    "text_preview": result["text"][:200],
                    "error": result.get("error"),
                }
            )

        return results

    # ------------------------------------------------------------------
    # Quality Assessment
    # ------------------------------------------------------------------

    @staticmethod
    def _assess_quality(local_text: str, cloud_text: str) -> str:
        """
        Basic quality comparison between local and cloud outputs.

        Checks: length similarity, keyword overlap, coherence markers.
        """
        if not local_text or not cloud_text:
            return "One or both outputs empty — cannot compare."

        notes = []

        # Length comparison
        len_ratio = len(cloud_text) / max(len(local_text), 1)
        if len_ratio < 0.5:
            notes.append("Cloud output significantly shorter")
        elif len_ratio > 2.0:
            notes.append("Cloud output significantly longer")

        # Keyword overlap
        local_words = set(local_text.lower().split())
        cloud_words = set(cloud_text.lower().split())
        if local_words and cloud_words:
            overlap = len(local_words & cloud_words) / len(local_words | cloud_words)
            if overlap < 0.1:
                notes.append(f"Low keyword overlap ({overlap:.0%}) — outputs may differ substantially")
            elif overlap > 0.5:
                notes.append(f"High keyword overlap ({overlap:.0%}) — outputs are similar")

        return "; ".join(notes) if notes else "Outputs appear comparable."

    # ------------------------------------------------------------------
    # Distillation Analysis (Bonus)
    # ------------------------------------------------------------------

    def analyze_distillation(
        self,
        teacher_model: str,
        student_model: str,
        test_prompts: list[str],
    ) -> dict[str, Any]:
        """
        Compare a large teacher model vs a distilled student model.

        Args:
            teacher_model: The larger/slower model ID.
            student_model: The distilled/faster model ID.
            test_prompts: List of prompts to test on both.

        Returns:
            Dict with per-prompt comparisons and aggregate metrics.
        """
        comparisons = []

        for prompt in test_prompts:
            teacher_result = self.generate(prompt, model=teacher_model, max_tokens=256)
            student_result = self.generate(prompt, model=student_model, max_tokens=256)

            comparisons.append(
                {
                    "prompt": prompt[:80],
                    "teacher_tps": teacher_result["tokens_per_second"],
                    "student_tps": student_result["tokens_per_second"],
                    "speedup": (
                        student_result["tokens_per_second"] / teacher_result["tokens_per_second"]
                        if teacher_result["tokens_per_second"] > 0
                        else 0
                    ),
                    "teacher_text": teacher_result["text"][:300],
                    "student_text": student_result["text"][:300],
                }
            )

        # Aggregate
        avg_speedup = sum(c["speedup"] for c in comparisons) / len(comparisons) if comparisons else 0
        avg_teacher_tps = sum(c["teacher_tps"] for c in comparisons) / len(comparisons) if comparisons else 0
        avg_student_tps = sum(c["student_tps"] for c in comparisons) / len(comparisons) if comparisons else 0

        return {
            "teacher_model": teacher_model,
            "student_model": student_model,
            "num_prompts": len(test_prompts),
            "avg_teacher_tps": avg_teacher_tps,
            "avg_student_tps": avg_student_tps,
            "avg_speedup": avg_speedup,
            "comparisons": comparisons,
        }
