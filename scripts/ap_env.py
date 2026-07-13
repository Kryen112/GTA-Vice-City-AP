"""Locate the Archipelago checkout and link this world into it.

Shared by the test runner and the fill fuzzer so they agree on where
Archipelago lives (AP_ROOT override, else the sibling checkout) and how the
world package is exposed to it.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORLD_NAME = "gta_vice_city"
WORLD_SOURCE = REPOSITORY_ROOT / "apworld" / WORLD_NAME


def archipelago_root() -> pathlib.Path | None:
    override = os.environ.get("AP_ROOT")
    candidate = pathlib.Path(override) if override else REPOSITORY_ROOT.parent / "Archipelago"
    if (candidate / "worlds").is_dir():
        return candidate.resolve()
    return None


def link_world(root: pathlib.Path) -> pathlib.Path | None:
    target = root / "worlds" / WORLD_NAME
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
