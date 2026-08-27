"""Writes the id snapshot the test suite holds the world's tables to.

    python scripts/freeze_ids.py              rewrite it, before release
    python scripts/freeze_ids.py --first-run  write the very first one

Item and location ids are DERIVED: each table is its names in registry order,
numbered from a base. That makes a reorder in data.py a silent renumbering of
everything after it, and after the first public release a renumbering breaks
every seed and every tracker already out there. The snapshot is what turns that
into a failing test.

Before the release the snapshot is a mirror: change the tables on purpose, run
this, and the diff shows exactly which ids moved. After it, when the snapshot
says released, an id that already exists is fixed forever and this refuses to
write a file that moves one.

Adding is allowed after release, and only at the very end of a table. Each table
is its category lists concatenated, so a new trap or a tenth radio station lands
in the middle of one and shifts every name after it, which is a move and is
refused like any other.

Two things this does NOT freeze, and both matter to a seed in progress. The
reserved SCM globals are numbered from the same order (scm.py derives the
completion block from the location list and the reward block from its length),
so even a legal tail append shifts them and breaks a save that is mid-seed. And
nothing here pins the tracker pack, which reads these ids from the world.

Flipping `released` to true is a hand edit of the snapshot, done once, at the
release. Nothing automates it: it is the moment the ids stop being ours.
"""

from __future__ import annotations

import json
import sys

from ap_env import REPOSITORY_ROOT, WORLD_SOURCE, archipelago_root, link_world

SNAPSHOT = WORLD_SOURCE / "test" / "frozen_ids.json"
KINDS = ("items", "locations")


def current_tables() -> dict[str, object]:
    """The world's own id tables, read through the linked world package.

    Imported as worlds.gta_vice_city, the way Archipelago itself imports it,
    since the package's own __init__ reaches for the core.
    """
    from worlds.gta_vice_city.items import ID_BASE as ITEM_ID_BASE
    from worlds.gta_vice_city.items import ITEM_NAME_TO_ID
    from worlds.gta_vice_city.locations import ID_BASE as LOCATION_ID_BASE
    from worlds.gta_vice_city.locations import LOCATION_NAME_TO_ID
    return {
        "item_id_base": ITEM_ID_BASE,
        "location_id_base": LOCATION_ID_BASE,
        "items": dict(ITEM_NAME_TO_ID),
        "locations": dict(LOCATION_NAME_TO_ID),
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
        print("No Archipelago checkout found. Set AP_ROOT or clone 0.6.7 as a "
              "sibling directory.")
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
          f"locations, {state}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
