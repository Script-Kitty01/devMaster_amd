"""Headless snapshot check for KutaarConsole (no interactive TTY needed)."""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ui.console_tui import KutaarConsole


async def main() -> int:
    app = KutaarConsole()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause(1.5)
        for sel in ("#toollist", "#stream", "#ask", "#backend", "#model",
                    "#phases", "#chain", "#sys", "#agentstream", "#findings"):
            try:
                app.query_one(sel)
                print(f"OK {sel}")
            except Exception as exc:  # noqa: BLE001
                print(f"MISSING {sel}: {exc}")
                return 1
        print("SNAPSHOT_OK")
        return 0


raise SystemExit(asyncio.run(main()))
