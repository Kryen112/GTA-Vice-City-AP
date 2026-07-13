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
    ("story only (packages off) EXPECT reject", {"enable_hidden_packages": False}),
    ("100 percent, all classes on", {
        "goal": "hundred_percent", "enable_hidden_packages": True,
        "enable_rampages_stunts": True, "enable_emergency_vehicles": True,
        "enable_properties": True, "enable_robbable_stores": True,
        "enable_side_events": True,
    }),
    ("100 percent, one class off EXPECT reject", {
        "goal": "hundred_percent", "enable_side_events": False,
    }),
    ("deathlink on", {"death_link": True}),
]


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
        flag = ""
        if expect_reject and rejected != seeds:
            flag = "  <-- expected all rejected"
            any_unexpected = True
        if not expect_reject and (fill_errors or unbeatable):
            flag = "  <-- unexpected failure"
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
