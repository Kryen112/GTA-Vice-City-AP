"""Runs the world and setup tests against a real Archipelago checkout.

The single test entry point for pre-commit, CI, and manual runs. Locates the
Archipelago checkout (AP_ROOT override, else the nearest one up the tree), links the
world package into it, and runs pytest over the world, setup, and build tests.
"""

import subprocess
import sys

from ap_env import REPOSITORY_ROOT, WORLD_SOURCE, archipelago_root, link_world, missing_checkout_message


def main() -> int:
    if not WORLD_SOURCE.is_dir():
        print(f"No world package at {WORLD_SOURCE} yet; nothing to test.")
        return 0
    root = archipelago_root()
    if root is None:
        print(missing_checkout_message())
        return 1
    target = link_world(root)
    if target is None:
        return 1
    failed = subprocess.call(
        [sys.executable, "-m", "pytest", str(target / "test"),
         str(REPOSITORY_ROOT / "scripts" / "test"), "-q"],
        cwd=root,
    )
    if failed:
        return failed
    failed = _run_spec_dumper()
    if failed:
        return failed
    failed = _run_helper("check_scm_mirrors.py")
    if failed:
        return failed
    # Exercise the native APCpp transport when its harness has been built.
    return _run_interop_check()


def _run_spec_dumper() -> int:
    """Runs scripts/dump_scm_spec.py and requires it to succeed.

    The dumper is the only thing that reads the world tables the way the SCM
    build reads them, so it is what catches a gate table drifting from
    rules.py. Nothing else imports it, so a signature change in rules.py rots
    it unnoticed; running it here makes that a test failure. Output is dropped
    unless it fails, since the spec itself is for humans at the keyboard.
    """
    return _run_helper("dump_scm_spec.py")


def _run_interop_check() -> int:
    """Runs scripts/native_interop_check.py when its harness binary is around."""
    candidates = sorted(REPOSITORY_ROOT.glob("**/native_harness.exe"))
    if not candidates:
        print("interop check SKIPPED: no native_harness.exe built, so the APCpp "
              "transport is unexercised this run.")
        return 0
    completed = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / "native_interop_check.py"),
         str(candidates[0])],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
    )
    if completed.returncode:
        print("scripts/native_interop_check.py failed:")
        print(completed.stdout[-2000:])
        print(completed.stderr[-2000:])
    return completed.returncode


def _run_helper(name: str) -> int:
    """Runs one script in scripts/ and requires it to succeed.

    Output is dropped unless it fails: the spec is for humans at the keyboard and
    the mirror check has nothing to say when it agrees. stdin is closed because
    Archipelago's ModuleUpdate prompts on a dependency mismatch, and a prompt
    nobody can answer is a hang rather than a failure.
    """
    completed = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / name)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
    )
    if completed.returncode:
        print(f"scripts/{name} failed:")
        print(completed.stdout[-2000:])
        print(completed.stderr[-2000:])
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
