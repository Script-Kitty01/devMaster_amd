"""
ROCm LLM Service — Singleton wrapper around llama-cpp-python with HIP/ROCm GPU offloading.

Supports:
- Batched inference for multi-agent parallel queries
- Embedding generation via sentence-transformers on ROCm
- Fallback to CPU if GPU unavailable
- Optional Radeon Cloud API for bonus comparison benchmarks
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ensure CUDA runtime DLLs are discoverable by llama-cpp-python on Windows.
# nvidia-* wheels install DLLs under nvidia/cu*/bin/x86_64/ inside site-packages.
# ---------------------------------------------------------------------------
def _register_cuda_dll_paths() -> None:
    """Add nvidia CUDA & llama.cpp DLL directories to the DLL search path (Windows only)."""
    if sys.platform != "win32":
        return
    import site

    dll_dirs: list[str] = []

    for base in site.getsitepackages():
        # CUDA runtime DLLs from nvidia-* wheels
        nvidia_base = os.path.join(base, "nvidia")
        if os.path.isdir(nvidia_base):
            for entry in os.listdir(nvidia_base):
                pkg_dir = os.path.join(nvidia_base, entry)
                if not os.path.isdir(pkg_dir):
                    continue
                # Pattern 1: nvidia/<pkg>/bin/x86_64/  (cu13 packages)
                bin_x64 = os.path.join(pkg_dir, "bin", "x86_64")
                if os.path.isdir(bin_x64):
                    dll_dirs.append(bin_x64)
                # Pattern 2: nvidia/<pkg>/bin/  (cu12 packages)
                bin_dir = os.path.join(pkg_dir, "bin")
                if os.path.isdir(bin_dir) and bin_dir not in dll_dirs:
                    dll_dirs.append(bin_dir)

        # llama.cpp own DLLs
        llama_lib = os.path.join(base, "llama_cpp", "lib")
        if os.path.isdir(llama_lib):
            dll_dirs.append(llama_lib)

    # Register with os.add_dll_directory (Python 3.8+)
    for d in dll_dirs:
        try:
            os.add_dll_directory(d)
        except OSError:
            pass

    # Also prepend to PATH as a fallback for ctypes
    if dll_dirs:
        os.environ["PATH"] = ";".join(dll_dirs) + ";" + os.environ.get("PATH", "")


_register_cuda_dll_paths()


@dataclass
class LLMConfig:
    """Configuration for the ROCm LLM service."""

    model_path: str = "models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    embedding_model: str = "all-MiniLM-L6-v2"
    n_gpu_layers: int = -1  # -1 = all layers on GPU; 0 = CPU only
    n_ctx: int = 4096
    n_batch: int = 4
    temperature: float = 0.1
    max_tokens: int = 1024
    verbose: bool = False
    # Radeon Cloud API (bonus)
    cloud_api_url: str = ""
    cloud_api_key: str = ""


@dataclass
class InferenceResult:
    """Result from a single inference call."""

    text: str
    tokens_generated: int
    tokens_per_second: float
    model_name: str
    backend: str  # "rocm", "cpu", "cloud"


class ROCmLLM:
    """
    Singleton LLM service backed by llama-cpp-python with ROCm/HIP GPU acceleration.

    Usage:
        llm = ROCmLLM.get_instance()
        result = llm.generate("Explain this code...")
        embeddings = llm.embed(["def foo(): pass", "class Bar:"])
    """

    _instance: Optional["ROCmLLM"] = None
    _lock = threading.Lock()

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig()
        self._llm: Any = None
        self._embedder: Any = None
        self._backend: str = "cpu"
        self._initialized = False
        self._inference_lock = threading.Lock()  # serialize llama-cpp calls (not thread-safe)

    @classmethod
    def get_instance(cls, config: Optional[LLMConfig] = None) -> "ROCmLLM":
        """Return the singleton instance, creating it if needed."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (useful for testing)."""
        with cls._lock:
            cls._instance = None

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        """Load the GGUF model onto ROCm GPU (or CPU fallback). Returns True on success."""
        if self._initialized:
            return True

        try:
            from llama_cpp import Llama

            model_path = Path(self.config.model_path)
            if not model_path.exists():
                logger.warning(
                    "Model not found at %s. Download it first. Falling back to CPU mock.",
                    model_path,
                )
                self._backend = "cpu"
                self._initialized = True
                return False

            self._llm = Llama(
                model_path=str(model_path),
                n_gpu_layers=self.config.n_gpu_layers,
                n_ctx=self.config.n_ctx,
                n_batch=self.config.n_batch,
                n_threads=4,
                use_mmap=True,
                use_mlock=False,
                verbose=self.config.verbose,
            )
            self._backend = "rocm"
            logger.info("ROCm LLM initialized successfully on GPU.")
        except Exception as exc:
            logger.warning("Failed to load on ROCm GPU: %s. Using CPU fallback.", exc)
            self._backend = "cpu"
            try:
                from llama_cpp import Llama

                self._llm = Llama(
                    model_path=str(Path(self.config.model_path)),
                    n_gpu_layers=0,
                    n_ctx=self.config.n_ctx,
                    n_batch=self.config.n_batch,
                    n_threads=4,
                    use_mmap=True,
                    use_mlock=False,
                    verbose=self.config.verbose,
                )
            except Exception:
                logger.error("CPU fallback also failed. LLM will be unavailable.")
                self._llm = None

        self._initialized = True
        return self._llm is not None

    # ------------------------------------------------------------------
    # Text Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[list[str]] = None,
    ) -> InferenceResult:
        """Generate a completion for the given prompt."""
        if not self._initialized:
            self.initialize()

        if self._llm is None:
            return InferenceResult(
                text="[LLM unavailable — model not loaded]",
                tokens_generated=0,
                tokens_per_second=0.0,
                model_name=self.config.model_path,
                backend=self._backend,
            )

        import time

        full_prompt = prompt
        if system_prompt:
            full_prompt = (
                f"<|system|>\n{system_prompt}\n<|user|>\n{prompt}\n<|assistant|>"
            )

        temp = temperature if temperature is not None else self.config.temperature
        max_tok = max_tokens if max_tokens is not None else self.config.max_tokens

        t0 = time.perf_counter()
        with self._inference_lock:  # llama-cpp is NOT thread-safe
            output = self._llm(
                full_prompt,
                max_tokens=max_tok,
                temperature=temp,
                stop=stop or [],
                echo=False,
            )
        elapsed = time.perf_counter() - t0

        text = output["choices"][0]["text"]
        tokens = output.get("usage", {}).get("completion_tokens", len(text.split()))
        tps = tokens / elapsed if elapsed > 0 else 0.0

        return InferenceResult(
            text=text.strip(),
            tokens_generated=tokens,
            tokens_per_second=tps,
            model_name=self.config.model_path,
            backend=self._backend,
        )

    def generate_batch(
        self,
        prompts: list[str],
        *,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> list[InferenceResult]:
        """Generate completions for multiple prompts (sequential batching)."""
        return [
            self.generate(
                p,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            for p in prompts
        ]

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts using sentence-transformers."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._embedder = SentenceTransformer(
                    self.config.embedding_model,
                    device="cuda" if self._backend == "rocm" else "cpu",
                )
                logger.info(
                    "Embedding model '%s' loaded on %s.",
                    self.config.embedding_model,
                    "GPU" if self._backend == "rocm" else "CPU",
                )
            except Exception as exc:
                logger.error("Failed to load embedding model: %s", exc)
                return [[0.0] * 384 for _ in texts]

        embeddings = self._embedder.encode(texts, show_progress_bar=False)
        return embeddings.tolist()

    # ------------------------------------------------------------------
    # Cloud API (Bonus)
    # ------------------------------------------------------------------

    def generate_cloud(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> InferenceResult:
        """Generate via Radeon Cloud API for comparison benchmarks."""
        if not self.config.cloud_api_url:
            return InferenceResult(
                text="[Cloud API not configured]",
                tokens_generated=0,
                tokens_per_second=0.0,
                model_name="cloud",
                backend="cloud",
            )

        import time

        try:
            import requests

            temp = temperature if temperature is not None else self.config.temperature
            max_tok = max_tokens if max_tokens is not None else self.config.max_tokens

            t0 = time.perf_counter()
            resp = requests.post(
                self.config.cloud_api_url,
                json={
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "temperature": temp,
                    "max_tokens": max_tok,
                },
                headers={"Authorization": f"Bearer {self.config.cloud_api_key}"},
                timeout=120,
            )
            elapsed = time.perf_counter() - t0
            resp.raise_for_status()
            data = resp.json()
            text = data.get("text", "")
            tokens = data.get("tokens", len(text.split()))
            tps = tokens / elapsed if elapsed > 0 else 0.0

            return InferenceResult(
                text=text,
                tokens_generated=tokens,
                tokens_per_second=tps,
                model_name="radeon-cloud",
                backend="cloud",
            )
        except Exception as exc:
            logger.error("Cloud API call failed: %s", exc)
            return InferenceResult(
                text=f"[Cloud API error: {exc}]",
                tokens_generated=0,
                tokens_per_second=0.0,
                model_name="cloud",
                backend="cloud",
            )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def is_ready(self) -> bool:
        return self._initialized and self._llm is not None
