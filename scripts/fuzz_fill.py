"""Multi-seed fill fuzzer.

Generates many seeds across the goal and toggle matrix and reports, per
configuration: solved, FillError (structural or seed-luck unsolvable), and
OptionError (a configuration the world rejects on purpose). This is how we
learn the FillError base rate and confirm the solvability guards, per the
playbook. Run: python scripts/fuzz_fill.py [seeds_per_config].
"""

from __future__ import annotations

import sys

from ap_env import WORLD_SOURCE, archipelago_root, link_world, missing_checkout_message

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
    # Nineteen of the 36 unique stunt jumps sit on the start island, so the
    # class carries the story pool on its own the way the stores do.
    ("story plus stunt jumps", {
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_emergency_vehicles": False, "enable_properties": False,
        "enable_robbable_stores": False, "enable_side_events": False,
    }),
    # The 110 ambient pickups carry the story pool on their own: 53 sit on the
    # start island, which is 54 free checks in sphere 0, the widest of these
    # rows but only just, since packages alone give 49.
    ("story plus pickups", {
        "enable_pickups": True,
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False, "enable_robbable_stores": False,
        "enable_side_events": False,
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
    # Shops are the newest check class and the second the game's own completion
    # stat never counted, so they are fuzzed for the pool shapes they make
    # rather than for the goal. All 36 sit behind Boomshine Saigon and their own
    # stock gates, which is the deepest any class hides its checks.
    ("shops on", {"shuffle_shops": True}),
    # The tightest pool the class can make: every other optional class off, so
    # the story pool's items have 36 homes and all of them are behind one
    # mission partway down a strand.
    ("story plus shops", {
        "shuffle_shops": True,
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False, "enable_robbable_stores": False,
        "enable_side_events": False,
    }),
    # Every shop check is a purchase, so the wallet key puts the Wallet item on
    # all 36 at once, which is the largest single block of checks any one
    # ability term gates.
    ("shops on, wallet lock", {
        "shuffle_shops": True, "ability_locks": ["wallet"],
    }),
    # The uncounted-class path: the 100 percent goal neither demands shops nor
    # counts them, so a seed with both has 36 checks the goal ignores and must
    # still generate and still be beatable.
    ("shops on, 100 percent", {
        "shuffle_shops": True, "goal": "hundred_percent",
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
    # Pickups are the one class every ability key leaves standing, since walking
    # over one takes nothing: 50 free checks here against 54 with no locks. The
    # four that close are pay stands on the start island, which charge for what
    # they give and so wait on Wallet, ten of them across the city.
    ("ability locks, all keys, story plus pickups", {
        "enable_pickups": True,
        "ability_locks": ["sprint", "jump", "crouch", "vehicles",
                          "weapon_equip", "wallet"],
        "enable_hidden_packages": False, "enable_rampages": False,
        "enable_stunt_jumps": False, "enable_emergency_vehicles": False,
        "enable_properties": False, "enable_robbable_stores": False,
        "enable_side_events": False,
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
    # still measure a free count of 35. Content locks plus something else that
    # narrows the start close it down to the first mission alone: ability_locks
    # here, disabled check classes in the packages-only row further down. These
    # are the shapes the directed opener widens, so they generate rather than
    # refuse, and each row is here to hold that.
    ("content and ability locks, all keys", {
        "content_locks": ["hidden_packages", "rampages", "stunt_jumps",
                          "properties", "robbable_stores"],
        "ability_locks": ["sprint", "jump", "crouch", "vehicles",
                          "weapon_equip", "wallet"],
    }),
    ("packages held plus three ability keys", {
        "content_locks": ["hidden_packages"],
        "ability_locks": ["vehicles", "weapon_equip", "wallet"],
    }),
    # The shape a player is most likely to ask for: every content key split to
    # its finest, three ability keys, one class off and both draws on. The
    # narrowest start any option set produces, and the one the directed opener
    # exists for.
    ("every content key per class, three ability keys, both draws", {
        "goal": "hidden_packages", "enable_emergency_vehicles": False,
        "content_locks": ["hidden_packages", "rampages", "stunt_jumps",
                          "properties", "robbable_stores"],
        "split_content_locks": "per_class",
        "ability_locks": ["vehicles", "weapon_equip", "wallet"],
        "starting_content_unlock": True, "starting_ability_unlock": True,
        "randomize_radio_stations": True, "split_mainland_access": True,
        "randomize_pickups": True, "death_link": True,
    }),
    # "packages held plus three ability keys" with both draws on, and it must
    # come out the same way. A draw takes a content item into starting
    # inventory, so a draw free to take the packages would leave this shape with
    # nothing left to direct and refuse it. The opener is reserved ahead of the
    # draws for exactly that reason, and this row is what holds it.
    ("packages held plus three ability keys, both draws", {
        "content_locks": ["hidden_packages"],
        "ability_locks": ["vehicles", "weapon_equip", "wallet"],
        "starting_content_unlock": True,
        "starting_ability_unlock": True,
    }),
    ("content lock on a disabled class", {
        "enable_properties": False, "content_locks": ["properties"],
    }),
    # Holding the packages leaves the first mission alone reachable, since
    # every other start-island class is off. The one held class is what the
    # opener is drawn from, so the seed generates on a directed Hidden Packages.
    ("content lock, packages only", {
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
        print(missing_checkout_message())
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
