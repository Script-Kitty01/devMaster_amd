"""
Kutaar Benchmark Dashboard — Streamlit page for ROCm GPU profiling,
inference speed comparison, and quantization benchmarks.
"""
from __future__ import annotations

import time
import streamlit as st
from dataclasses import dataclass, field
from typing import Any

st.set_page_config(page_title="Kutaar Benchmarks", page_icon="📊", layout="wide")

# ---------------------------------------------------------------------------
# Benchmark runner (inline to avoid import issues during startup)
# ---------------------------------------------------------------------------

BENCHMARK_PROMPTS = [
    ("Code Review", "Review this Python code for security issues:\n```python\ndef login(user, pw):\n    query = f\"SELECT * FROM users WHERE name='{user}' AND pass='{pw}'\"\n    return db.execute(query)\n```"),
    ("Architecture", "What design pattern would you recommend for a microservice that needs to fan-out work to 10 workers and aggregate results?"),
    ("Performance", "Analyze the time complexity of this function:\n```python\ndef find_pairs(arr, target):\n    for i in range(len(arr)):\n        for j in range(i+1, len(arr)):\n            if arr[i] + arr[j] == target:\n                return (i, j)\n    return None\n```"),
    ("DevOps", "What are the security risks in this Dockerfile?\n```dockerfile\nFROM python:3.12\nCOPY . /app\nRUN pip install -r requirements.txt\nUSER root\nCMD [\"python\", \"app.py\"]\n```"),
]


@dataclass
class BenchEntry:
    task: str
    tokens: int
    elapsed_ms: float
    tps: float


def run_benchmarks() -> list[BenchEntry]:
    """Run a lightweight benchmark suite using the local ROCm LLM."""
    results: list[BenchEntry] = []
    try:
        from src.llm.rocm_service import get_llm
        llm = get_llm()
    except Exception:
        st.warning("LLM not available — showing placeholder data")
        return _placeholder_results()

    for name, prompt in BENCHMARK_PROMPTS:
        t0 = time.perf_counter()
        try:
            output = llm.generate(prompt, max_tokens=128)
        except Exception:
            output = ""
        elapsed = (time.perf_counter() - t0) * 1000
        tokens = len(output.split()) if output else 0
        tps = tokens / (elapsed / 1000) if elapsed > 0 else 0
        results.append(BenchEntry(name, tokens, elapsed, tps))

    return results


def _placeholder_results() -> list[BenchEntry]:
    return [
        BenchEntry("Code Review", 85, 3200, 26.5),
        BenchEntry("Architecture", 92, 3400, 27.1),
        BenchEntry("Performance", 78, 2900, 26.9),
        BenchEntry("DevOps", 88, 3100, 28.4),
    ]


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("📊 Kutaar Benchmark Dashboard")
st.caption("AMD ROCm GPU Inference Performance")

col1, col2, col3, col4 = st.columns(4)

# GPU Info
with col1:
    st.metric("Backend", "ROCm/HIP", delta="AMD GPU")
with col2:
    st.metric("Model", "Llama 3.2 3B", delta="Q4_K_M")
with col3:
    st.metric("GPU Layers", "32/32", delta="Full offload")
with col4:
    st.metric("Context", "4096 tokens", delta="Default")

st.divider()

# Run benchmarks
if st.button("▶ Run Benchmarks", type="primary", use_container_width=True):
    with st.spinner("Running inference benchmarks on AMD ROCm GPU..."):
        results = run_benchmarks()

    st.subheader("Inference Speed by Task")
    cols = st.columns(len(results))
    for col, r in zip(cols, results):
        with col:
            st.metric(r.task, f"{r.tps:.1f} tok/s", delta=f"{r.tokens} tokens")

    st.divider()

    # Comparison table
    st.subheader("📋 Detailed Results")
    st.dataframe(
        {
            "Task": [r.task for r in results],
            "Tokens": [r.tokens for r in results],
            "Time (ms)": [f"{r.elapsed_ms:.0f}" for r in results],
            "Tokens/sec": [f"{r.tps:.1f}" for r in results],
        },
        use_container_width=True,
        hide_index=True,
    )

    # Average
    avg_tps = sum(r.tps for r in results) / len(results) if results else 0
    st.metric("Average Throughput", f"{avg_tps:.1f} tok/s")

else:
    st.info("Click **Run Benchmarks** to measure ROCm GPU inference performance.")

st.divider()

# Quantization comparison (bonus)
st.subheader("🔬 Quantization Comparison")
st.caption("Llama 3.2 3B — theoretical throughput on AMD Radeon GPU")

st.dataframe(
    {
        "Quantization": ["Q2_K", "Q3_K_M", "Q4_K_M ★", "Q5_K_M", "Q6_K", "Q8_0", "F16"],
        "Size (GB)": ["1.2", "1.5", "1.9", "2.2", "2.5", "3.3", "6.4"],
        "Est. tok/s": ["42", "35", "28", "22", "18", "12", "6"],
        "Quality": ["Low", "Fair", "Good", "Better", "Best", "Excellent", "Reference"],
    },
    use_container_width=True,
    hide_index=True,
)

st.caption("★ = currently deployed | Q4_K_M is the sweet spot for 6-8 GB VRAM GPUs")

# ROCm vs Cloud comparison
st.divider()
st.subheader("☁️ ROCm Local vs Radeon Cloud API")

col_a, col_b = st.columns(2)
with col_a:
    st.metric("Local ROCm", "~28 tok/s", delta="Llama 3.2 3B Q4_K_M")
    st.caption("Zero latency, no API costs")
with col_b:
    st.metric("Radeon Cloud API", "~45 tok/s", delta="Larger model possible")
    st.caption("Higher throughput, pay-per-use")
