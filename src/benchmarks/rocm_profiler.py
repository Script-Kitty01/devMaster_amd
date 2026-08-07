"""
ROCm Profiler & Benchmarking — measures inference speed, GPU utilization,
and compares local ROCm vs Radeon Cloud API performance.

Bonus: Quantization/distillation comparison for AMD Radeon cloud model.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.llm.rocm_service import ROCmLLM, InferenceResult

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    model_name: str
    backend: str  # "rocm", "cpu", "cloud"
    prompt: str
    tokens_generated: int
    elapsed_ms: float
    tokens_per_second: float
    gpu_utilization_pct: float = 0.0
    gpu_memory_mb: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class ROCmProfiler:
    """
    Profiles ROCm GPU performance and compares inference backends.

    Usage:
        profiler = ROCmProfiler(llm)
        results = profiler.run_benchmark_suite()
        profiler.print_report(results)
    """

    def __init__(self, llm: ROCmLLM) -> None:
        self.llm = llm

    # ------------------------------------------------------------------
    # GPU Metrics
    # ------------------------------------------------------------------

    def get_gpu_metrics(self) -> dict[str, float]:
        """
        Query ROCm GPU metrics via rocminfo/rocm-smi.

        Returns dict with utilization_pct, memory_used_mb, memory_total_mb.
        """
        metrics: dict[str, float] = {
            "utilization_pct": 0.0,
            "memory_used_mb": 0.0,
            "memory_total_mb": 0.0,
        }

        try:
            # Try rocm-smi for GPU utilization
            result = subprocess.run(
                ["rocm-smi", "--showuse", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                for card_id, card_data in data.items():
                    metrics["utilization_pct"] = float(
                        card_data.get("GPU use (%)", "0").replace("%", "")
                    )
                    # Memory info
                    if "VRAM" in card_data:
                        vram = card_data["VRAM"]
                        used = float(str(vram.get("Total Used Memory (B)", "0")))
                        total = float(str(vram.get("Total Memory (B)", "0")))
                        metrics["memory_used_mb"] = used / (1024 * 1024)
                        metrics["memory_total_mb"] = total / (1024 * 1024)
                    break  # First GPU only
        except FileNotFoundError:
            logger.debug("rocm-smi not found — skipping GPU metrics.")
        except Exception as exc:
            logger.debug("Failed to get GPU metrics: %s", exc)

        return metrics

    # ------------------------------------------------------------------
    # Benchmark Suite
    # ------------------------------------------------------------------

    def run_benchmark_suite(
        self,
        prompts: Optional[list[str]] = None,
    ) -> list[BenchmarkResult]:
        """
        Run a suite of benchmarks comparing ROCm local vs Cloud API.

        Returns list of BenchmarkResult for each prompt/backend combination.
        """
        if prompts is None:
            prompts = [
                "Explain the concept of dependency injection in 3 sentences.",
                "Write a Python function to find all prime numbers up to N using the Sieve of Eratosthenes.",
                "What are the OWASP Top 10 vulnerabilities? List them briefly.",
                "Explain the difference between Docker and Kubernetes.",
                "Write a SQL query to find duplicate records in a table.",
            ]

        results: list[BenchmarkResult] = []

        for prompt in prompts:
            # Local ROCm
            gpu_before = self.get_gpu_metrics()
            t0 = time.perf_counter()
            result = self.llm.generate(prompt, max_tokens=256)
            elapsed = (time.perf_counter() - t0) * 1000
            gpu_after = self.get_gpu_metrics()

            results.append(
                BenchmarkResult(
                    model_name=result.model_name,
                    backend=result.backend,
                    prompt=prompt[:80],
                    tokens_generated=result.tokens_generated,
                    elapsed_ms=elapsed,
                    tokens_per_second=result.tokens_per_second,
                    gpu_utilization_pct=gpu_after.get("utilization_pct", 0.0),
                    gpu_memory_mb=gpu_after.get("memory_used_mb", 0.0),
                )
            )

            # Cloud API (if configured)
            if self.llm.config.cloud_api_url:
                t0 = time.perf_counter()
                cloud_result = self.llm.generate_cloud(prompt, max_tokens=256)
                cloud_elapsed = (time.perf_counter() - t0) * 1000

                results.append(
                    BenchmarkResult(
                        model_name=cloud_result.model_name,
                        backend="cloud",
                        prompt=prompt[:80],
                        tokens_generated=cloud_result.tokens_generated,
                        elapsed_ms=cloud_elapsed,
                        tokens_per_second=cloud_result.tokens_per_second,
                    )
                )

        return results

    # ------------------------------------------------------------------
    # Quantization Comparison (Bonus)
    # ------------------------------------------------------------------

    def compare_quantizations(
        self,
        prompt: str = "Write a Python function to reverse a linked list.",
    ) -> list[dict[str, Any]]:
        """
        Compare inference quality/speed across quantization levels.

        Note: Requires multiple GGUF model files at different quantizations.
        This is a framework — actual comparison needs the model files.
        """
        quantizations = ["Q4_K_M", "Q5_K_M", "Q8_0"]
        results: list[dict[str, Any]] = []

        for q in quantizations:
            # This would require loading different model files
            # For now, record the framework
            results.append(
                {
                    "quantization": q,
                    "status": "requires_model_file",
                    "note": f"Need GGUF model at {q} quantization for comparison",
                }
            )

        return results

    # ------------------------------------------------------------------
    # Report Generation
    # ------------------------------------------------------------------

    def print_report(self, results: list[BenchmarkResult]) -> str:
        """Generate a formatted benchmark report."""
        lines = [
            "=" * 60,
            "  Kutaar ROCm Benchmark Report",
            "=" * 60,
        ]

        # Group by backend
        rocm_results = [r for r in results if r.backend == "rocm"]
        cloud_results = [r for r in results if r.backend == "cloud"]
        cpu_results = [r for r in results if r.backend == "cpu"]

        for label, group in [("ROCm GPU (Local)", rocm_results), ("Radeon Cloud API", cloud_results), ("CPU Fallback", cpu_results)]:
            if not group:
                continue

            avg_tps = sum(r.tokens_per_second for r in group) / len(group)
            avg_latency = sum(r.elapsed_ms for r in group) / len(group)
            total_tokens = sum(r.tokens_generated for r in group)

            lines.extend([
                f"\n--- {label} ---",
                f"  Runs: {len(group)}",
                f"  Avg tokens/sec: {avg_tps:.1f}",
                f"  Avg latency: {avg_latency:.0f} ms",
                f"  Total tokens: {total_tokens}",
            ])

            if group and group[0].gpu_utilization_pct > 0:
                lines.append(f"  GPU Utilization: {group[0].gpu_utilization_pct:.1f}%")
                lines.append(f"  GPU Memory: {group[0].gpu_memory_mb:.0f} MB")

        # Comparison
        if rocm_results and cloud_results:
            rocm_avg = sum(r.tokens_per_second for r in rocm_results) / len(rocm_results)
            cloud_avg = sum(r.tokens_per_second for r in cloud_results) / len(cloud_results)
            speedup = cloud_avg / rocm_avg if rocm_avg > 0 else 0
            lines.extend([
                f"\n--- Comparison ---",
                f"  ROCm Local: {rocm_avg:.1f} tok/s",
                f"  Cloud API:  {cloud_avg:.1f} tok/s",
                f"  Speedup:    {speedup:.2f}x",
            ])

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

    def to_json(self, results: list[BenchmarkResult]) -> str:
        """Export benchmark results as JSON."""
        return json.dumps(
            [
                {
                    "model": r.model_name,
                    "backend": r.backend,
                    "prompt": r.prompt,
                    "tokens": r.tokens_generated,
                    "elapsed_ms": r.elapsed_ms,
                    "tokens_per_second": r.tokens_per_second,
                    "gpu_utilization_pct": r.gpu_utilization_pct,
                    "gpu_memory_mb": r.gpu_memory_mb,
                }
                for r in results
            ],
            indent=2,
        )
