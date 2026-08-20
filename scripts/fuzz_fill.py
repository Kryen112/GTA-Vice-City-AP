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
    # Splitting the mainland access into one item per crossing turns the single
    # mainland edge into a one-of-four choice, which loosens reachability while
    # adding three progression items to place. Covered on its own, on the
    # tightest accepted pool, and with the collectible classes that put the most
    # checks behind the mainland.
    ("mainland crossings split", {"split_mainland_access": True}),
    # Splitting the content locks turns five progression items into 42, which is
    # the largest single change to the pool any option makes, so it is fuzzed at
    # both granularities and against the mainland split it composes with.
    ("content locks per district", {
        "content_locks": ["hidden_packages", "rampages", "stunt_jumps",
                          "properties", "robbable_stores"],
        "split_content_locks": "per_district",
    }),
    ("content locks per class", {
        "content_locks": ["hidden_packages", "rampages", "stunt_jumps",
                          "properties", "robbable_stores"],
        "split_content_locks": "per_class",
    }),
    ("content locks per class, mainland split too", {
        "content_locks": ["hidden_packages", "rampages", "stunt_jumps",
                          "properties", "robbable_stores"],
        "split_content_locks": "per_class",
        "split_mainland_access": True,
    }),
    ("mainland crossings split, tightest pool", {
        "split_mainland_access": True,
        "enable_hidden_packages": True, "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False, "enable_side_events": False,
        "enable_robbable_stores": False,
    }),
    ("mainland crossings split, all classes on", {
        "split_mainland_access": True, "enable_hidden_packages": True,
        "enable_rampages": True, "enable_stunt_jumps": True,
        "enable_emergency_vehicles": True, "enable_properties": True,
        "enable_robbable_stores": True, "enable_side_events": True,
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
    # The starting draws take one item per family out of the pool and into
    # starting inventory, so they shift the item count against the location
    # count on every seed.
    ("ability locks, all keys, starting draw", {
        "ability_locks": ["sprint", "jump", "crouch", "vehicles",
                          "weapon_equip", "wallet"],
        "starting_ability_unlock": True,
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
    # Content locks put a term on every check of the classes they hold, so the
    # matrix covers all keys with everything on, the widest 100 percent rule
    # surface, both lock families at once, and a key on a class the seed does
    # not otherwise enable.
    ("content locks, all keys", {
        "content_locks": ["hidden_packages", "rampages", "stunt_jumps",
                          "properties", "robbable_stores"],
    }),
    ("content locks, all keys, 100 percent", {
        "goal": "hundred_percent",
        "content_locks": ["hidden_packages", "rampages", "stunt_jumps",
                          "properties", "robbable_stores"],
    }),
    # Both draws on with only content keys selected, so the content draw fires
    # and the ability one finds nothing to draw from. Ability keys are left out:
    # all five content keys plus any ability key is a refused shape, covered by
    # its own row below.
    ("content locks, all keys, starting draw", {
        "content_locks": ["hidden_packages", "rampages", "stunt_jumps",
                          "properties", "robbable_stores"],
        "starting_content_unlock": True,
        "starting_ability_unlock": True,
    }),
    # With every check class enabled, all five content keys and no ability key
    # still measure a free count of 35. What refuses a seed is content locks
    # plus something else that narrows the start: ability_locks here, disabled
    # check classes in the packages-only row further down. Hidden packages are
    # the one class no ability term touches, so holding them is what tips a
    # seed over, and combinations well short of every key are refused; the
    # matrix carries a minimal one beside the full corner.
    ("content and ability locks, all keys EXPECT reject", {
        "content_locks": ["hidden_packages", "rampages", "stunt_jumps",
                          "properties", "robbable_stores"],
        "ability_locks": ["sprint", "jump", "crouch", "vehicles",
                          "weapon_equip", "wallet"],
    }),
    ("packages held plus three ability keys EXPECT reject", {
        "content_locks": ["hidden_packages"],
        "ability_locks": ["vehicles", "weapon_equip", "wallet"],
    }),
    # The narrow-start guard measures what is open with no item at all, so a
    # starting draw cannot rescue a refused shape. Deliberate: no seed's
    # solvability may rest on a random draw.
    ("packages held plus three ability keys, both draws EXPECT reject", {
        "content_locks": ["hidden_packages"],
        "ability_locks": ["vehicles", "weapon_equip", "wallet"],
        "starting_content_unlock": True,
        "starting_ability_unlock": True,
    }),
    ("content lock on a disabled class", {
        "enable_properties": False, "content_locks": ["properties"],
    }),
    # Holding the packages leaves the first mission alone reachable, since
    # every other start-island class is off. Same shape as a heavy ability
    # lock, refused for the same reason.
    ("content lock, packages only EXPECT reject", {
        "content_locks": ["hidden_packages"],
        "enable_rampages": False, "enable_stunt_jumps": False,
        "enable_emergency_vehicles": False, "enable_properties": False,
        "enable_robbable_stores": False, "enable_side_events": False,
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
    "packages held plus three ability keys, both draws EXPECT reject":
        "check is reachable on a new game",
    "ability locks, all keys, story plus side events EXPECT reject":
        "check is reachable on a new game",
    "ability locks, all keys, packages off EXPECT reject":
        "check is reachable on a new game",
    "content lock, packages only EXPECT reject":
        "check is reachable on a new game",
    "content and ability locks, all keys EXPECT reject":
        "check is reachable on a new game",
    "packages held plus three ability keys EXPECT reject":
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
