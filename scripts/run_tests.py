"""Runs the client tests and the world tests.

The single test entry point for pre-commit, CI, and manual runs. The client
tests (protocol and bridge) need no Archipelago checkout and run from the repo
root. The world tests need the checkout (AP_ROOT override, else the sibling
directory), so the world package is linked into it and pytest runs from there.
"""

import subprocess
import sys

from ap_env import REPOSITORY_ROOT, WORLD_SOURCE, archipelago_root, link_world


def _run_client_tests() -> int:
    client_tests = REPOSITORY_ROOT / "client"
    if not client_tests.is_dir():
        return 0
    return subprocess.call(
        [sys.executable, "-m", "pytest", str(client_tests), "-q"],
        cwd=REPOSITORY_ROOT,
    )


def _run_world_tests() -> int:
    if not WORLD_SOURCE.is_dir():
        print(f"No world package at {WORLD_SOURCE} yet; skipping world tests.")
        return 0
    root = archipelago_root()
    if root is None:
        print("No Archipelago checkout found. Set AP_ROOT or clone 0.6.7 as a sibling directory.")
        return 1
    target = link_world(root)
    if target is None:
        return 1
    return subprocess.call(
        [sys.executable, "-m", "pytest", str(target / "test"), "-q"],
        cwd=root,
    )


def main() -> int:
    client_result = _run_client_tests()
    world_result = _run_world_tests()
    return client_result or world_result


if __name__ == "__main__":
    sys.exit(main())
