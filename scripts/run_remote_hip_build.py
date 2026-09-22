"""
Drive the remote Radeon Linux instance to do Phase 1 verify + Phase 2 HIP build.
Uses the existing Anrui websocket/ssh tunnel helpers in the workspace.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = os.environ.get("ANRUI_BASE", "https://radeon-global.anruicloud.com/instances/u-14073-bcd85560")
TOKEN = os.environ.get("ANRUI_TOKEN", os.environ.get("amd-oneclick", ""))


def _request(path: str, payload: dict | None = None, method: str = "GET") -> dict:
    url = f"{BASE.rstrip('/')}/{path.lstrip('/')}"
    headers = {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)  # type: ignore[arg-type]
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    print("This helper drives the remote ROCm host to execute:")
    print("  1. scripts/verify_rocm_host.py")
    print("  2. scripts/build_llama_cpp_hip.sh")
    print("Configure ANRUI_BASE/ANRUI_TOKEN env vars, or use the existing tunnel.")
    print(f"BASE = {BASE}")
    print(f"TOKEN = {'set' if TOKEN else 'NOT SET'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
