"""Multi-seed fill fuzzer.

Generates many seeds across the goal and toggle matrix and reports, per
configuration: solved, FillError (structural or seed-luck unsolvable), and
OptionError (a configuration the world rejects on purpose). This is how we
learn the FillError base rate and confirm the solvability guards, per the
playbook. Run: python scripts/fuzz_fill.py [seeds_per_config].
"""

from __future__ import annotations

import sys

from ap_env import WORLD_SOURCE, archipelago_root, link_world

GAME = "Grand Theft Auto Vice City"

# (label, options). Some are expected to be rejected by design; the report
# shows whether each config solved, failed fill, or was rejected.
CONFIGURATIONS: list[tuple[str, dict]] = [
    ("default (final mission, packages on)", {}),
    ("goal hidden_packages", {"goal": "hidden_packages"}),
    ("goal hidden_packages, need all", {"goal": "hidden_packages", "hidden_packages_required": 100}),
    # The hunt adds 100 macguffins; with only packages and story on, the pool
    # outgrows the checks and the overflow guard refuses the seed.
    ("goal hidden_packages, minimal classes EXPECT reject", {
        "goal": "hidden_packages", "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False, "enable_robbable_stores": False,
        "enable_side_events": False,
    }),
    # Story-only is refused on item math: the story pool's progressive unlocks
    # and the two area items outnumber the 44 story checks.
    ("story only (all optional classes off) EXPECT reject", {
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False,
        "enable_robbable_stores": False, "enable_side_events": False,
    }),
    # One collectible class gives the story pool homes. These are the near
    # minimal accepted pools, and the ones the world modifiers stack on.
    ("story plus stores", {
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False, "enable_side_events": False,
    }),
    ("story plus side events", {
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False, "enable_robbable_stores": False,
    }),
    # Every stunt jump sits on the mainland, so a seed carrying them as its
    # only collectible class opens nothing at the start but the first mission,
    # with no lock selected at all.
    ("story plus stunt jumps EXPECT reject", {
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_emergency_vehicles": False, "enable_properties": False,
        "enable_robbable_stores": False, "enable_side_events": False,
    }),
    # Radio stations add eight useful items to the pool.
    ("radio stations on", {"randomize_radio_stations": True}),
    ("radio stations on, story plus stores", {
        "randomize_radio_stations": True,
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False, "enable_side_events": False,
    }),
    ("100 percent, all classes on", {
        "goal": "hundred_percent", "enable_hidden_packages": True,
        "enable_rampages": True, "enable_stunt_jumps": True,
        "enable_emergency_vehicles": True, "enable_properties": True,
        "enable_robbable_stores": True, "enable_side_events": True,
    }),
    ("100 percent, one class off EXPECT reject", {
        "goal": "hundred_percent", "enable_side_events": False,
    }),
    # Ability locks add up to eight items whose terms gate whole check
    # classes; the matrix covers all locks with everything on, the tightest
    # accepted pool, the widest 100 percent rule surface, and a partial set.
    ("ability locks, all keys", {
        "ability_locks": ["sprint", "jump", "crouch", "vehicles",
                          "weapon_equip", "wallet"],
    }),
    # Locks put these seeds' start-region checks behind an item, so only the
    # first mission is reachable on a new game and the fill would have to chain
    # through it. A locked class does not always land here: packages off with
    # rampages on and only weapon_equip locked keeps two checks and is accepted.
    ("ability locks, all keys, story plus stores EXPECT reject", {
        "ability_locks": ["sprint", "jump", "crouch", "vehicles",
                          "weapon_equip", "wallet"],
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False, "enable_side_events": False,
    }),
    ("weapon_equip lock, story plus stores EXPECT reject", {
        "ability_locks": ["weapon_equip"],
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False, "enable_side_events": False,
    }),
    ("ability locks, all keys, story plus stunt jumps EXPECT reject", {
        "ability_locks": ["sprint", "jump", "crouch", "vehicles",
                          "weapon_equip", "wallet"],
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_emergency_vehicles": False, "enable_properties": False,
        "enable_robbable_stores": False, "enable_side_events": False,
    }),
    ("ability locks, all keys, story plus side events EXPECT reject", {
        "ability_locks": ["sprint", "jump", "crouch", "vehicles",
                          "weapon_equip", "wallet"],
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False, "enable_robbable_stores": False,
    }),
    ("ability locks, all keys, 100 percent", {
        "goal": "hundred_percent",
        "ability_locks": ["sprint", "jump", "crouch", "vehicles",
                          "weapon_equip", "wallet"],
    }),
    ("ability locks, vehicles and wallet", {
        "ability_locks": ["vehicles", "wallet"],
    }),
    # Hidden packages are the only start-region class with no ability term, so
    # turning them off while every other class stays on still leaves the first
    # mission alone reachable. The guard refuses the shape rather than the
    # individual seed, so this one is refused with the rest of it.
    ("ability locks, all keys, packages off EXPECT reject", {
        "ability_locks": ["sprint", "jump", "crouch", "vehicles",
                          "weapon_equip", "wallet"],
        "enable_hidden_packages": False,
    }),
    ("deathlink on", {"death_link": True}),
]

# Which guard must refuse each EXPECT reject configuration, as a fragment of
# its message. A row refused by a different guard is as wrong as one that
# generates, since it would pass while covering nothing it claims to cover.
REFUSAL_GUARDS: dict[str, str] = {
    "goal hidden_packages, minimal classes EXPECT reject":
        "progression and useful items",
    "story only (all optional classes off) EXPECT reject":
        "progression and useful items",
    "story plus stunt jumps EXPECT reject":
        "check is reachable on a new game",
    "100 percent, one class off EXPECT reject":
        "100 percent goal requires every check class",
    "ability locks, all keys, story plus stores EXPECT reject":
        "check is reachable on a new game",
    "weapon_equip lock, story plus stores EXPECT reject":
        "check is reachable on a new game",
    "ability locks, all keys, story plus stunt jumps EXPECT reject":
        "check is reachable on a new game",
    "ability locks, all keys, story plus side events EXPECT reject":
        "check is reachable on a new game",
    "ability locks, all keys, packages off EXPECT reject":
        "check is reachable on a new game",
}


def main() -> int:
    root = archipelago_root()
    if root is None:
        print("No Archipelago checkout found. Set AP_ROOT or clone 0.6.7 as a sibling.")
        return 1
    if not WORLD_SOURCE.is_dir():
        print(f"No world package at {WORLD_SOURCE}.")
        return 1
    if link_world(root) is None:
        return 1
    sys.path.insert(0, str(root))

    from Fill import FillError, distribute_items_restrictive
    from Options import OptionError
    from test.general import gen_steps, setup_multiworld
    from worlds.AutoWorld import AutoWorldRegister

    world_type = AutoWorldRegister.world_types[GAME]
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 25

    any_unexpected = False
    print(f"Fuzzing {GAME}: {seeds} seeds per configuration.\n")
    for label, options in CONFIGURATIONS:
        solved = fill_errors = rejected = unbeatable = 0
        first_error = ""
        for seed in range(seeds):
            try:
                multiworld = setup_multiworld(world_type, gen_steps, seed=seed, options=options)
                distribute_items_restrictive(multiworld)
                state = multiworld.get_all_state(False)
                if multiworld.completion_condition[1](state):
                    solved += 1
                else:
                    unbeatable += 1
            except OptionError as error:
                rejected += 1
                first_error = first_error or str(error)
            except FillError as error:
                fill_errors += 1
                first_error = first_error or str(error)
        expect_reject = "EXPECT reject" in label
        guard = REFUSAL_GUARDS.get(label)
        flag = ""
        if expect_reject and rejected != seeds:
            flag = "  <-- expected all rejected"
        elif expect_reject and guard is None:
            flag = "  <-- add this label to REFUSAL_GUARDS"
        elif expect_reject and guard not in first_error:
            flag = f"  <-- refused by the wrong guard, wanted {guard!r}"
        elif not expect_reject and rejected:
            flag = "  <-- unexpected rejection"
        elif fill_errors or unbeatable:
            flag = "  <-- unexpected failure"
        if flag:
            any_unexpected = True
        print(f"{label}")
        print(f"    solved={solved} fill_errors={fill_errors} rejected={rejected} "
              f"unbeatable={unbeatable}{flag}")
        if first_error:
            print(f"    first message: {first_error[:120]}")
    print()
    print("DONE" + ("" if not any_unexpected else " (see unexpected flags above)"))
    return 1 if any_unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
