"""Headless C++ ASI to Python client interop check.

Starts the real Python AsiBridge, runs the compiled C++ harness against it as a
subprocess, and asserts the round trip: the harness receives the welcome, the
resync items and checked locations, and its emitted check reaches the bridge.
Windows and MSVC only (needs the built harness), so this is a dev-machine check,
not part of the ubuntu CI. Usage:
    python scripts/asi_interop_check.py <path-to-harness.exe>
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT / "client"))

from gta_vc_bridge import protocol  # noqa: E402
from gta_vc_bridge.bridge import AsiBridge  # noqa: E402

EXPECTED_HASH = "interophash01"
RESYNC_ITEMS = [(0, 111), (1, 222), (2, 333)]
RESYNC_CHECKED = [542000000, 542000001]
EMITTED_CHECK = 542000042


class Recorder:
    def __init__(self) -> None:
        self.checks: list[int] = []
        self.connected = 0

    def seed_hash(self) -> str:
        return EXPECTED_HASH

    async def on_check(self, location: int) -> None:
        self.checks.append(location)

    async def on_goal(self) -> None:
        pass

    async def on_connected(self, bridge: AsiBridge) -> None:
        self.connected += 1
        await bridge.send_items(RESYNC_ITEMS)
        await bridge.send_checked(RESYNC_CHECKED)


async def run(harness: str) -> int:
    recorder = Recorder()
    bridge = AsiBridge(
        "127.0.0.1", 0,
        expected_seed_hash=recorder.seed_hash,
        on_check=recorder.on_check,
        on_goal_reached=recorder.on_goal,
        on_connected=recorder.on_connected,
    )
    await bridge.start()
    process = await asyncio.create_subprocess_exec(
        harness,
        "--host", "127.0.0.1", "--port", str(bridge.port),
        "--seed-hash", "", "--emit-check", str(EMITTED_CHECK), "--run-ms", "1500",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
    except TimeoutError:
        process.kill()
        await process.wait()
        print("FAIL: the harness did not exit in time")
        return 1
    finally:
        await bridge.stop()

    summary_line = stdout.decode(errors="replace").strip().splitlines()
    summary = json.loads(summary_line[-1]) if summary_line else {}
    failures: list[str] = []
    if recorder.checks != [EMITTED_CHECK]:
        failures.append(f"bridge checks {recorder.checks} != [{EMITTED_CHECK}]")
    if summary.get("welcome_seed_hash") != EXPECTED_HASH:
        failures.append(f"welcome hash {summary.get('welcome_seed_hash')!r} != {EXPECTED_HASH!r}")
    if summary.get("items") != [list(pair) for pair in RESYNC_ITEMS]:
        failures.append(f"items {summary.get('items')} != {RESYNC_ITEMS}")
    if summary.get("checked") != RESYNC_CHECKED:
        failures.append(f"checked {summary.get('checked')} != {RESYNC_CHECKED}")

    if failures:
        print("FAIL: C++ ASI interop check")
        for failure in failures:
            print("  " + failure)
        print("harness stderr:\n" + stderr.decode(errors="replace"))
        return 1
    print("OK: C++ ASI interop check passed")
    print(f"  handshake used protocol version {protocol.PROTOCOL_VERSION}")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/asi_interop_check.py <path-to-harness.exe>")
        return 2
    return asyncio.run(run(sys.argv[1]))


if __name__ == "__main__":
    sys.exit(main())
