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
import json
import hashlib
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


# ---------------------------------------------------------------------------
# Verified runtime detection (plan.md Phase 3 items 3 & 6)
#
# The reported backend must be the runtime that is actually loaded, never a
# guess based on the class name or on the requested layer count.
# ---------------------------------------------------------------------------

_GPU_BACKEND_LIBRARIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rocm", ("libggml-hip.so", "libggml-hip.dylib", "ggml-hip.dll", "ggml-hip.so")),
    ("cuda", ("libggml-cuda.so", "libggml-cuda.dylib", "ggml-cuda.dll", "ggml-cuda.so")),
    ("vulkan", ("libggml-vulkan.so", "ggml-vulkan.dll", "ggml-vulkan.so")),
)


def _llama_cpp_lib_dir() -> Optional[Path]:
    """Directory holding the shared libraries shipped with llama-cpp-python."""
    try:
        import llama_cpp
    except Exception:  # noqa: BLE001 - any import failure means "unknown runtime"
        return None

    package_dir = Path(getattr(llama_cpp, "__file__", "") or "").parent
    lib_dir = package_dir / "lib"
    return lib_dir if lib_dir.is_dir() else None


def detect_llama_cpp_runtime() -> dict[str, Any]:
    """Detect the ggml backend the installed llama.cpp build actually provides.

    Evidence comes from:

    1. the backend libraries shipped next to the ``llama_cpp`` package
       (``libggml-hip.so`` for HIP/ROCm, ``ggml-cuda.dll`` for CUDA, ...); and
    2. Torch's device metadata, which describes what the host exposes.

    Returns ``runtime`` as ``rocm`` | ``cuda`` | ``vulkan`` | ``cpu`` | ``unknown``
    plus the library path, human-readable evidence, GPU name and HIP version.
    """
    info: dict[str, Any] = {
        "runtime": "unknown",
        "library": "",
        "evidence": "",
        "gpu_name": "",
        "hip_version": "",
        "torch_cuda_available": False,
    }

    lib_dir = _llama_cpp_lib_dir()
    if lib_dir is None:
        info["evidence"] = "llama_cpp is not importable or ships no lib directory"
    else:
        for runtime, names in _GPU_BACKEND_LIBRARIES:
            for name in names:
                library = lib_dir / name
                if library.exists():
                    info["runtime"] = runtime
                    info["library"] = str(library)
                    info["evidence"] = f"found {name} next to the llama_cpp package"
                    break
            if info["library"]:
                break

        if not info["library"]:
            info["runtime"] = "cpu"
            info["evidence"] = (
                f"no HIP/CUDA ggml backend library in {lib_dir} (CPU-only llama.cpp build)"
            )

    # Host-level device evidence (secondary — the llama.cpp build is authoritative).
    try:
        import torch

        info["hip_version"] = str(getattr(torch.version, "hip", "") or "")
        info["torch_cuda_available"] = bool(torch.cuda.is_available())
        if info["torch_cuda_available"]:
            try:
                info["gpu_name"] = str(torch.cuda.get_device_name(0))
            except Exception:  # noqa: BLE001
                info["gpu_name"] = ""
    except Exception:  # noqa: BLE001
        info["hip_version"] = ""

    return info


@dataclass
class LLMConfig:
    """Configuration for the ROCm LLM service.

    All fields can be overridden with environment variables (see from_env).
    """

    model_path: str = "gemma2:2b"
    backend: str = "ollama"  # ollama or llama_cpp
    ollama_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "all-MiniLM-L6-v2"
    n_gpu_layers: int = -1  # -1 = all layers on GPU; 0 = CPU only
    n_ctx: int = 4096
    n_batch: int = 4
    temperature: float = 0.1
    max_tokens: int = 1024
    verbose: bool = False
    allow_cpu_fallback: bool = True
    # Radeon Cloud API (bonus)
    cloud_api_url: str = ""
    cloud_api_key: str = ""

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Build a config from KUTAAR_* environment variables.

        - KUTAAR_LLM_BACKEND: 'ollama' (default) or 'llama_cpp'
        - KUTAAR_MODEL: Ollama model tag (ollama) or path to a .gguf file (llama_cpp)
        - KUTAAR_OLLAMA_URL: Ollama server URL
        - KUTAAR_EMBEDDING_MODEL: sentence-transformers model name
        - KUTAAR_GPU_LAYERS: -1 (all on GPU) or 0 (CPU only)
        - KUTAAR_MAX_TOKENS / KUTAAR_TEMPERATURE: generation defaults
        - KUTAAR_ALLOW_CPU_FALLBACK: 1/0 — when 0, llama_cpp mode fails hard
          instead of silently falling back to CPU
        """
        backend = os.environ.get("KUTAAR_LLM_BACKEND", "ollama").strip().lower()
        default_model = "gemma2:2b" if backend == "ollama" else "models/model.gguf"
        allow_fallback = os.environ.get("KUTAAR_ALLOW_CPU_FALLBACK", "1").strip() not in ("0", "false", "no")
        return cls(
            model_path=os.environ.get("KUTAAR_MODEL", default_model),
            backend=backend,
            ollama_url=os.environ.get("KUTAAR_OLLAMA_URL", "http://127.0.0.1:11434"),
            embedding_model=os.environ.get("KUTAAR_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            n_gpu_layers=int(os.environ.get("KUTAAR_GPU_LAYERS", "-1")),
            temperature=float(os.environ.get("KUTAAR_TEMPERATURE", "0.1")),
            max_tokens=int(os.environ.get("KUTAAR_MAX_TOKENS", "1024")),
            verbose=os.environ.get("KUTAAR_VERBOSE", "0").strip() not in ("0", "false", "no"),
            allow_cpu_fallback=allow_fallback,
        )


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
        self.config = config or LLMConfig.from_env()
        self._llm: Any = None
        self._embedder: Any = None
        self._backend: str = "cpu"
        self._fallback_reason: str = ""
        self._initialized = False
        self._runtime_info: dict[str, Any] = {}
        self._embedding_unavailable = False
        self._embedding_device: str = "not-loaded"
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

        if self.config.backend == "ollama":
            try:
                import urllib.request

                with urllib.request.urlopen(
                    f"{self.config.ollama_url.rstrip('/')}/api/tags", timeout=5
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                models = {item.get("name") for item in payload.get("models", [])}
                if self.config.model_path not in models:
                    self._fallback_reason = (
                        f"Ollama model '{self.config.model_path}' is not installed. "
                        f"Run: ollama pull {self.config.model_path}"
                    )
                    logger.error(self._fallback_reason)
                    self._backend = "ollama"
                    self._initialized = True
                    return False
                self._backend = "ollama"
                self._llm = True
                self._initialized = True
                logger.info("Ollama LLM initialized: %s", self.config.model_path)
                return True
            except Exception as exc:
                self._fallback_reason = (
                    f"Ollama server unreachable at {self.config.ollama_url}: {exc}"
                )
                logger.warning("Ollama initialization failed: %s", exc)
                self._backend = "ollama"
                self._initialized = True
                return False

        # ---- llama_cpp backend (ROCm/HIP when built with GGML_HIP=ON) ----
        model_path = Path(self.config.model_path)
        if not model_path.exists():
            self._fallback_reason = (
                f"Model file not found: {model_path}. "
                "Set KUTAAR_MODEL to a valid .gguf path."
            )
            logger.warning(self._fallback_reason)
            if not self.config.allow_cpu_fallback:
                logger.error("CPU fallback disabled (KUTAAR_ALLOW_CPU_FALLBACK=0). Failing hard.")
                self._backend = "cpu"
                self._initialized = True
                return False
            self._backend = "cpu"
            self._initialized = True
            return False

        # Verify the actual ggml backend before claiming a GPU runtime
        # (plan.md Phase 3 item 3).
        self._runtime_info = detect_llama_cpp_runtime()
        gpu_runtime = str(self._runtime_info.get("runtime", "unknown"))
        gpu_build_available = gpu_runtime in ("rocm", "cuda", "vulkan")
        wants_gpu = self.config.n_gpu_layers != 0
        runtime_evidence = str(self._runtime_info.get("evidence", ""))

        if wants_gpu and not gpu_build_available:
            self._fallback_reason = (
                f"GPU offload requested (n_gpu_layers={self.config.n_gpu_layers}) but the "
                f"installed llama.cpp build has no GPU backend: {runtime_evidence}. "
                "Rebuild with GGML_HIP=ON (scripts/build_llama_cpp_hip.sh) to use ROCm."
            )
            if not self.config.allow_cpu_fallback:
                logger.error(
                    "%s CPU fallback disabled (KUTAAR_ALLOW_CPU_FALLBACK=0). Failing hard.",
                    self._fallback_reason,
                )
                self._backend = "cpu"
                self._initialized = True
                return False
            logger.warning(self._fallback_reason)

        # Never request GPU layers from a CPU-only build.
        effective_gpu_layers = self.config.n_gpu_layers if gpu_build_available else 0

        try:
            from llama_cpp import Llama

            self._llm = Llama(
                model_path=str(model_path),
                n_gpu_layers=effective_gpu_layers,
                n_ctx=self.config.n_ctx,
                n_batch=self.config.n_batch,
                n_threads=4,
                use_mmap=True,
                use_mlock=False,
                verbose=self.config.verbose,
            )
            if gpu_build_available and wants_gpu:
                self._backend = gpu_runtime
                logger.info(
                    "llama.cpp initialized on %s (verified by %s).",
                    gpu_runtime.upper(),
                    self._runtime_info.get("library") or runtime_evidence,
                )
            else:
                self._backend = "cpu"
                logger.info(
                    "llama-cpp LLM initialized on CPU (no GPU offload requested or available)."
                )
        except Exception as exc:
            self._fallback_reason = f"Failed to load on GPU: {exc}"
            logger.warning("%s. Using CPU fallback.", self._fallback_reason)
            if not self.config.allow_cpu_fallback:
                logger.error("CPU fallback disabled (KUTAAR_ALLOW_CPU_FALLBACK=0). Failing hard.")
                self._backend = "cpu"
                self._llm = None
                self._initialized = True
                return False
            self._backend = "cpu"
            try:
                from llama_cpp import Llama

                self._llm = Llama(
                    model_path=str(model_path),
                    n_gpu_layers=0,
                    n_ctx=self.config.n_ctx,
                    n_batch=self.config.n_batch,
                    n_threads=4,
                    use_mmap=True,
                    use_mlock=False,
                    verbose=self.config.verbose,
                )
            except Exception as cpu_exc:
                self._fallback_reason = f"GPU load failed ({exc}); CPU fallback also failed ({cpu_exc})"
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
        if self._backend == "ollama":
            try:
                import urllib.request

                payload = json.dumps(
                    {
                        "model": self.config.model_path,
                        "prompt": prompt,
                        "system": system_prompt,
                        "stream": False,
                        "options": {
                            "temperature": temp,
                            "num_predict": max_tok,
                        },
                    }
                ).encode("utf-8")
                request = urllib.request.Request(
                    f"{self.config.ollama_url.rstrip('/')}/api/generate",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self._inference_lock, urllib.request.urlopen(request, timeout=600) as response:
                    output = json.loads(response.read().decode("utf-8"))
                elapsed = time.perf_counter() - t0
                text = output.get("response", "")
                tokens = int(output.get("eval_count", len(text.split())))
                tps = tokens / elapsed if elapsed > 0 else 0.0
                return InferenceResult(
                    text=text.strip(),
                    tokens_generated=tokens,
                    tokens_per_second=tps,
                    model_name=self.config.model_path,
                    backend="ollama",
                )
            except Exception as exc:
                logger.error("Ollama generation failed: %s", exc)
                return InferenceResult(
                    text=f"[Ollama error: {exc}]",
                    tokens_generated=0,
                    tokens_per_second=0.0,
                    model_name=self.config.model_path,
                    backend="ollama",
                )

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
        if self._embedding_unavailable:
            return self._fallback_embeddings(texts)

        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer

                device = "cuda" if self._backend == "rocm" else "cpu"
                self._embedder = SentenceTransformer(
                    self.config.embedding_model,
                    device=device,
                    local_files_only=True,
                )
                self._embedding_device = device
                logger.info(
                    "Embedding model '%s' loaded on %s.",
                    self.config.embedding_model,
                    "GPU (ROCm)" if device == "cuda" else "CPU",
                )
            except Exception as exc:
                logger.error("Failed to load embedding model: %s", exc)
                self._embedding_unavailable = True
                self._embedding_device = "unavailable"
                return self._fallback_embeddings(texts)

        embeddings = self._embedder.encode(texts, show_progress_bar=False)
        return embeddings.tolist()

    @staticmethod
    def _fallback_embeddings(texts: list[str], dimensions: int = 384) -> list[list[float]]:
        """Create stable local vectors when the optional embedding model is unavailable."""
        vectors = []
        for text in texts:
            vector = [0.0] * dimensions
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            for index, byte in enumerate(digest):
                vector[index % dimensions] += (byte / 255.0) * 2.0 - 1.0
            vectors.append(vector)
        return vectors

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
    def fallback_reason(self) -> str:
        """Why the LLM is not on the requested backend (empty when healthy)."""
        return self._fallback_reason

    @property
    def is_ready(self) -> bool:
        return self._initialized and self._llm is not None

    def _backend_is_verified(self) -> bool:
        """True only when the reported backend matches observed runtime evidence.

        A ROCm/CUDA claim requires the matching ggml backend library; Ollama and
        CPU states are verified by a successful health check / model load.
        """
        if self._backend in ("rocm", "cuda", "vulkan"):
            return bool(self._runtime_info.get("library"))
        if self._backend == "ollama":
            return bool(self._initialized and self._llm is not None and not self._fallback_reason)
        return bool(self._initialized and self._llm is not None)

    def diagnostics(self) -> dict[str, Any]:
        """Runtime diagnostics for truthful status reporting (plan.md Phase 3)."""
        runtime = self._runtime_info or {}
        return {
            "configured_backend": self.config.backend,
            "active_backend": self._backend,
            "backend_verified": self._backend_is_verified(),
            "model": self.config.model_path,
            "n_gpu_layers": self.config.n_gpu_layers,
            "gpu_offload_layers": self.config.n_gpu_layers,
            "runtime": runtime.get("runtime", "not-checked"),
            "runtime_evidence": runtime.get("evidence", ""),
            "gpu_backend_library": runtime.get("library", ""),
            "detected_gpu": runtime.get("gpu_name", ""),
            "hip_version": runtime.get("hip_version", ""),
            "ready": self.is_ready,
            "fallback_reason": self._fallback_reason,
            "cpu_fallback_allowed": self.config.allow_cpu_fallback,
            "embedding_model": self.config.embedding_model,
            "embedding_device": self._embedding_device,
            "embedding_unavailable": self._embedding_unavailable,
            "ollama_url": self.config.ollama_url if self.config.backend == "ollama" else "",
        }

    def status_line(self) -> str:
        """One-line, truthful status shared by both UIs (plan.md Phase 5 item 3)."""
        diag = self.diagnostics()
        verified = "" if diag["backend_verified"] else " (unverified)"
        parts = [
            f"backend={diag['active_backend']}{verified}",
            f"model={Path(str(diag['model'])).name}",
            f"gpu_layers={diag['gpu_offload_layers']}",
        ]
        if diag["runtime"] not in ("", "not-checked"):
            parts.append(f"runtime={diag['runtime']}")
        if diag["detected_gpu"]:
            parts.append(f"gpu={diag['detected_gpu']}")
        if diag["hip_version"]:
            parts.append(f"hip={diag['hip_version']}")
        if diag["embedding_device"] not in ("", "not-loaded"):
            parts.append(f"embeddings={diag['embedding_device']}")
        if diag["fallback_reason"]:
            parts.append(f"fallback_reason={diag['fallback_reason']}")
        return " | ".join(parts)
