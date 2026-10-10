"""
Phase 1/2 helper — verify a Linux ROCm host before attempting the HIP build.
Run this on the target ROCm machine (or via the remote terminal). It exits 0
if the host is ready to build llama-cpp-python with HIP, non-zero otherwise.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


def run(cmd: list[str]) -> tuple[bool, str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return out.returncode == 0, (out.stdout or "") + (out.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main() -> int:
    report: dict[str, Any] = {}

    ok, rocm_info = run(["rocminfo"])
    report["rocminfo"] = {"ok": ok, "output": rocm_info.splitlines()[:20]}

    ok, smi_info = run(["rocm-smi", "--showid"])
    report["rocm_smi"] = {"ok": ok, "output": smi_info.splitlines()[:10]}

    hipcc = shutil.which("hipcc")
    report["hipcc"] = {"ok": hipcc is not None, "path": hipcc or ""}

    # Attempt to infer a sensible AMDGPU_TARGETS from rocminfo Name lines.
    targets: list[str] = []
    for line in rocm_info.splitlines():
        if "Name:" in line and "gfx" in line:
            parts = line.split()
            for p in parts:
                if p.startswith("gfx"):
                    targets.append(p.strip())
    report["suggested_amdgpu_targets"] = targets

    # Python-level HIP check if torch is installed.
    try:
        import torch

        report["torch_version"] = torch.__version__
        report["torch_cuda_available"] = torch.cuda.is_available()
        report["torch_hip_available"] = hasattr(torch, "_HIP_VERSION")
    except ImportError:
        report["torch_version"] = "not installed"

    print(json.dumps(report, indent=2))

    if not all((report["rocminfo"]["ok"], report["rocm_smi"]["ok"], report["hipcc"]["ok"])):
        print("\nROCm host verification FAILED", file=sys.stderr)
        return 1
    print("\nROCm host verification PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
