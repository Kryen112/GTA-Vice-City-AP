"""Runs the world tests against a real Archipelago checkout.

The single test entry point for pre-commit, CI, and manual runs. Locates
the Archipelago checkout from AP_ROOT or the sibling directory, links the
world package into its worlds directory, and runs pytest from there.
"""

import os
import pathlib
import subprocess
import sys

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORLD_NAME = "gta_vice_city"
WORLD_SOURCE = REPOSITORY_ROOT / "apworld" / WORLD_NAME


def find_archipelago_root() -> pathlib.Path | None:
    override = os.environ.get("AP_ROOT")
    candidate = pathlib.Path(override) if override else REPOSITORY_ROOT.parent / "Archipelago"
    if (candidate / "worlds").is_dir():
        return candidate.resolve()
    return None


def link_world_into(archipelago_root: pathlib.Path) -> pathlib.Path | None:
    target = archipelago_root / "worlds" / WORLD_NAME
    if target.exists():
        if target.resolve() == WORLD_SOURCE.resolve():
            return target
        print(f"{target} exists and does not point at this repository; remove it first.")
        return None
    if sys.platform == "win32":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(WORLD_SOURCE)],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            print("Creating the directory junction failed:")
            print(completed.stderr.decode(errors="replace"))
            return None
    else:
        target.symlink_to(WORLD_SOURCE, target_is_directory=True)
    return target


def main() -> int:
    if not WORLD_SOURCE.is_dir():
        print(f"No world package at {WORLD_SOURCE} yet; nothing to test.")
        return 0
    archipelago_root = find_archipelago_root()
    if archipelago_root is None:
        print("No Archipelago checkout found. Set AP_ROOT or clone 0.6.7 as a sibling directory.")
        return 1
    target = link_world_into(archipelago_root)
    if target is None:
        return 1
    return subprocess.call(
        [sys.executable, "-m", "pytest", str(target / "test"), "-q"],
        cwd=archipelago_root,
    )


if __name__ == "__main__":
    sys.exit(main())
