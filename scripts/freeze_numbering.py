"""Writes the numbering snapshot the test suite holds the world to.

    python scripts/freeze_numbering.py              rewrite it, before release
    python scripts/freeze_numbering.py --first-run  write the very first one

Three numberings, all derived and all breakable the same way. Item and location
ids are DERIVED: each table is its names in registry order,
numbered from a base. That makes a reorder in data.py a silent renumbering of
everything after it, and after the first public release a renumbering breaks
every seed and every tracker already out there. The snapshot is what turns that
into a failing test. The reserved SCM globals are numbered the same way, from
the same lists, and they are worse to move: they are compiled into main.scm and
the CLEO scripts and written into save files, so a global that shifts points a
running seed's save at the wrong word. That breaks a game in progress, which is
why this half of the freeze matters before any release as well as after one.

Before the release the snapshot is a mirror: change the tables on purpose, run
this, and the diff shows exactly which ids moved. After it, when the snapshot
says released, an id that already exists is fixed forever and this refuses to
write a file that moves one.

Adding after release is narrower than it sounds, and for the globals it is
narrower still. A table append has to be the tail of the LAST category, since
each table is its category lists concatenated. And appending a LOCATION, which
the id half allows, grows the completion block and pushes REWARD_BASE and every
block above it up one, which this refuses: that shift is precisely the mid-seed
save break. After release, then, a new location means a new numbering and a new
apworld release, not an append.

A new reserved global has no tail either. Every block is followed by another, so
one added above the highest moves base:highest_reserved, which is frozen too and
deliberately: add_markers.py sizes the marker scratch from it, so the top of the
reserved block is itself a number main.scm is built against. Each table
is its category lists concatenated, so a new trap or a tenth radio station lands
in the middle of one and shifts every name after it, which is a move and is
refused like any other.

One thing this does NOT freeze: the tracker pack, which reads these ids from the
world and is pinned by nothing here.

Flipping `released` to true is a hand edit of the snapshot, done once, at the
release. Nothing automates it: it is the moment the ids stop being ours.
"""

from __future__ import annotations

import json
import sys

from ap_env import REPOSITORY_ROOT, WORLD_SOURCE, archipelago_root, link_world, missing_checkout_message

SNAPSHOT = WORLD_SOURCE / "test" / "frozen_numbering.json"
KINDS = ("items", "locations", "scm_globals")


def current_tables() -> dict[str, object]:
    """The world's own id tables, read through the linked world package.

    Imported as worlds.gta_vice_city, the way Archipelago itself imports it,
    since the package's own __init__ reaches for the core.
    """
    from worlds.gta_vice_city.items import ID_BASE as ITEM_ID_BASE
    from worlds.gta_vice_city.items import ITEM_NAME_TO_ID
    from worlds.gta_vice_city.locations import ID_BASE as LOCATION_ID_BASE
    from worlds.gta_vice_city.locations import LOCATION_NAME_TO_ID
    from worlds.gta_vice_city.scm import reserved_global_map
    return {
        "item_id_base": ITEM_ID_BASE,
        "location_id_base": LOCATION_ID_BASE,
        "items": dict(ITEM_NAME_TO_ID),
        "locations": dict(LOCATION_NAME_TO_ID),
        "scm_globals": reserved_global_map(),
    }


def moved_entries(frozen: dict, current: dict) -> list[str]:
    """Every id the snapshot already fixed that the tables no longer agree with.

    A name whose id changed, and a name that is gone. Names the tables have
    gained are not here: appending is the one change the freeze allows, and the
    test is what holds an append to the tail.

    A released snapshot missing a table is itself an entry, because reading it
    as nothing to check is how a released freeze quietly stops freezing.
    """
    moved = []
    for kind in KINDS:
        if kind not in frozen:
            moved.append(f"{kind}: the released snapshot has no {kind} at all")
            continue
        for name, identifier in frozen[kind].items():
            now = current[kind].get(name)
            if now is None:
                moved.append(f"{kind}: {name!r} is gone, id {identifier}")
            elif now != identifier:
                moved.append(f"{kind}: {name!r} was {identifier}, now {now}")
    moved.extend(f"{field} was {frozen[field]}, now {current[field]}"
                 for field in ("item_id_base", "location_id_base")
                 if field in frozen and frozen[field] != current[field])
    return moved


def main() -> int:
    first_run = "--first-run" in sys.argv[1:]
    root = archipelago_root()
    if root is None:
        print(missing_checkout_message())
        return 1
    if link_world(root) is None:
        return 1
    sys.path.insert(0, str(root))
    current = current_tables()

    if not SNAPSHOT.is_file():
        # The snapshot is checked in, so after the first run its absence is a
        # deletion. Writing a fresh one over whatever the tables happen to hold
        # would take the freeze off and report success doing it.
        if not first_run:
            print(f"Refusing to write the snapshot: there is none at "
                  f"{SNAPSHOT.relative_to(REPOSITORY_ROOT)}, and it is checked "
                  "in, so it has been deleted rather than never written. Restore "
                  "it from git. Pass --first-run only to write the very first "
                  "one.")
            return 1
    else:
        frozen = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        if first_run:
            print("Refusing to write the snapshot: --first-run, but "
                  f"{SNAPSHOT.relative_to(REPOSITORY_ROOT)} already exists.")
            return 1
        released = frozen.get("released")
        if not isinstance(released, bool):
            print(f"Refusing to write the snapshot: its released flag is "
                  f"{released!r}, which is neither true nor false, so nothing "
                  "here knows which phase it is in.")
            return 1
        if released:
            moved = moved_entries(frozen, current)
            if moved:
                shown = "\n  ".join(moved[:10])
                more = f"\n  and {len(moved) - 10} more" if len(moved) > 10 else ""
                print("Refusing to write the snapshot: these ids are released, "
                      f"and a released id never moves.\n  {shown}{more}\n"
                      "Every seed and tracker in the world reads these. Put the "
                      "tables back, and append instead.")
                return 1
        current["released"] = released

    snapshot = {"released": current.pop("released", False), **current}
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot, indent=2, sort_keys=False) + "\n",
                        encoding="utf-8")
    state = "released" if snapshot["released"] else "not yet released"
    print(f"Wrote {SNAPSHOT.relative_to(REPOSITORY_ROOT)}: "
          f"{len(snapshot['items'])} items, {len(snapshot['locations'])} "
          f"locations, {len(snapshot['scm_globals'])} reserved globals, {state}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
