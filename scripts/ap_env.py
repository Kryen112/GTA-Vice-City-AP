"""Locate the Archipelago checkout and link this world into it.

Shared by the test runner and the fill fuzzer so they agree on where
Archipelago lives (AP_ROOT override, else an Archipelago beside one of this
repository's ancestors) and how the world package is exposed to it.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORLD_NAME = "gta_vice_city"
WORLD_SOURCE = REPOSITORY_ROOT / "apworld" / WORLD_NAME


def _is_checkout(candidate: pathlib.Path) -> bool:
    """Whether a path is an Archipelago checkout rather than a folder named one."""
    return (candidate / "worlds").is_dir()


def archipelago_root() -> pathlib.Path | None:
    """The Archipelago checkout to run against, or None when there is none.

    AP_ROOT wins outright and is never second-guessed: an override that is not a
    checkout returns None rather than falling back to the search, so a typo in it
    fails here rather than running the suite against some other checkout.

    Without the override, every ancestor of this repository is tried in turn for
    an Archipelago beside it, nearest first. The immediate parent is the sibling
    layout, and the ancestors above it keep the checkout findable when this
    repository sits some folders deeper than the one Archipelago is cloned into.
    Nearest wins, so a checkout beside this repository still beats a further one.
    """
    override = os.environ.get("AP_ROOT")
    if override:
        candidate = pathlib.Path(override)
        return candidate.resolve() if _is_checkout(candidate) else None
    for ancestor in REPOSITORY_ROOT.parents:
        candidate = ancestor / "Archipelago"
        if _is_checkout(candidate):
            return candidate.resolve()
    return None


def _remove_dangling_link(target: pathlib.Path) -> bool:
    """Delete a link at target whose destination is gone, and say whether it did.

    A junction or symlink an earlier layout left behind keeps the name once what
    it pointed at moves away, and the linking below refuses a name that already
    exists, so the stale entry blocks every run until it goes. Removing it can
    take no file with it: the entry is a link, and it is one to nothing.

    Only a link to a path that no longer exists is removed. A link to a live path
    that is not this repository is left for the caller to refuse, since it may be
    another checkout's and is not this script's to delete.
    """
    if not os.path.lexists(target) or target.exists():
        return False
    try:
        if sys.platform == "win32":
            os.rmdir(target)
        else:
            target.unlink()
    except OSError:
        return False
    return True


def link_world(root: pathlib.Path) -> pathlib.Path | None:
    target = root / "worlds" / WORLD_NAME
    if _remove_dangling_link(target):
        print(f"Removed the link at {target}; what it pointed at is gone.")
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
