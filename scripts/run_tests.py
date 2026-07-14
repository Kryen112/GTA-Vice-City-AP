"""Runs the world and client tests against a real Archipelago checkout.

The single test entry point for pre-commit, CI, and manual runs. Locates the
Archipelago checkout (AP_ROOT override, else the sibling directory), links the
world package into it, and runs pytest over the world tests and the bundled
client tests (the client is a subpackage of the world).
"""

import subprocess
import sys

from ap_env import WORLD_SOURCE, archipelago_root, link_world


def main() -> int:
    if not WORLD_SOURCE.is_dir():
        print(f"No world package at {WORLD_SOURCE} yet; nothing to test.")
        return 0
    root = archipelago_root()
    if root is None:
        print("No Archipelago checkout found. Set AP_ROOT or clone 0.6.7 as a sibling directory.")
        return 1
    target = link_world(root)
    if target is None:
        return 1
    return subprocess.call(
        [sys.executable, "-m", "pytest", str(target / "test"), str(target / "client" / "test"), "-q"],
        cwd=root,
    )


if __name__ == "__main__":
    sys.exit(main())
