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
    completion_top = scm.COMPLETION_BASE + len(locations.LOCATION_NAME_TO_ID) - 1
    print(f"- Completion:     ${scm.COMPLETION_BASE}..${completion_top}"
          "  (the SCM sets to 1 on completion; the ASI polls them)")
    reward_top = scm.REWARD_BASE + len(scm.REWARD_KEYS) - 1
    print(f"- Reward globals: ${scm.REWARD_BASE}..${reward_top}"
          "  (ASI writes 1 when the reward item is received; the SCM re-gates the "
          "vanilla grant on it when its class is shuffled)")
    print(f"- Config flags:   ${scm.PACKAGES_SHUFFLED_GLOBAL} packages_shuffled, "
          f"${scm.EMERGENCY_SHUFFLED_GLOBAL} emergency_shuffled  (ASI stamps from slot_data)")
    print(f"- Highest reserved global: ${scm.highest_reserved_global()} "
          "(reference it once so Sanny grows the global space to cover the block)")
    print()

    print("## Mission gates (per launcher, in vanilla order)")
    print("Gate the launcher before load_and_launch_mission_internal: allow the")
    print("mission only when every listed global is at least its count. Set the")
    print("completion global to 1 when the mission passes. A venue mission also")
    print("gates on its property being bought, read from the venue purchase's")
    print("completion global (in logic the stand-in is the items to pass")
    print(f"{data.PROPERTY_UNLOCK_MISSION}, the mission that puts the businesses up for sale).")
    print("The ownership condition is the required behavior; for the Boatyard and")
    print("Sunshine Autos activity launchers the SCM emits no explicit condition,")
    print("because their threads only start at the buy cutscene, which already")
    print("carries it.")
    for strand, (class_key, missions) in data.progressive_strands().items():
        print()
        print(f"### {strand}  [{class_key}]  unlock global ${scm.unlock_global(strand)}")
        for position, mission in enumerate(missions, start=1):
            giver = locations.MISSION_GIVER[mission]
            requirements = rules._mission_requirements(mission, giver)
            parts = [
                f"${scm.unlock_global(_strand_of(item))} >= {count}"
                for item, count in requirements
            ]
            if strand in data.VENUE_STRANDS:
                purchase = f"{strand} Purchase"
                parts.append(f"${scm.completion_global(purchase)} >= 1 (property bought)")
            gate = " AND ".join(parts) if parts else "(free, no unlock)"
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
    print("## Persistent-reward globals (re-gate the vanilla grant on these when "
          "the reward class is shuffled)")
    reward_activity = {item: activity for activity, item in data.EMERGENCY_REWARD_BY_ACTIVITY.items()}
    for reward in data.PERSISTENT_REWARD_ITEMS:
        activity = reward_activity.get(reward)
        source = f"emergency: {activity} completion" if activity else "hidden-package reward"
        print(f"- ${scm.reward_global(reward)}  {reward}  ({source})")

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
