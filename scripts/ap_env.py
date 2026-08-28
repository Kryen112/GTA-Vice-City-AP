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


# What tells an Archipelago checkout from a folder that merely shares its name.
# The search below walks to the drive root, so any folder called Archipelago in
# any ancestor is a candidate, and a bare worlds directory is a name two projects
# could both have. This file is the world API every checkout carries.
CHECKOUT_MARKER = pathlib.Path("worlds") / "AutoWorld.py"


def _is_checkout(candidate: pathlib.Path) -> bool:
    """Whether a path is an Archipelago checkout rather than a folder named one."""
    return (candidate / CHECKOUT_MARKER).is_file()


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
    override = _override()
    if override is not None:
        candidate = pathlib.Path(override)
        return candidate.resolve() if _is_checkout(candidate) else None
    for ancestor in REPOSITORY_ROOT.parents:
        candidate = ancestor / "Archipelago"
        if _is_checkout(candidate):
            return candidate.resolve()
    return None


def _override() -> str | None:
    """The AP_ROOT override, or None when it is unset or empty.

    Both the lookup and the message that explains a failed one ask through here,
    so the two cannot reach different conclusions about whether the override is
    the thing that failed. An empty AP_ROOT counts as unset, since a variable
    cleared to nothing is not a path anyone meant to point at.
    """
    return os.environ.get("AP_ROOT") or None


def missing_checkout_message() -> str:
    """What to print when archipelago_root finds nothing, which is two failures.

    A rejected AP_ROOT and an empty search both come back as None, and they need
    opposite advice. Telling someone who set the override to set the override is
    the one instruction that cannot help them, so that case names the value it
    turned down instead. Every entry point prints this rather than its own words,
    which is what keeps the wording from drifting apart across six files.
    """
    override = _override()
    if override is None:
        return ("No Archipelago checkout found. Set AP_ROOT, or clone 0.6.7 as "
                "Archipelago beside this repository or beside one of its ancestors.")
    advice = ("Point it at a 0.6.7 checkout, or unset it to search beside this "
              "repository.")
    # A mistyped path is the commonest way this fails, and telling someone their
    # folder lacks a file when the folder itself is absent sends them looking
    # inside something that is not there.
    if not pathlib.Path(override).is_dir():
        return f"AP_ROOT is set to {override}, which is not a folder. {advice}"
    return (f"AP_ROOT is set to {override}, which is a folder but not an "
            f"Archipelago checkout: it has no {CHECKOUT_MARKER.as_posix()}. "
            f"{advice}")


def _remove_dangling_link(target: pathlib.Path) -> bool:
    """Delete a link at target whose destination is gone, and say whether it did.

    A junction or symlink an earlier layout left behind keeps the name once what
    it pointed at moves away, and the linking below refuses a name that already
    exists, so the stale entry blocks every run until it goes. Removing it can
    take no file with it: the entry is a link, and it is one to nothing.

    Only a link whose destination does not resolve is removed. A link to a live
    path that is not this repository is left for the caller to refuse, since it
    may be another checkout's and is not this script's to delete. Unreachable
    counts as gone here, so a link into a disconnected share or an absent drive
    is taken as well; the name is one the linking below would claim regardless,
    and no file behind it is reachable to lose.
    """
    if not os.path.lexists(target) or target.exists():
        return False
    try:
        if sys.platform == "win32":
            try:
                os.rmdir(target)
            except NotADirectoryError:
                target.unlink()
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
