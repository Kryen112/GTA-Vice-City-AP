"""Runs the world and client tests against a real Archipelago checkout.

The single test entry point for pre-commit, CI, and manual runs. Locates the
Archipelago checkout (AP_ROOT override, else the sibling directory), links the
world package into it, and runs pytest over the world tests and the bundled
client tests (the client is a subpackage of the world).
"""

import subprocess
import sys

from ap_env import REPOSITORY_ROOT, WORLD_SOURCE, archipelago_root, link_world


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
    failed = subprocess.call(
        [sys.executable, "-m", "pytest", str(target / "test"), str(target / "client" / "test"), "-q"],
        cwd=root,
    )
    if failed:
        return failed
    return _run_spec_dumper()


def _run_spec_dumper() -> int:
    """Runs scripts/dump_scm_spec.py and requires it to succeed.

    The dumper is the only thing that reads the world tables the way the SCM
    build reads them, so it is what catches a gate table drifting from
    rules.py. Nothing else imports it, so a signature change in rules.py rots
    it unnoticed; running it here makes that a test failure. Output is dropped
    unless it fails, since the spec itself is for humans at the keyboard.
    """
    completed = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / "dump_scm_spec.py")],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
    )
    if completed.returncode:
        print("scripts/dump_scm_spec.py failed:")
        print(completed.stdout[-2000:])
        print(completed.stderr[-2000:])
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
