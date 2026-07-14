"""Prints the SCM buildout spec from the world's own tables.

For the custom main.scm: every mission launcher's unlock gate (which reserved
global to read and the count threshold) and every location's completion global
(which reserved global to set on completion). Derived from scm.py, data.py, and
rules.py, so it never drifts from the generator's logic. Run it and work from
the output in Sanny Builder.

    python scripts/dump_scm_spec.py
"""

from __future__ import annotations

import sys

from ap_env import archipelago_root, link_world


def _strand_of(item_name: str) -> str:
    return item_name[len("Progressive "):]


def main() -> int:
    root = archipelago_root()
    if root is None:
        print("No Archipelago checkout found. Set AP_ROOT or clone 0.6.7 as a sibling.")
        return 1
    if link_world(root) is None:
        return 1
    sys.path.insert(0, str(root))
    from worlds.gta_vice_city import data, locations, rules, scm

    print("# main.scm buildout spec (generated from scm.py, data.py, rules.py)")
    print()
    print("## Reserved global block (declare all of these, zero-initialized)")
    print(f"- Seed hash:      ${scm.SEED_HASH_BASE}..${scm.SEED_HASH_BASE + scm.SEED_HASH_GLOBAL_COUNT - 1}"
          "  (ASI writes and reads; the SCM only reserves them)")
    print(f"- Applied index:  ${scm.APPLIED_INDEX_GLOBAL}  (ASI managed)")
    print(f"- Unlock globals: ${scm.UNLOCK_BASE}..${scm.UNLOCK_BASE + len(scm.UNLOCK_KEYS) - 1}"
          "  (ASI writes the received count; the SCM reads them in gates)")
    print(f"- Completion:     ${scm.COMPLETION_BASE}..${scm.highest_reserved_global()}"
          "  (the SCM sets to 1 on completion; the ASI polls them)")
    print(f"- Highest reserved global: ${scm.highest_reserved_global()} "
          "(reference it once so Sanny grows the global space to cover the block)")
    print()

    print("## Mission gates (per launcher, in vanilla order)")
    print("Gate the launcher before load_and_launch_mission_internal: allow the")
    print("mission only when every listed global is at least its count. Set the")
    print("completion global to 1 when the mission passes.")
    for strand, (class_key, missions) in data.progressive_strands().items():
        print()
        print(f"### {strand}  [{class_key}]  unlock global ${scm.unlock_global(strand)}")
        for position, mission in enumerate(missions, start=1):
            giver = locations.MISSION_GIVER[mission]
            requirements = rules._mission_requirements(mission, giver)
            if requirements:
                gate = " AND ".join(
                    f"${scm.unlock_global(_strand_of(item))} >= {count}"
                    for item, count in requirements)
            else:
                gate = "(free, no unlock)"
            print(f"  #{position} {mission}")
            print(f"      gate:       {gate}")
            print(f"      completion: ${scm.completion_global(mission)} = 1 on pass")

    print()
    print("## Area access")
    for area in data.AREA_ITEMS:
        print(f"- {area}: unlock global ${scm.unlock_global(area)}. When it is >= 1, "
              "open the area (Mainland: delete roadblocks $1781/$1782/$1783 and set "
              "$847 = 1, mirroring the Phnom Penh '86 flip).")

    print()
    print("## Completion globals for non-mission locations (set to 1 when the "
          "in-game event completes)")
    mission_names = set(locations.MISSION_GIVER)
    by_class: dict[str, list[str]] = {}
    for name in locations.LOCATION_NAME_TO_ID:
        if name in mission_names:
            continue
        by_class.setdefault(locations.LOCATION_CLASS[name], []).append(name)
    for class_key, names in by_class.items():
        print()
        print(f"### {class_key}  ({len(names)} locations)")
        for name in names:
            print(f"  ${scm.completion_global(name)}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
