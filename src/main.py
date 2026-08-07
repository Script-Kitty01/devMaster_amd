"""
Kutaar — Main Entry Point

Usage:
    # Launch the Streamlit UI
    python -m src.main

    # Or via streamlit directly:
    streamlit run src/ui/chat_app.py

    # Run benchmarks only:
    python -m src.main --benchmark
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for Kutaar."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def run_benchmarks() -> None:
    """Run the ROCm benchmark suite and print results."""
    from src.llm.rocm_service import ROCmLLM, LLMConfig
    from src.benchmarks.rocm_profiler import ROCmProfiler

    print("=" * 60)
    print("  Kutaar — ROCm Benchmark Suite")
    print("=" * 60)

    config = LLMConfig()
    llm = ROCmLLM.get_instance(config)
    llm.initialize()

    profiler = ROCmProfiler(llm)

    print("\nRunning benchmarks (5 prompts, local ROCm + Cloud if configured)...")
    results = profiler.run_benchmark_suite()

    print(profiler.print_report(results))

    # Save to file
    report_path = Path("benchmark_report.json")
    report_path.write_text(profiler.to_json(results))
    print(f"\nDetailed report saved to: {report_path}")


def run_ui() -> None:
    """Launch the Streamlit UI."""
    import subprocess

    ui_path = Path(__file__).resolve().parent / "ui" / "chat_app.py"
    print(f"Launching Kutaar UI from: {ui_path}")
    subprocess.run(
        ["streamlit", "run", str(ui_path)],
        check=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kutaar — Multi-Agent Engineering Assistant powered by AMD ROCm",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run the ROCm benchmark suite instead of the UI",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level",
    )
    parser.add_argument(
        "--model-path",
        default="models/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        help="Path to GGUF model file",
    )
    parser.add_argument(
        "--cloud-api-url",
        default="",
        help="Radeon Cloud API URL (for bonus comparison)",
    )
    parser.add_argument(
        "--cloud-api-key",
        default="",
        help="Radeon Cloud API key",
    )

    args = parser.parse_args()
    setup_logging(args.log_level)

    # Configure LLM if custom model path
    if args.model_path or args.cloud_api_url:
        from src.llm.rocm_service import ROCmLLM, LLMConfig

        config = LLMConfig(
            model_path=args.model_path,
            cloud_api_url=args.cloud_api_url,
            cloud_api_key=args.cloud_api_key,
        )
        ROCmLLM.get_instance(config)

    if args.benchmark:
        run_benchmarks()
    else:
        run_ui()


if __name__ == "__main__":
    main()
