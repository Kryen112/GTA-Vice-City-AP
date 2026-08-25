"""Generation and solvability tests for GTA: Vice City.

Run through scripts/run_tests.py, which links this world into a real
Archipelago checkout and invokes pytest.
"""

from __future__ import annotations

import collections
import io
import math
import random
from typing import ClassVar
from unittest.mock import patch

from BaseClasses import CollectionState, ItemClassification, LocationProgressType
from Fill import distribute_items_restrictive
from Options import OptionError, Visibility
from test.bases import WorldTestBase
from test.general import gen_steps, setup_multiworld
from worlds.AutoWorld import call_all

from .. import (
    MINIMUM_DIRECTED_SPHERE_ZERO,
    MINIMUM_SPHERE_ZERO,
    GTAViceCityWorld,
    data,
    district_data,
    rules,
    scm,
)
from ..items import DISTRICT_CONTENT_NAMES, ITEM_CLASSIFICATIONS, ITEM_NAME_TO_ID, ORDERED_ITEM_NAMES
from ..locations import (
    CLASS_TOGGLE,
    LOCATION_NAME_TO_ID,
    LOCATION_REGIONS,
    MISSION_GIVER,
    ORDERED_LOCATION_NAMES,
    PACKAGE_NAMES,
    STORY_MISSION_NAMES,
    STRAND_MISSIONS,
)
from ..options import (
    CHECK_CLASS_OPTIONS,
    HUNDRED_PERCENT_CLASS_OPTIONS,
    UNCOUNTED_CLASS_KEYS,
    UNCOUNTED_CLASS_OPTIONS,
    EnablePickups,
    EnableSideEvents,
)

_ALL_ABILITY_LOCKS: list[str] = [
    "sprint", "jump", "crouch", "vehicles", "weapon_equip", "wallet",
]

_ALL_CONTENT_LOCKS: list[str] = [
    "hidden_packages", "rampages", "stunt_jumps", "properties",
    "robbable_stores",
]


# The fields _restore_options reads unconditionally, so a passthrough test only
# has to name what it is actually about.
_TRACKER_SLOT_DATA: dict = {
    "goal": "final_mission",
    "hidden_packages_required": 60,
    "death_link": False,
}


class TestDefault(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: final-mission goal, hidden packages on.

    def test_a_sourced_route_binds_with_no_ability_key_selected(self) -> None:
        # A route's VEHICLE drops out when its key is unselected, since the item
        # is not in the pool and the vehicle is free; the SOURCE does not, and
        # that is the half these three packages are about. Three start-island
        # roofs the audit reaches only by helicopter, and no helicopter is on the
        # start island until the mainland opens or Rub Out leaves the Vice Point
        # Sparrow. So they gate on the mainland in a DEFAULT seed, where nothing
        # is locked at all, which is the case every other route test misses by
        # running with the keys on.
        roofs = [data.hidden_package_name(index) for index in (21, 25, 40)]
        for name in roofs:
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name(["Mainland Access"])
        for name in roofs:
            self.assertTrue(self.can_reach_location(name), name)

    def test_a_route_of_only_free_abilities_gates_nothing(self) -> None:
        # The other half of the same rule, and the reason the three above are
        # not simply mainland checks: a route naming only ability items is free
        # once none of them is locked, so the whole requirement is dropped. Two
        # of Leaf Links' five are that, the car and the fence, and either alone
        # opens the golf course in a default seed. The other three are not: the
        # helicopter and the boat carry a source, and Four Iron is a mission, so
        # a route can name something that is not an ability and still bind, which
        # is exactly what the test above is about.
        for index in (46, 47, 48, 49, 50):
            name = data.hidden_package_name(index)
            self.assertTrue(self.can_reach_location(name), name)


class TestHiddenPackagesGoal(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"goal": "hidden_packages", "hidden_packages_required": 50}

    def test_pool_holds_one_macguffin_per_package(self) -> None:
        macguffins = [
            item for item in self.multiworld.itempool
            if item.name == data.PACKAGE_FRAGMENT_ITEM and item.player == self.player
        ]
        self.assertEqual(len(macguffins), data.HIDDEN_PACKAGE_COUNT)
        # Progression, so the generator guarantees enough are reachable.
        self.assertTrue(all(item.advancement for item in macguffins))

    def test_goal_counts_received_macguffins_not_own_pickups(self) -> None:
        # The bug this guards: the goal is how many Package Fragments are
        # received, not whether the player reaches package locations in their own
        # game. A state with no macguffins does not win; receiving enough does.
        completion = self.multiworld.completion_condition[self.player]
        state = CollectionState(self.multiworld)
        self.assertFalse(completion(state))
        for _ in range(50):
            state.collect(
                self.world.create_item(data.PACKAGE_FRAGMENT_ITEM), prevent_sweep=True,
            )
        self.assertTrue(completion(state))


class TestHundredPercentAllClasses(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "goal": "hundred_percent",
        "enable_hidden_packages": True,
        "enable_rampages": True, "enable_stunt_jumps": True,
        "enable_emergency_vehicles": True,
        "enable_properties": True,
        "enable_robbable_stores": True,
        "enable_side_events": True,
    }

    def test_the_goal_does_not_demand_the_pickup_class(self) -> None:
        # This world constructs with enable_pickups off, which is the one
        # deliberate hole in "the goal requires every check class": the game's
        # completion stat never counted an ambient pickup, so demanding the class
        # would make the goal mean something the game itself does not. Pickups
        # stay a check class in every other respect, so the two lists differ by
        # exactly this one name and nothing else may drift out of the first.
        self.assertFalse(bool(self.world.options.enable_pickups.value))
        self.assertEqual(self.world.options.goal.current_key, "hundred_percent")
        self.assertNotIn("enable_pickups", HUNDRED_PERCENT_CLASS_OPTIONS)
        self.assertIn("enable_pickups", CHECK_CLASS_OPTIONS)
        self.assertIn("enable_pickups", UNCOUNTED_CLASS_OPTIONS)
        # Every check class is classified, and classified once. A class in
        # neither list is silently EXEMPT, since the goal iterates the demanded
        # list; a class in both would make the two disagree. And the registry is
        # where a class is born, so it is tied in too: a class added there and
        # not here would get locations and a toggle but reach no slot_data, no
        # tracker replay, and no goal precondition.
        self.assertEqual(
            set(HUNDRED_PERCENT_CLASS_OPTIONS) | set(UNCOUNTED_CLASS_OPTIONS),
            set(CHECK_CLASS_OPTIONS))
        self.assertEqual(
            set(HUNDRED_PERCENT_CLASS_OPTIONS) & set(UNCOUNTED_CLASS_OPTIONS),
            set())
        self.assertEqual(set(CHECK_CLASS_OPTIONS), set(CLASS_TOGGLE.values()))
        # The two uncounted lists name the same classes by different keys and
        # drive different halves of one contract: the options list drives the
        # goal's precondition, the keys list drives which locations the goal and
        # the client skip. Adding a class to the options list alone leaves its
        # checks required by the completion condition and waited on by the
        # client, which is a seed that generates and cannot be finished. The
        # registry already knows the pairing, so it is the tie.
        self.assertEqual(
            {data.optional_check_classes()[key][0] for key in UNCOUNTED_CLASS_KEYS},
            set(UNCOUNTED_CLASS_OPTIONS))


_STORY_ONLY_OPTIONS: dict = {
    "enable_hidden_packages": False,
    "enable_rampages": False, "enable_stunt_jumps": False,
    "enable_emergency_vehicles": False,
    "enable_properties": False,
    "enable_robbable_stores": False,
    "enable_side_events": False,
}

# A near-minimal pool that still generates. Story-only is refused on item math
# (see TestRejections), so this adds the one collectible class needed to give
# the story pool homes. Every world modifier adds pool items without adding
# checks, so this is the config their tests stack on.
_TIGHTEST_OPTIONS: dict = dict(_STORY_ONLY_OPTIONS, enable_robbable_stores=True)


# The items that satisfy the finale's asset prerequisite (the mandatory
# Printworks asset plus five optional ones), for tests whose subject is a
# different finale edge and needs the asset terms out of the way.
# The audit's mission chain: Death Row waits on Cortez's fourth and Diaz's
# fourth, and Rub Out hands the mansion over as Diaz's last, which is what the
# protection strand and everything behind it wait on. Progressives only, so a
# test whose subject is an area item or an ability still collects that itself and
# still sees it withheld.
_MANSION_CHAIN: list[str] = [
    "Progressive Rosenberg", "Progressive Cortez", "Progressive Diaz",
    "Progressive Death Row",
]

# What passing that chain takes besides the progressives: Death Row is played on
# the mainland, the Diaz missions want a weapon and the Cubans' boat, and the
# mansion missions behind them want a car. Tests whose subject is one of these
# collect it themselves instead.
_MANSION_CHAIN_COST: list[str] = [
    "Mainland Access", data.WEAPON_EQUIP_ITEM, data.SEA_VEHICLES_ITEM,
    data.LAND_VEHICLES_ITEM,
]

def _check_count(multiworld, player: int) -> int:
    # Locations with an address. The event locations carrying the audited island
    # routes have none, since passing a mission is not a check.
    return sum(1 for location in multiworld.get_locations(player)
               if location.address is not None)


_FINALE_ASSET_ITEMS: list[str] = [
    "Printworks Ownership", "Progressive Printworks",
    "Malibu Club Ownership", "Progressive Malibu Club",
    "Film Studio Ownership", "Progressive Film Studio",
    "Kaufman Cabs Ownership", "Progressive Kaufman Cabs",
    "Cherry Popper Ownership", "Progressive Cherry Popper",
    "Pole Position Ownership",
]


class TestTightestPool(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = dict(_TIGHTEST_OPTIONS)

    def test_solvable_with_the_tightest_pool(self) -> None:
        # A near-all-progression pool with almost no filler slack. The default
        # reachability tests already prove solvability; this asserts the world
        # generated at all and left the final mission as a real check.
        self.assertIn(
            data.FINAL_MISSION,
            {location.name for location in self.multiworld.get_locations(self.player)},
        )

    def test_nothing_is_granted_at_the_start(self) -> None:
        # No seed is rescued with starting inventory. This seed sets no
        # start_inventory_from_pool and no radio shuffle, the two things that
        # legitimately precollect, so it must start empty-handed.
        self.assertEqual(self.multiworld.precollected_items[self.player], [])


class TestUniversalTracker(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "goal": "hidden_packages",
        "hidden_packages_required": 30,
        "enable_properties": False,
    }

    def test_slot_data_carries_the_world_shaping_options(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["goal"], "hidden_packages")
        self.assertEqual(slot_data["hidden_packages_required"], 30)
        # The client counts received copies of this id for the hunt goal.
        self.assertEqual(
            slot_data["hidden_package_item_id"], ITEM_NAME_TO_ID[data.PACKAGE_FRAGMENT_ITEM],
        )
        # And watches this location being checked for the final-mission goal.
        self.assertEqual(
            slot_data["final_location_id"], LOCATION_NAME_TO_ID[data.FINAL_MISSION],
        )
        self.assertFalse(slot_data["enable_properties"])
        self.assertTrue(slot_data["enable_hidden_packages"])
        self.assertIn("shuffle_emergency_rewards", slot_data)
        self.assertIn("randomize_radio_stations", slot_data)
        self.assertIn("radio_start_station", slot_data)
        self.assertIn("shuffle_minimap", slot_data)
        self.assertIn("randomize_pickups", slot_data)
        self.assertIn("pickup_permutation", slot_data)
        self.assertIn("pickup_layout", slot_data)
        self.assertIn("ability_locks", slot_data)
        # The lock draws, like the radio and pickup draws above: chosen at
        # generation, so a regeneration has to replay them rather than reroll.
        self.assertIn("starting_ability_unlock", slot_data)
        self.assertIn("starting_content_unlock", slot_data)
        self.assertIn("starting_ability_item", slot_data)
        self.assertIn("starting_content_item", slot_data)
        # Carried so a tracker regeneration rebuilds the same filler/trap split.
        self.assertIn("trap_percentage", slot_data)
        for name in CHECK_CLASS_OPTIONS:
            self.assertIn(name, slot_data)

    def test_regeneration_restores_options_from_slot_data(self) -> None:
        # Stand in for a Universal Tracker regeneration: a different seed's
        # slot_data passed through must overwrite the options generate_early
        # would otherwise use.
        slot_data = {
            "goal": "hundred_percent",
            "hidden_packages_required": 80,
            "death_link": True,
            "shuffle_emergency_rewards": True,
            "randomize_radio_stations": True,
            "radio_start_station": 3,
            "shuffle_minimap": True,
            "randomize_pickups": True,
            "pickup_permutation": list(reversed(range(len(data.PICKUP_SLOTS)))),
            "ability_locks": ["vehicles", "wallet"],
            "trap_percentage": 40,
            "enable_hidden_packages": True,
            "enable_rampages": True, "enable_stunt_jumps": True,
            "enable_emergency_vehicles": True,
            "enable_properties": True,
            "enable_robbable_stores": True,
            "enable_side_events": True,
            "enable_pickups": True,
            "shuffle_shops": True,
        }
        self.multiworld.re_gen_passthrough = {self.game: slot_data}
        self.world.generate_early()
        self.assertEqual(self.world.options.goal.current_key, "hundred_percent")
        self.assertEqual(self.world.options.hidden_packages_required.value, 80)
        self.assertTrue(bool(self.world.options.death_link.value))
        self.assertTrue(bool(self.world.options.shuffle_emergency_rewards.value))
        self.assertEqual(self.world.options.trap_percentage.value, 40)
        self.assertTrue(bool(self.world.options.randomize_radio_stations.value))
        self.assertTrue(bool(self.world.options.shuffle_minimap.value))
        # The played seed's starting station replays instead of rerolling.
        self.assertEqual(self.world.radio_start_station, 3)
        # And so does the played seed's pickup layout.
        self.assertTrue(bool(self.world.options.randomize_pickups.value))
        self.assertEqual(
            self.world.pickup_permutation,
            list(reversed(range(len(data.PICKUP_SLOTS)))),
        )
        # The played seed's ability locks restore, so pool and rules match.
        self.assertEqual(self.world.options.ability_locks.value, {"vehicles", "wallet"})
        for name in CHECK_CLASS_OPTIONS:
            self.assertEqual(getattr(self.world.options, name).value, 1)


class TestRadioStationsOn(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"randomize_radio_stations": True}

    def test_one_start_station_and_eight_pool_items(self) -> None:
        pool = [item.name for item in self.multiworld.itempool
                if item.name in data.RADIO_STATION_ITEMS]
        precollected = [
            item.name for item in self.multiworld.precollected_items[self.player]
            if item.name in data.RADIO_STATION_ITEMS
        ]
        self.assertEqual(len(precollected), 1)
        self.assertEqual(len(pool), len(data.RADIO_STATION_ITEMS) - 1)
        self.assertEqual(sorted(pool + precollected), sorted(data.RADIO_STATION_ITEMS))
        # The precollected station is the seed's chosen start.
        self.assertIsNotNone(self.world.radio_start_station)
        self.assertEqual(
            precollected[0], data.RADIO_STATION_ITEMS[self.world.radio_start_station],
        )

    def test_stations_are_useful_never_progression(self) -> None:
        # Useful, never progression: no access rule may require one, and the
        # generator does not have to guarantee any particular station.
        for name in data.RADIO_STATION_ITEMS:
            self.assertEqual(ITEM_CLASSIFICATIONS[name], ItemClassification.useful, name)

    def test_slot_data_carries_the_radio_contract(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertTrue(slot_data["randomize_radio_stations"])
        self.assertEqual(slot_data["radio_start_station"], self.world.radio_start_station)
        self.assertEqual(slot_data["config_globals"][str(scm.RADIO_RANDOMIZED_GLOBAL)], 1)
        # Each station item counts into its unlock global, in engine station
        # id order, through the ordinary item_globals mechanism.
        item_globals = slot_data["item_globals"]
        for index, name in enumerate(data.RADIO_STATION_ITEMS):
            self.assertEqual(
                item_globals[str(ITEM_NAME_TO_ID[name])], scm.RADIO_UNLOCK_BASE + index,
            )

    def test_reserved_block_stays_below_the_marker_globals(self) -> None:
        # $9670 up is SCM-internal (marker handles and visibility flags, whose
        # bases live in add_markers.py); the reserved contract must never grow
        # into it. The district content unlocks took $9613..$9667, the finale warp
        # flag $9668 and the finale active flag $9669, which is why
        # add_markers.py's HANDLE_BASE moved with them: a reserved block growing
        # into the marker scratch would have the ASI writing over live marker
        # handles.
        #
        # Every number here is a mirror, so adding locations moves them all: the
        # reward block sits directly above the completion block, so a class
        # appended to the registry leaves the unlock and completion globals alone
        # and pushes everything from the rewards up by its own size.
        self.assertLess(scm.highest_reserved_global(), 9670)


class TestRadioStationsOff(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: randomize_radio_stations is off.

    def test_no_station_items_and_a_vanilla_config_flag(self) -> None:
        pool_names = {item.name for item in self.multiworld.itempool}
        precollected = {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        for name in data.RADIO_STATION_ITEMS:
            self.assertNotIn(name, pool_names, name)
            self.assertNotIn(name, precollected, name)
        slot_data = self.world.fill_slot_data()
        self.assertFalse(slot_data["randomize_radio_stations"])
        self.assertIsNone(slot_data["radio_start_station"])
        self.assertEqual(slot_data["config_globals"][str(scm.RADIO_RANDOMIZED_GLOBAL)], 0)


class TestRadioStationsTightestPool(WorldTestBase):
    # The tightest accepted pool plus the eight station items must still leave
    # every progression item a home. The inherited default tests prove the seed
    # fills and stays reachable.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = dict(_TIGHTEST_OPTIONS, randomize_radio_stations=True)


class TestMinimapShuffleOn(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"shuffle_minimap": True}

    def test_one_minimap_item_in_the_pool(self) -> None:
        minimaps = [item for item in self.multiworld.itempool
                    if item.name == data.MINIMAP_ITEM and item.player == self.player]
        self.assertEqual(len(minimaps), 1)

    def test_minimap_is_useful_never_progression(self) -> None:
        # Useful, never progression: no access rule requires the minimap, so
        # the generator owes it no reachability guarantee and it may land
        # anywhere, the very end of the seed included.
        self.assertEqual(
            ITEM_CLASSIFICATIONS[data.MINIMAP_ITEM], ItemClassification.useful,
        )

    def test_slot_data_carries_the_minimap_contract(self) -> None:
        # The ASI hides the radar disc while the shuffled flag is set and the
        # unlock global is zero, so the config stamp and the item mapping must
        # both travel.
        slot_data = self.world.fill_slot_data()
        self.assertTrue(slot_data["shuffle_minimap"])
        self.assertEqual(
            slot_data["config_globals"][str(scm.MINIMAP_SHUFFLED_GLOBAL)], 1,
        )
        self.assertEqual(
            slot_data["item_globals"][str(ITEM_NAME_TO_ID[data.MINIMAP_ITEM])],
            scm.MINIMAP_UNLOCK_GLOBAL,
        )


class TestMinimapShuffleOff(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: shuffle_minimap is off.

    def test_no_minimap_item_and_a_vanilla_config_flag(self) -> None:
        pool_names = {item.name for item in self.multiworld.itempool}
        precollected = {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        self.assertNotIn(data.MINIMAP_ITEM, pool_names)
        self.assertNotIn(data.MINIMAP_ITEM, precollected)
        slot_data = self.world.fill_slot_data()
        self.assertFalse(slot_data["shuffle_minimap"])
        self.assertEqual(
            slot_data["config_globals"][str(scm.MINIMAP_SHUFFLED_GLOBAL)], 0,
        )


class TestMinimapTightestPool(WorldTestBase):
    # The tightest accepted pool plus the Minimap item: the extra useful item
    # must still leave every progression item a home. The inherited default
    # tests prove the seed fills and stays reachable.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = dict(_TIGHTEST_OPTIONS, shuffle_minimap=True)


class TestPickupRandomizerOn(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"randomize_pickups": True}

    def test_permutation_conserves_the_vanilla_multiset(self) -> None:
        # A true permutation: every vanilla item lands somewhere exactly once,
        # so the world holds the same count of every weapon, heart, armor,
        # pill, and bribe as vanilla.
        permutation = self.world.pickup_permutation
        self.assertIsNotNone(permutation)
        self.assertEqual(sorted(permutation), list(range(len(data.PICKUP_SLOTS))))

    def test_no_bribe_lands_on_a_shop_slot(self) -> None:
        # An in-shop bribe would be free, because a bribe's weapon-type field is
        # zero and so is the cost table's zeroth entry, and each bribe takes a
        # star off the wanted level, so a free one that respawns is an endless
        # supply of them. The permutation keeps bribes off shop-type slots.
        for slot_index, source_index in enumerate(self.world.pickup_permutation):
            if data.PICKUP_SLOTS[slot_index][3] == data.PICKUP_SHOP_TYPE:
                self.assertNotEqual(
                    data.PICKUP_SLOTS[source_index][4], data.PICKUP_BRIBE_MODEL,
                    slot_index,
                )

    def test_slot_data_carries_the_layout(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertTrue(slot_data["randomize_pickups"])
        self.assertEqual(slot_data["pickup_permutation"], self.world.pickup_permutation)
        layout = slot_data["pickup_layout"]
        # The ambient slots, then Phil's four stands, which ride the same layout
        # because they are pickups even though the shop class owns them.
        self.assertEqual(len(layout),
                         len(data.PICKUP_SLOTS) + len(data.SHOP_STAND_SLOTS))
        layout = layout[:len(data.PICKUP_SLOTS)]
        for slot_index, row in enumerate(layout):
            x, y, z, pickup_type, _model, _ammo = data.PICKUP_SLOTS[slot_index]
            source = data.PICKUP_SLOTS[self.world.pickup_permutation[slot_index]]
            # The seventh element is the completion global of the check on this
            # slot, and zero here because the class is off in this seed: the
            # shuffle alone makes no slot a check. The eighth is the price index
            # a stand charges from while it wears the marker, and no ambient slot
            # carries one: that term belongs to the shop class alone.
            self.assertEqual(row,
                             [x, y, z, pickup_type, source[4], source[5], 0, 0])

    def test_forced_shop_conflict_is_swapped_away(self) -> None:
        # The fix branch only runs when the shuffle happens to drop a bribe on
        # a shop slot, so force that exact layout and reroll: the bribe must
        # trade places with a non-bribe on a non-shop slot while the result
        # stays a permutation.
        slots = data.PICKUP_SLOTS
        shop_slot = next(
            index for index, slot in enumerate(slots)
            if slot[3] == data.PICKUP_SHOP_TYPE
        )
        bribe_slot = next(
            index for index, slot in enumerate(slots)
            if slot[4] == data.PICKUP_BRIBE_MODEL
        )
        forced = list(range(len(slots)))
        forced[shop_slot], forced[bribe_slot] = forced[bribe_slot], forced[shop_slot]

        class ForcedShuffleRandom(random.Random):
            def shuffle(self, sequence: list) -> None:
                sequence[:] = forced

        self.world.random = ForcedShuffleRandom()
        self.world._choose_pickup_permutation(None)
        permutation = self.world.pickup_permutation
        self.assertEqual(sorted(permutation), list(range(len(slots))))
        for slot_index, source_index in enumerate(permutation):
            if slots[slot_index][3] == data.PICKUP_SHOP_TYPE:
                self.assertNotEqual(
                    slots[source_index][4], data.PICKUP_BRIBE_MODEL, slot_index,
                )

    def test_spoiler_names_every_slot(self) -> None:
        handle = io.StringIO()
        self.world.write_spoiler(handle)
        lines = [line for line in handle.getvalue().splitlines() if ": " in line]
        self.assertEqual(len(lines), len(data.PICKUP_SLOTS))

    def test_slot_table_invariants(self) -> None:
        # Every slot has a named model, a known pickup type, and non-negative
        # ammo, and slots sit farther apart than the ASI's matching tolerance,
        # so a position match is always unambiguous.
        for _x, _y, _z, pickup_type, model, ammo in data.PICKUP_SLOTS:
            self.assertIn(model, data.PICKUP_MODEL_NAMES)
            self.assertIn(pickup_type, (1, 2, 15))
            self.assertGreaterEqual(ammo, 0)
        positions = [slot[:3] for slot in data.PICKUP_SLOTS]
        closest = min(
            math.dist(positions[first], positions[second])
            for first in range(len(positions))
            for second in range(first + 1, len(positions))
        )
        self.assertGreater(closest, 2.0)
        # The bribe fix always has somewhere to swap to: strictly more
        # non-shop slots than bribes, so a non-shop slot holding a non-bribe
        # always exists.
        non_shop_slots = sum(
            1 for slot in data.PICKUP_SLOTS if slot[3] != data.PICKUP_SHOP_TYPE
        )
        bribes = sum(
            1 for slot in data.PICKUP_SLOTS if slot[4] == data.PICKUP_BRIBE_MODEL
        )
        self.assertGreater(non_shop_slots, bribes)

    def test_the_bribe_help_text_is_retired(self) -> None:
        # The vanilla bribe tutorial fires on whatever model sits on a bribe
        # spot, so with the shuffle on it describes an item that is not there.
        # Stamping the vanilla already-shown flag retires it for the seed.
        config = self.world.fill_slot_data()["config_globals"]
        self.assertEqual(config[str(data.BRIBE_HELP_SHOWN_FLAG)], 1)



class TestPickupRandomizerOff(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: randomize_pickups is off.

    def test_no_permutation_and_an_empty_layout(self) -> None:
        # Off means fully vanilla: no permutation rolls and the ASI receives
        # an empty layout, so it never touches the pickup pool.
        self.assertIsNone(self.world.pickup_permutation)
        slot_data = self.world.fill_slot_data()
        self.assertFalse(slot_data["randomize_pickups"])
        self.assertIsNone(slot_data["pickup_permutation"])
        self.assertEqual(slot_data["pickup_layout"], [])
        # And the bribe help text stays vanilla, since the bribes are where the
        # text says they are.
        self.assertNotIn(str(data.BRIBE_HELP_SHOWN_FLAG), slot_data["config_globals"])
        handle = io.StringIO()
        self.world.write_spoiler(handle)
        self.assertEqual(handle.getvalue(), "")


class TestHundredPercentWithPickups(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "goal": "hundred_percent",
        "enable_hidden_packages": True,
        "enable_rampages": True, "enable_stunt_jumps": True,
        "enable_emergency_vehicles": True,
        "enable_properties": True,
        "enable_robbable_stores": True,
        "enable_side_events": True,
        "enable_pickups": True,
    }

    def test_slot_data_names_the_locations_the_goal_skips(self) -> None:
        # The world stopped counting these toward the goal, but the client is what
        # sends it, so the ids have to travel. Without them the client waits for
        # 110 checks the seed does not need, and one it cannot collect holds the
        # goal forever.
        uncounted = self.world.fill_slot_data()["goal_uncounted_locations"]
        self.assertEqual(
            set(uncounted),
            {LOCATION_NAME_TO_ID[name] for name in data.PICKUP_NAMES})

    def test_the_goal_ignores_the_pickups_even_with_the_class_on(self) -> None:
        # This goal is the GAME's 100 percent, so it asks for what the game's
        # own stat counts and nothing more. The stat never counted an ambient
        # pickup, so the class is out of the goal on both counts: not required to
        # be on, and not counted when it is. Turning it on just adds extra checks.
        self.assertEqual(self.world.options.goal.current_key, "hundred_percent")
        for name in data.PICKUP_NAMES:
            self.assertTrue(self.world._location_enabled(name), name)
        # And they really are in the seed, not merely enabled in principle.
        placed = {location.name
                  for location in self.multiworld.get_locations(self.player)}
        for name in data.PICKUP_NAMES:
            self.assertIn(name, placed, name)

        # Asked of the condition rather than of the location list, because the
        # assertions above would stay green if a future edit put the pickups back
        # into the goal. Withholding any single pickup must NOT stop the goal
        # being met; withholding a mission must.
        condition = self.multiworld.completion_condition[self.player]

        class ReachesAllBut:
            def __init__(self, withheld: str) -> None:
                self.withheld = withheld

            def can_reach_location(self, name: str, _player: int) -> bool:
                return name != self.withheld

        for name in data.PICKUP_NAMES:
            self.assertTrue(condition(ReachesAllBut(name)), name)
        # And the goal still means something: a counted check held back does stop
        # it, so this is not passing because the condition is trivially true.
        self.assertFalse(condition(ReachesAllBut(data.FINAL_MISSION)))


# The one shop item whose stock, not whose shop, waits on the crossing.
CROSSING_STOCKED_SHOP_ITEM = "Shop - Vice Point - Ammu-Nation - Sniper Rifle"

# The items a shop only racks once a mission has passed, read off the same table
# the rules read, since the point of these tests is what reaching one costs and
# not which rows the table holds; test_a_mission_a_check_waits_on_has_an_event
# is where the membership is written out.
STOCK_GATED_SHOP_ITEMS = frozenset(
    data.shop_data.shop_item_name(item) for item in data.shop_data.SHOP_ITEMS
    if (item.thread, item.script_global) in data.shop_data.SHOP_STOCK_MISSIONS
)


class TestShops(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"shuffle_shops": True, "ability_locks": ["wallet"]}

    def test_the_shop_locations_exist(self) -> None:
        names = {location.name
                 for location in self.multiworld.get_locations(self.player)}
        for name in data.shop_data.SHOP_ITEM_NAMES:
            self.assertIn(name, names)
        # 32 things the six script-thread shops sell, plus the four in-shop
        # pickups Boomshine Saigon racks at Phil's Place, which the engine sells
        # and the pickup layout reaches instead.
        self.assertEqual(len(data.shop_data.SHOP_ITEM_NAMES), 36)
        self.assertEqual(len(data.SHOP_STAND_SLOTS), 4)

    def test_phils_stands_price_from_their_own_weapon_type(self) -> None:
        # The one thing the shop class promises that the pickup layout has to
        # carry: a pending stand charges what the stand charges. Every other
        # pending slot prices at the ASI's own figure for the marker, so a stand
        # whose price index went missing would quietly discount three of these
        # four by thousands.
        layout = self.world.fill_slot_data()["pickup_layout"]
        stands = layout[len(data.PICKUP_SLOTS):]
        self.assertEqual(len(stands), 4)
        for row, stand in zip(stands, data.SHOP_STAND_SLOTS, strict=True):
            item = data.SHOP_STAND_ITEMS[stand[6]]
            self.assertNotEqual(row[6], 0, item.display_name)
            self.assertEqual(row[7], item.weapon_type, item.display_name)
        # Every ambient row carries none, so the term is the stands' alone.
        for row in layout[:len(data.PICKUP_SLOTS)]:
            self.assertEqual(row[7], 0)
        # The prices themselves are the game's, read out of CostOfWeapon rather
        # than invented, and the dearest of them is what makes the override
        # worth having: the marker's own price is a thousand.
        prices = {item.display_name: item.price
                  for item in data.SHOP_STAND_ITEMS.values()}
        self.assertEqual(prices, {"M60": 8000, "Rocket Launcher": 8000,
                                  "Minigun": 10000, "Remote Grenades": 1000})

    def test_stock_the_crossing_opens_gates_on_the_crossing(self) -> None:
        # Reaching a shop and it having the thing in stock are two questions.
        # The Vice Point sniper stocks off the flag the mainland crossing sets,
        # so it must gate on Mainland Access even though its shop is on the
        # starting island. Left start-island the fill can hide Mainland Access
        # itself behind it, and the seed cannot be finished.
        self.assertEqual(LOCATION_REGIONS[CROSSING_STOCKED_SHOP_ITEM],
                         data.REGION_MAINLAND)
        self.collect_by_name([data.WALLET_ITEM])
        self.assertFalse(
            self.can_reach_location(CROSSING_STOCKED_SHOP_ITEM),
            "the sniper is reachable with the Wallet alone, before the "
            "mainland opens")
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location(CROSSING_STOCKED_SHOP_ITEM))

    def test_every_crossing_stocked_key_names_a_real_item(self) -> None:
        # A key matching no row would silently do nothing, and the unwinnable
        # placement it exists to stop would be back.
        rows = {(item.thread, item.script_global)
                for item in data.shop_data.SHOP_ITEMS}
        self.assertTrue(data.shop_data.CROSSING_STOCKED_ITEMS)
        self.assertLessEqual(data.shop_data.CROSSING_STOCKED_ITEMS, rows)

    def test_only_that_one_start_island_item_waits_on_the_crossing(self) -> None:
        # The override is one item, not a rule about Vice Point: its five
        # neighbours on the same wall are start-island checks.
        waiting = {data.shop_data.shop_item_name(item)
                   for item in data.shop_data.SHOP_ITEMS
                   if data.shop_data.SHOP_DISTRICTS[item.thread]
                   not in data.MAINLAND_DISTRICTS
                   and data.shop_item_region(item) == data.REGION_MAINLAND}
        self.assertEqual(waiting, {CROSSING_STOCKED_SHOP_ITEM})

    def test_the_shop_names_are_unique(self) -> None:
        # Two rows sharing a display name inside one shop would be one location
        # and one row that is silently not a check, which the count and the
        # membership above both survive.
        names = data.shop_data.SHOP_ITEM_NAMES
        self.assertEqual(len(set(names)), len(names))

    def test_a_shop_item_needs_the_wallet_to_be_reached(self) -> None:
        # The tables are one thing and reaching a Location is another. All 32,
        # not a sample: filtering to one island is what left the mainland stands
        # unclaimed in the pickup class.
        self.collect_by_name(["Mainland Access"])
        for name in data.shop_data.SHOP_ITEM_NAMES:
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name([data.WALLET_ITEM])
        # Thirteen more wait on the mission that racks them, which no item can
        # hand over, so the wallet opens the other nineteen and stops there.
        for name in data.shop_data.SHOP_ITEM_NAMES:
            self.assertEqual(self.can_reach_location(name),
                             name not in STOCK_GATED_SHOP_ITEMS, name)

    def test_a_mainland_shop_also_needs_the_crossing(self) -> None:
        # The eleven Downtown and Little Havana items wait on the crossing as
        # well, so the Wallet alone leaves them out of reach. So does the Vice
        # Point sniper, whose shop is on the starting island but whose stock is
        # not.
        self.collect_by_name([data.WALLET_ITEM])
        for name in data.shop_data.SHOP_ITEM_NAMES:
            waits = (" - Downtown - " in name or " - Little Havana - " in name
                     or name == CROSSING_STOCKED_SHOP_ITEM
                     or name in STOCK_GATED_SHOP_ITEMS)
            self.assertEqual(self.can_reach_location(name), not waits, name)

    def test_a_stock_gated_item_opens_with_its_mission(self) -> None:
        # The gate is the mission, not the shop: the Ocean Beach shotgun sits on
        # the starting island beside two items the wallet alone opens, and waits
        # for Mall Shootout because that is what puts it on the rack.
        self.collect_by_name([data.WALLET_ITEM])
        shotgun = "Shop - Ocean Beach - Ammu-Nation - Shotgun"
        self.assertIn(shotgun, STOCK_GATED_SHOP_ITEMS)
        self.assertFalse(self.can_reach_location(shotgun))
        # Two Cortez progressives reach Mall Shootout, and passing it takes the
        # car and the weapon its own row names.
        self.collect_by_name(["Progressive Cortez", "Progressive Cortez"])
        self.assertTrue(self.can_reach_location(shotgun))

    def test_a_shop_sits_on_the_island_it_stands_in(self) -> None:
        # Three of the seven shops are on the mainland, so fifteen of the
        # thirty six wait on the crossing, and the sniper waits with them for its
        # stock rather than its island. Written out rather than counted from the
        # same table the code reads, so a district moving is a failure here.
        mainland = {name for name in data.shop_data.SHOP_ITEM_NAMES
                    if " - Downtown - " in name or " - Little Havana - " in name
                    or " - Little Haiti - " in name}
        self.assertEqual(len(mainland), 15)
        for name in data.shop_data.SHOP_ITEM_NAMES:
            region = LOCATION_REGIONS[name]
            expected = (data.REGION_MAINLAND
                        if name in mainland or name == CROSSING_STOCKED_SHOP_ITEM
                        else data.REGION_VICE_CITY)
            self.assertEqual(region, expected, name)

    def test_the_class_flag_reaches_the_script(self) -> None:
        # The script reads this before it hides what a shop sells. Without it the
        # withholding would key on the completion global alone, which every seed
        # allocates, and a seed without the class would still change the world.
        flags = self.world.fill_slot_data()["config_globals"]
        self.assertEqual(flags[str(scm.SHOPS_ENABLED_GLOBAL)], 1)

    def test_every_shop_item_wants_the_wallet(self) -> None:
        # A shop charges, and the wallet lock pins the balance to zero, so all
        # thirty two wait on the Wallet item while that key is selected.
        requirements = data.location_ability_requirements()
        for name in data.shop_data.SHOP_ITEM_NAMES:
            self.assertIn(name, requirements, name)
            self.assertIn(data.WALLET_ITEM, requirements[name], name)


class TestShopsOff(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"shuffle_shops": False}

    def test_the_class_flag_is_zero_and_no_locations_exist(self) -> None:
        # A disabled check class behaves fully vanilla in game, which for the
        # shops means the flag the script reads is zero: no marker on the wall
        # and a first purchase that pays out like it always did.
        flags = self.world.fill_slot_data()["config_globals"]
        self.assertEqual(flags[str(scm.SHOPS_ENABLED_GLOBAL)], 0)
        names = {location.name
                 for location in self.multiworld.get_locations(self.player)}
        for name in data.shop_data.SHOP_ITEM_NAMES:
            self.assertNotIn(name, names)

    def test_no_layout_at_all_leaves_phils_stands_alone(self) -> None:
        # Phil's four are in-shop pickups, so the pickup layout is the only
        # thing that could put a marker on them and no script flag reaches them.
        # This seed has every pickup option off as well, so the layout is empty
        # and the ASI enforces nothing: the stands are the game's, priced and
        # stocked by it. The composed case, a layout emitted for the pickup
        # options with the shop class still off, is pinned where those options
        # are on.
        self.assertEqual(self.world.fill_slot_data()["pickup_layout"], [])


class TestHundredPercentWithShops(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "goal": "hundred_percent",
        "enable_hidden_packages": True,
        "enable_rampages": True, "enable_stunt_jumps": True,
        "enable_emergency_vehicles": True,
        "enable_properties": True,
        "enable_robbable_stores": True,
        "enable_side_events": True,
        "shuffle_shops": True,
    }

    def test_the_goal_skips_the_shop_locations(self) -> None:
        # The game's percentage never counted buying a shotgun, so the goal does
        # not wait on one. The ids still have to travel, since the client is what
        # decides the goal is met and one uncollectable check would hold it.
        uncounted = self.world.fill_slot_data()["goal_uncounted_locations"]
        self.assertEqual(
            set(uncounted),
            {LOCATION_NAME_TO_ID[name]
             for name in data.shop_data.SHOP_ITEM_NAMES})


class TestPickupChecksOn(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_pickups": True}

    def test_every_ambient_slot_is_a_location(self) -> None:
        # One check per slot, so the count is the slot table's count and not a
        # number written twice.
        self.assertEqual(len(data.PICKUP_NAMES), len(data.PICKUP_SLOTS))
        for name in data.PICKUP_NAMES:
            self.assertIn(name, LOCATION_NAME_TO_ID, name)

    def test_the_names_are_unique(self) -> None:
        # A district and an item name a slot, and 55 of the 110 share both, so
        # the colliding stems carry a suffix. Two slots sharing a name would be
        # one location and the other slot would be no check at all.
        self.assertEqual(len(set(data.PICKUP_NAMES)), len(data.PICKUP_NAMES))

    def test_an_ordinary_pickup_needs_only_its_area(self) -> None:
        # Walking over a pickup takes no ability, so an ordinary slot asks for the
        # island it stands on and nothing else. Asserted against the region rather
        # than a list of items, because naming the items would restate the area
        # rules here and pass while saying nothing about the pickups.
        #
        # Ordinary means the pay stands are out, since those want the wallet, and
        # so are the three inside Diaz's mansion, which want Rub Out passed: an
        # island is not the whole of what reaching those costs. The audit's
        # several-routes slots stay in: with no ability key selected most of them
        # have a route of ability items alone, which is then free, and the four
        # whose other route names a mission keep a threshold that their own
        # region already satisfies, since all four are mainland slots and the
        # mainland is one of the sources the air route resolves to.
        ordinary = [(name, data.pickup_region(index))
                    for index, name in enumerate(data.PICKUP_NAMES)
                    if index not in data.PICKUP_PAY_STAND_INDICES
                    and index not in data.PICKUP_MISSION_REQUIREMENTS]
        self.assertEqual({region for _name, region in ordinary},
                         {data.REGION_VICE_CITY, data.REGION_MAINLAND,
                          data.REGION_STARFISH})

        def check(stage: str) -> None:
            for name, region in ordinary:
                self.assertEqual(
                    self.can_reach_location(name), self.can_reach_region(region),
                    f"{name} does not follow {region} {stage}")

        check("with nothing collected")
        self.collect_by_name(["Mainland Access"])
        check("after the mainland opens")
        for region in (data.REGION_VICE_CITY, data.REGION_MAINLAND,
                       data.REGION_STARFISH):
            self.assertTrue(self.can_reach_region(region), region)

    def test_the_mansion_pickups_wait_for_rub_out(self) -> None:
        # The slots that wait on a mission are the exception to the rule above:
        # reaching the island is not enough. Three are inside Diaz's mansion,
        # where the island is open and the front door is not, and six are the
        # permanent creations, which are not in the world at all until their
        # mission passes. Every one of them still refuses on the island alone,
        # which is what this walks.
        self.assertEqual(len(data.PICKUP_MISSION_REQUIREMENTS), 9)
        self.collect_by_name(["Mainland Access", "Starfish Island Access"])
        # The seven Rub Out holds: the three behind the mansion door and the four
        # it leaves in the courtyard. The other two wait on The Job and on
        # Trojan Voodoo, which are other strands and other tests; what this one
        # walks is the mission term doing its work at all.
        mansion = [data.pickup_name(index) for index, missions
                   in data.PICKUP_MISSION_REQUIREMENTS.items()
                   if missions == ["Rub Out"]]
        self.assertEqual(len(mansion), 7)
        for name in mansion:
            self.assertTrue(self.can_reach_region(LOCATION_REGIONS[name]), name)
            self.assertFalse(self.can_reach_location(name), name)
        # Rub Out is Diaz's fifth, and passing it is what the event stands for.
        self.collect_by_name(["Progressive Diaz"] * 5
                             + ["Progressive Cortez"] * 4
                             + ["Progressive Death Row"])
        for name in mansion:
            self.assertTrue(self.can_reach_location(name), name)

    def test_slot_data_carries_the_class(self) -> None:
        # The played seed has to record the setting, for a tracker regeneration
        # and for whatever the client chooses to forward. Forwarding it to the
        # ASI is a separate step in client/context.py and belongs to the mod half.
        self.assertTrue(self.world.fill_slot_data()["enable_pickups"])


class TestPickupReach(WorldTestBase):
    # The pickup checks with every ability locked, which is where the audit's
    # reach terms bind hardest. TestDefault covers the other case, the routes
    # that still bind with no key selected because a source is not an ability.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "enable_pickups": True,
        "ability_locks": _ALL_ABILITY_LOCKS,
    }

    def test_the_audited_pickups_need_what_reaching_them_takes(self) -> None:
        # The reach terms the pickup audit added. The counts are pinned because
        # the other ninety-odd slots carrying nothing is the claim that matters:
        # a slot with no term is one the audit walked and found free, not one
        # nobody looked at.
        self.assertEqual(len(data.PICKUP_ABILITY_REQUIREMENTS), 4)
        self.assertEqual(len(data.PICKUP_ABILITY_ALTERNATIVES), 14)
        for index, items in data.PICKUP_ABILITY_REQUIREMENTS.items():
            name = data.pickup_name(index)
            with self.subTest(pickup=name):
                for item in items:
                    self.assertIn(item, data.LOCATION_ABILITY_REQUIREMENTS[name])
        # The Viceport sniper is the one slot in both tables: on the bridge rail,
        # so a jump outright and then either a car to jump from or a run-up.
        sniper = data.pickup_name(41)
        self.assertIn(data.JUMP_ITEM, data.LOCATION_ABILITY_REQUIREMENTS[sniper])
        self.assertEqual(data.LOCATION_ABILITY_ALTERNATIVES[sniper],
                         [[data.LAND_VEHICLES_ITEM], [data.SPRINT_ITEM]])
        self.collect_by_name(["Mainland Access", data.JUMP_ITEM])
        self.assertFalse(self.can_reach_location(sniper))
        self.collect_by_name([data.SPRINT_ITEM])
        self.assertTrue(self.can_reach_location(sniper))

    def test_the_leaf_links_pickups_take_the_same_five_ways_in(self) -> None:
        # The three ambient slots inside the golf course carry the package
        # table's routes, so the wall is one fact and not two.
        inside = [data.pickup_name(index) for index in (33, 59, 85)]
        for name in inside:
            self.assertEqual(data.LOCATION_ABILITY_ALTERNATIVES[name],
                             data.LEAF_LINKS_ROUTES)
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name([data.JUMP_ITEM])
        for name in inside:
            self.assertTrue(self.can_reach_location(name), name)

    def test_a_roof_pickup_takes_the_helicopter_or_the_mission(self) -> None:
        # Four slots the audit reaches by air or by the mission that leaves an
        # aircraft standing there. The mission side is what makes them worth
        # writing down: with the vehicles key selected and no helicopter placed,
        # the mission is the only way and a bare Air Vehicles term would have hidden
        # that.
        roofs = {
            data.pickup_name(65): "G-spotlight",
            data.pickup_name(66): "Trojan Voodoo",
            data.pickup_name(69): "Loose Ends",
            data.pickup_name(87): "G-spotlight",
        }
        self.collect_by_name(["Mainland Access"])
        for name, mission in roofs.items():
            with self.subTest(pickup=name):
                self.assertEqual(
                    data.LOCATION_ABILITY_ALTERNATIVES[name],
                    [[data.AIR_VEHICLES_ITEM],
                     [data.mission_passed_item_name(mission)]])
                self.assertIn(mission, data.ROUTE_MISSIONS)
                self.assertFalse(self.can_reach_location(name), name)
        # The mission half first, with no helicopter anywhere, since that is the
        # half a bare Air Vehicles term would have hidden. Trojan Voodoo is the
        # cheapest of the three: Umberto's last, behind Auntie Poulet's third.
        haitian_factory = data.pickup_name(66)
        self.collect_by_name(
            ["Progressive Umberto Robina"] * 4
            + ["Progressive Auntie Poulet"] * 3
            + [data.LAND_VEHICLES_ITEM, data.SEA_VEHICLES_ITEM,
               data.WEAPON_EQUIP_ITEM])
        self.assertTrue(self.can_reach_location(haitian_factory))
        for name in roofs:
            if name != haitian_factory:
                self.assertFalse(self.can_reach_location(name), name)
        # And the helicopter opens the other three without their missions.
        self.collect_by_name([data.AIR_VEHICLES_ITEM])
        for name in roofs:
            self.assertTrue(self.can_reach_location(name), name)


class TestExclusionSeam(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_pickups": True}

    def test_an_excluded_class_is_not_counted_as_room(self) -> None:
        # Nothing is excluded today, so all four call sites of
        # _location_excluded are dead branches. They are the sites a future
        # excluded class depends on, and missing one of them cost two blockers:
        # a class kept out of the fill while still counted as somewhere
        # progression can go turns a clean refusal into a FillError.
        #
        # So the seam is pinned directly rather than through a configuration
        # sweep, which is what the deleted parity test tried to do and which no
        # longer works now that turning pickups on legitimately changes outcomes.
        pickups = frozenset(data.PICKUP_NAMES)
        world = self.world

        def excluded_none(_name: str) -> bool:
            return False

        def excluded_pickups(name: str) -> bool:
            return name in pickups

        with patch.object(type(world), "_location_excluded",
                          staticmethod(excluded_none)):
            base_free = world._free_start_location_count()
            base_opener = world._start_locations_opened_by(
                data.LAND_VEHICLES_ITEM, world._location_rules(),
                self.multiworld.get_all_state(False))

        with patch.object(type(world), "_location_excluded",
                          staticmethod(excluded_pickups)):
            free = world._free_start_location_count()
            opener = world._start_locations_opened_by(
                data.LAND_VEHICLES_ITEM, world._location_rules(),
                self.multiworld.get_all_state(False))

        # Sphere-0 room drops by the start-island pickups, and the opener score
        # with it: an excluded location is not room for progression, so neither
        # count may include it.
        # Start-island slots that are sphere-0 room, which is not the same as
        # start-island slots: the knife outside the Malibu Club stands on the
        # start island and is not room for anything until The Job has passed,
        # because until then it is not in the world.
        start_island = sum(1 for index in range(data.PICKUP_COUNT)
                           if data.pickup_region(index) == data.REGION_VICE_CITY
                           and index not in data.PICKUP_MISSION_REQUIREMENTS)
        self.assertGreater(start_island, 0)
        self.assertEqual(base_free - free, start_island)
        self.assertLess(opener, base_opener)


class TestPickupsAreOrdinaryLocations(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_pickups": True}

    def test_a_pickup_may_hold_anything_the_fill_puts_there(self) -> None:
        # They were excluded while they claimed to sit in the start region: a seed
        # must not need an item behind a claim. They sit on their real island now,
        # which test_no_pickup_sits_on_the_wrong_island verifies for all 110, so
        # they are ordinary locations and the fill may use them like any other.
        pickups = frozenset(data.PICKUP_NAMES)
        placed = [location for location in self.multiworld.get_locations(self.player)
                  if location.name in pickups]
        self.assertEqual(len(placed), len(data.PICKUP_NAMES))
        for location in placed:
            self.assertEqual(location.progress_type, LocationProgressType.DEFAULT,
                             location.name)

        distribute_items_restrictive(self.multiworld)
        for location in placed:
            self.assertIsNotNone(location.item, location.name)
        self.assertTrue(self.multiworld.can_beat_game())


class TestPickupChecksPayStands(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_pickups": True, "ability_locks": ["wallet"]}

    def test_a_pay_stand_needs_the_wallet(self) -> None:
        # The ten in-shop stands charge for what they give, so their checks wait
        # on the Wallet while that key is selected. The amount never gates: the
        # term is holding the wallet at all.
        # All ten, not the four on the start island: filtering by region left the
        # six mainland stands with no claim at all, which is the shape of gap
        # that hid in the ordinary-slot test too.
        stands = [data.pickup_name(index)
                  for index in sorted(data.PICKUP_PAY_STAND_INDICES)]
        self.assertEqual(len(stands), 10)
        self.collect_by_name(["Mainland Access"])
        for name in stands:
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name([data.WALLET_ITEM])
        for name in stands:
            self.assertTrue(self.can_reach_location(name), name)


class TestPickupChecksWithoutTheWalletKey(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_pickups": True, "ability_locks": []}

    def test_a_pay_stand_asks_for_nothing_when_the_key_is_off(self) -> None:
        # Toggle semantics: an unselected ability key means no lock, no item, and
        # no access rule naming that item. So with the wallet key off the ten
        # stands are ordinary pickups, reachable from their area alone, and Wallet
        # is in no pool for a rule to name.
        pool = {item.name for item in self.multiworld.itempool}
        self.assertNotIn(data.WALLET_ITEM, pool)
        # All ten, like the sibling test: filtering by region left the six
        # mainland stands with no claim at all.
        stands = [data.pickup_name(index)
                  for index in sorted(data.PICKUP_PAY_STAND_INDICES)]
        self.assertEqual(len(stands), 10)
        self.collect_by_name(["Mainland Access"])
        for name in stands:
            self.assertTrue(self.can_reach_location(name), name)


class TestPickupDistrictTable(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_pickups": True}

    def test_the_district_table_covers_every_slot(self) -> None:
        # Both tables are keyed by slot index and neither is derived from the
        # other, so either being the wrong length silently renames or misplaces
        # every slot after the gap. data.py asserts both counts at import, which
        # is what actually stops a bad table being used; this names them where
        # the assert message names a count, and covers the names as well.
        self.assertEqual(len(district_data.PICKUP_DISTRICTS),
                         len(data.PICKUP_SLOTS))
        self.assertEqual(len(data.PICKUP_NAMES), len(data.PICKUP_SLOTS))
        for district in district_data.PICKUP_DISTRICTS:
            self.assertIn(district, district_data.DISTRICTS, district)

    def test_no_pickup_sits_on_the_wrong_island(self) -> None:
        # The district table is the hand audit's, and through the region it
        # decides which island gate a check waits behind. An
        # intra-island error only misnames a location; a cross-island one puts a
        # check in logic on the start island while the pickup itself sits behind
        # Mainland Access, which is a seed that cannot be finished.
        #
        # So the region is pinned against the audited anchors the table was
        # derived from, the 100 packages and the 35 rampages: every slot must
        # agree with its NEAREST anchor, which is a stronger claim than the
        # weighted derivation makes and holds for all 110 today. The hand audit
        # may move a district freely within a region; moving one between regions
        # reddens this, which includes moving a slot between Starfish Island and
        # the rest of the start island, since Starfish is its own region and its
        # own gate.
        coords = scm.package_coords()
        anchors = [
            (coords[key], district) for key, district
            in zip(sorted(coords), district_data.PACKAGE_DISTRICTS, strict=True)
        ] + [
            (list(point), district) for point, district
            in zip(district_data.RAMPAGE_COORDS, district_data.RAMPAGE_DISTRICTS,
                   strict=True)
        ]
        for index, (x, y, z, _pickup_type, _model, _ammo) in enumerate(
                data.PICKUP_SLOTS):
            here = (x, y, z)
            _, nearest = min(
                (math.dist(here, (point[0], point[1], point[2])), district)
                for point, district in anchors
            )
            self.assertEqual(
                data.pickup_region(index), data.district_region(nearest),
                f"slot {index} ({data.pickup_name(index)}) is on a different "
                f"island from its nearest anchor, in {nearest}",
            )


class TestPickupChecksOff(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: enable_pickups is off.

    def test_the_class_is_offered_and_reported(self) -> None:
        # Offered like any other class, and reported by the mod, so a seed with it
        # on plays. Nothing about it is gated behind a flag any more: the slots sit
        # on their verified island and hold whatever the fill puts there.
        self.assertTrue(data.MOD_REPORTS_PICKUPS)
        self.assertEqual(EnablePickups.visibility, Visibility.all)
        self.assertEqual(EnableSideEvents.visibility, Visibility.all)

    def test_no_slot_is_a_location(self) -> None:
        # A disabled class contributes no locations, so the slots stay ambient
        # pickups and nothing else.
        placed = {location.name
                  for location in self.multiworld.get_locations(self.player)}
        for name in data.PICKUP_NAMES:
            self.assertNotIn(name, placed, name)
        self.assertFalse(self.world.fill_slot_data()["enable_pickups"])


class TestPickupChecksComposeWithTheRandomizer(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_pickups": True, "randomize_pickups": True}

    def test_both_options_hold_at_once(self) -> None:
        # The two are separate questions: whether a slot is a check the first
        # time, and what it hands over afterwards. Neither overrides the other.
        self.assertIn(data.PICKUP_NAMES[0], LOCATION_NAME_TO_ID)
        slot_data = self.world.fill_slot_data()
        self.assertTrue(slot_data["enable_pickups"])
        self.assertTrue(slot_data["randomize_pickups"])
        # One row per ambient slot, then one per Phil's Place stand. The stands
        # are in the layout whatever the pickup options say, because the marker
        # on them belongs to the shop class.
        self.assertEqual(len(slot_data["pickup_layout"]),
                         len(data.PICKUP_SLOTS) + len(data.SHOP_STAND_SLOTS))
        # The shop class is off in this seed, so no stand row is a check, and
        # each keeps the model the game racks there.
        for row, stand in zip(slot_data["pickup_layout"][len(data.PICKUP_SLOTS):],
                              data.SHOP_STAND_SLOTS, strict=True):
            self.assertEqual(row[6], 0)
            self.assertEqual(row[4], stand[4])


class TestAbilityLocksAll(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"ability_locks": _ALL_ABILITY_LOCKS}

    def test_all_eight_items_enter_the_pool(self) -> None:
        pool_names = [item.name for item in self.multiworld.itempool
                      if item.player == self.player]
        for name in data.ABILITY_ITEMS:
            self.assertEqual(pool_names.count(name), 1, name)

    def test_classification_splits_crouch_from_the_rest(self) -> None:
        # Crouch gates nothing, so it is useful; every other ability item may
        # appear in a rule, Sprint included (termless today, progression so a
        # runthrough-found term needs no classification flip).
        for name in data.ABILITY_ITEMS:
            expected = (ItemClassification.useful if name == data.CROUCH_ITEM
                        else ItemClassification.progression)
            self.assertEqual(ITEM_CLASSIFICATIONS[name], expected, name)

    def test_sphere_zero_mission_stays_free(self) -> None:
        # The first Rosenberg mission carries no ability term, so a locked
        # seed always has a sphere 0.
        self.assertTrue(self.can_reach_location("An Old Friend"))

    def test_stunt_jump_needs_a_land_vehicle(self) -> None:
        self.collect_by_name(["Mainland Access"])
        self.assertFalse(self.can_reach_location(data.stunt_jump_name(1)))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location(data.stunt_jump_name(1)))

    def test_emergency_level_needs_a_land_vehicle(self) -> None:
        self.assertFalse(self.can_reach_location("Paramedic Level 01"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Paramedic Level 01"))

    def test_chopper_checkpoint_needs_an_air_vehicle_and_one_to_fly(self) -> None:
        # A start-island checkpoint: the helicopter is the requirement, not a land
        # vehicle, and the audit adds where the helicopter is. On the start island
        # that is the Sparrow passing Rub Out leaves in Vice Point, so the
        # checkpoint waits on that mission as well as on the ability.
        self.assertEqual(
            data.LOCATION_MISSION_REQUIREMENTS["Ocean Beach Chopper Checkpoint"],
            ["Rub Out"])
        self.collect_by_name([data.LAND_VEHICLES_ITEM, data.AIR_VEHICLES_ITEM])
        self.assertFalse(self.can_reach_location("Ocean Beach Chopper Checkpoint"))
        # Everything Rub Out takes, so its event can be swept.
        self.collect_by_name([*_MANSION_CHAIN, *_MANSION_CHAIN_COST,
                              "Starfish Island Access"])
        self.assertTrue(self.can_reach_location("Ocean Beach Chopper Checkpoint"))

    def test_every_stadium_event_needs_the_car(self) -> None:
        # All three stadium events are driven, so all three take the car. The
        # game would allow two of them without it, since Hotring and Bloodring
        # take the player on foot and warp them into the event car while
        # Dirtring sets them down beside a Sanchez to mount; the term is what the
        # event is, not what its launcher checks.
        self.collect_by_name(["Mainland Access"])
        for name in ("Hotring", "Bloodring", "Dirtring"):
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        for name in ("Hotring", "Bloodring", "Dirtring"):
            self.assertTrue(self.can_reach_location(name), name)

    def test_robbable_store_needs_weapon_equip(self) -> None:
        self.assertFalse(self.can_reach_location(data.robbable_store_name(1)))
        self.collect_by_name([data.WEAPON_EQUIP_ITEM])
        self.assertTrue(self.can_reach_location(data.robbable_store_name(1)))

    def test_rampages_split_weapon_from_vehicle(self) -> None:
        # A weapon rampage waits for Weapon Equip; the run-them-down rampage
        # (21, Ocean Beach, no handed weapon) takes a land vehicle instead.
        weapon_rampage = data.rampage_name(1)
        vehicle_rampage = data.rampage_name(21)
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertFalse(self.can_reach_location(weapon_rampage))
        self.assertTrue(self.can_reach_location(vehicle_rampage))
        self.collect_by_name([data.WEAPON_EQUIP_ITEM])
        self.assertTrue(self.can_reach_location(weapon_rampage))

    def test_sunshine_asset_keeps_its_driving_term(self) -> None:
        # The finale threshold is a solvability contract, and Sunshine Autos is
        # the one asset that completes partway along its strand: $1175 rises in
        # IMPORT1's recognition block, so the first import garage list finishes
        # the asset and the other three only raise its daily take. Its driving
        # requirement must survive that slice, through the asset's own entry and
        # through the sliced mission, or the threshold would count an asset the
        # player cannot actually finish.
        self.collect_by_name(_MANSION_CHAIN)
        self.assertEqual(data.FINALE_OPTIONAL_ASSETS["Sunshine Autos"], 1)
        self.assertIn(
            data.LAND_VEHICLES_ITEM,
            data.ASSET_ABILITY_REQUIREMENTS["Sunshine Autos"],
        )
        self.assertIn(
            data.LAND_VEHICLES_ITEM,
            data.MISSION_ABILITY_REQUIREMENTS["Sunshine Autos Import List 1"],
        )
        # And in the built group for the asset, which is the slice itself: the
        # asset's own term and the sliced mission's both have to survive the cut
        # at one progressive.
        active_items = frozenset(
            item for items in data.ABILITY_LOCK_ITEMS.values() for item in items)
        group = dict(rules._asset_completion_requirements(
            "Sunshine Autos", data.FINALE_OPTIONAL_ASSETS["Sunshine Autos"],
            active_items, data.CONTENT_SPLIT_OFF))
        self.assertIn(data.LAND_VEHICLES_ITEM, group)
        # And in the whole finale rule. This half no longer isolates Sunshine
        # Autos, since Kaufman Cabs and Cherry Popper need the car too, so the
        # threshold fails for their sake as well; the group above is what says
        # the slice kept the term.
        self.collect_by_name([
            "Progressive Vercetti Finale", "Progressive Vercetti Protection",
            "Mainland Access", "Starfish Island Access", data.WALLET_ITEM,
            data.SEA_VEHICLES_ITEM,
            "Printworks Ownership", "Progressive Printworks",
            "Kaufman Cabs Ownership", "Progressive Kaufman Cabs",
            "Cherry Popper Ownership", "Progressive Cherry Popper",
            "Pole Position Ownership",
            "Boatyard Ownership", "Progressive Boatyard",
            "Sunshine Autos Ownership", "Progressive Sunshine Autos",
            # Every asset behind a venue strand now needs a weapon somewhere in
            # it, so the weapon is not what the threshold turns on.
            data.WEAPON_EQUIP_ITEM,
        ])
        self.assertFalse(self.can_reach_location("Cap the Collector"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Cap the Collector"))

    def test_purchases_need_the_wallet(self) -> None:
        # A safehouse is for sale from a new game but locked money still blocks
        # paying; a business purchase carries the wallet through the sale
        # requirements.
        self.collect_by_name(_MANSION_CHAIN)
        self.assertFalse(self.can_reach_location("El Swanko Casa Purchase"))
        self.collect_by_name([
            "Progressive Vercetti Protection", "Starfish Island Access",
            # Shakedown puts the businesses up for sale and takes a weapon, so
            # the sale requirements carry it onto every business purchase.
            *_MANSION_CHAIN_COST,
        ])
        self.assertFalse(self.can_reach_location("Malibu Club Purchase"))
        self.collect_by_name([data.WALLET_ITEM])
        self.assertTrue(self.can_reach_location("El Swanko Casa Purchase"))
        self.assertTrue(self.can_reach_location("Malibu Club Purchase"))

    def test_a_mission_inherits_its_strand_predecessor_terms(self) -> None:
        # A strand runs in order: APMARK reveals only its first unpassed
        # mission, so Two Bit Hit cannot start until Demolition Man passes, and
        # Demolition Man carries the Land Vehicles term. Without the inherited
        # term the fill could put Land Vehicles at Two Bit Hit, which no player
        # could then reach.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name(["Progressive Avery", data.WEAPON_EQUIP_ITEM,
                              "Mainland Access"])
        self.assertFalse(self.can_reach_location("Demolition Man"))
        self.assertFalse(self.can_reach_location("Two Bit Hit"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Demolition Man"))
        self.assertTrue(self.can_reach_location("Two Bit Hit"))

    def test_a_first_mission_term_reaches_the_whole_strand(self) -> None:
        # Umberto's first mission is the one carrying the boat, so every later
        # mission of his strand inherits it: the boat is what opens the first and
        # is still required at the last, even though the last needs more besides.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name(["Progressive Umberto Robina", "Mainland Access",
                              # The Cubans wait on Auntie Poulet's last as well,
                              # which is a different strand and not the subject.
                              "Progressive Auntie Poulet"])
        self.assertFalse(self.can_reach_location("Stunt Boat Challenge"))
        self.assertFalse(self.can_reach_location("Trojan Voodoo"))
        self.collect_by_name([data.SEA_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Stunt Boat Challenge"))
        # Its own car and the weapon Cannon Fodder needs, both inherited down the
        # strand, are the rest of what the last mission takes.
        self.assertFalse(self.can_reach_location("Trojan Voodoo"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM, data.WEAPON_EQUIP_ITEM])
        self.assertTrue(self.can_reach_location("Trojan Voodoo"))

    def test_a_strand_first_mission_inherits_nothing(self) -> None:
        # Propagation runs forward only: Four Iron opens on its unlock and its
        # own weapon, without the car Demolition Man behind it carries.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name(["Progressive Avery", data.WEAPON_EQUIP_ITEM])
        self.assertTrue(self.can_reach_location("Four Iron"))
        self.assertNotIn(
            data.LAND_VEHICLES_ITEM,
            data.LOCATION_ABILITY_REQUIREMENTS.get("Four Iron", []))

    def test_a_cross_giver_edge_carries_what_it_implies(self) -> None:
        # An edge says "N progressives of that strand", which stands in for
        # having PASSED that strand's first N missions, so whatever passing them
        # takes belongs to the mission holding the edge. Otherwise the fill can
        # put an item behind the very mission that needs it: Rub Out opens on one
        # Progressive Death Row, and passing Death Row takes a weapon and the
        # mainland, so without this a seed could hide either behind Rub Out.
        active_items = frozenset(
            item for items in data.ABILITY_LOCK_ITEMS.values() for item in items)
        for mission, giver in MISSION_GIVER.items():
            edges = (list(data.MISSION_PREREQUISITES.get(mission, []))
                     + list(data.STRAND_PREREQUISITES.get(giver, [])))
            for target_strand, count in edges:
                for implied in STRAND_MISSIONS[target_strand][:count]:
                    with self.subTest(mission=mission, implied=implied):
                        self.assertIn(implied,
                                      rules._inherited_missions(mission, giver))
                        # The built requirement list, since that is what the fill
                        # reads. Reachability cannot show this: every mission
                        # holding an edge is unreachable in the empty state for
                        # its progressives alone, whatever else it carries.
                        requirements = dict(rules._mission_requirements(
                            mission, giver, active_items,
                            data.CONTENT_SPLIT_OFF, False))
                        for item in data.LOCATION_ABILITY_REQUIREMENTS.get(implied, []):
                            self.assertIn(item, requirements,
                                          f"{mission} misses {item} from {implied}")
                        # And the several-routes half, which propagates the same
                        # way and would be as easy to leave behind.
                        thresholds = rules._mission_thresholds(
                            mission, giver, active_items, False)
                        for route in data.LOCATION_ABILITY_ALTERNATIVES.get(implied, []):
                            group = [(item, 1) for item in route]
                            self.assertTrue(
                                any(group in alternatives
                                    for alternatives, _needed in thresholds),
                                f"{mission} misses the {route} route "
                                f"from {implied}")
                        inherited_regions = rules._inherited_regions(mission, giver)
                        for region in data.MISSION_REGION_REQUIREMENTS.get(implied, []):
                            self.assertIn(region, inherited_regions,
                                          f"{mission} misses {region} from {implied}")

    def test_vigilante_needs_a_weapon_and_the_other_levels_do_not(self) -> None:
        # Shooting the criminal is the whole of Vigilante, so its levels take a
        # weapon on top of the car every emergency level takes. The other four
        # activities are driving or carrying, so the car is all they take.
        self.collect_by_name([data.LAND_VEHICLES_ITEM, "Mainland Access"])
        self.assertFalse(self.can_reach_location("Vigilante Level 01"))
        for activity in data.EMERGENCY_LEVELS:
            if activity != "Vigilante":
                name = data.emergency_name(activity, 1)
                self.assertTrue(self.can_reach_location(name), name)
        self.collect_by_name([data.WEAPON_EQUIP_ITEM])
        self.assertTrue(self.can_reach_location("Vigilante Level 01"))

    def test_leaf_links_has_five_ways_in_and_eight_checks_behind_them(self) -> None:
        # The golf course is walled, so the audit gives it five ways in and every
        # check inside carries all five: drive, fly, sail, jump the fence, or walk
        # through the gate Four Iron opens. One table, so the eight cannot drift
        # apart, and each of the five is a route on its own rather than a term.
        self.assertEqual(len(data.LEAF_LINKS_ROUTES), 5)
        for route in data.LEAF_LINKS_ROUTES:
            self.assertEqual(len(route), 1)
        inside = ([data.hidden_package_name(index) for index in (46, 47, 48, 49, 50)]
                  + [data.pickup_name(index) for index in (33, 59, 85)])
        for name in inside:
            with self.subTest(location=name):
                self.assertEqual(data.LOCATION_ABILITY_ALTERNATIVES[name],
                                 data.LEAF_LINKS_ROUTES)
        # Reaching them is asserted on the five packages, the checks this seed
        # has; TestPickupReach walks the same five ways in for the three pickups.
        packages = inside[:5]
        for name in packages:
            self.assertFalse(self.can_reach_location(name), name)
        # Any one of the five opens all of them, and the jump is the cheapest.
        self.collect_by_name([data.JUMP_ITEM])
        for name in packages:
            self.assertTrue(self.can_reach_location(name), name)

    def test_a_helicopter_route_says_where_the_helicopter_is(self) -> None:
        # Two start-island packages read "a helicopter" in the audit and then say
        # where one is, which is the whole point: holding Air Vehicles is being
        # ALLOWED to fly, not having something to fly. Left as a bare term they
        # would be free the moment the vehicles key handed the item over, with no
        # aircraft within reach.
        rooftops = [data.hidden_package_name(index) for index in (21, 40)]
        for name in rooftops:
            self.assertNotIn(name, data.LOCATION_ABILITY_REQUIREMENTS)
            self.assertEqual(data.LOCATION_ABILITY_ALTERNATIVES[name],
                             [[data.AIR_VEHICLES_ITEM]])
            self.assertIn(name, data.SOURCED_ROUTE_LOCATIONS)
        self.collect_by_name([data.AIR_VEHICLES_ITEM])
        for name in rooftops:
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name(["Mainland Access"])
        for name in rooftops:
            self.assertTrue(self.can_reach_location(name), name)

    def test_the_starfish_pool_wall_can_be_flown_as_well_as_jumped(self) -> None:
        # Package 54 is the ONE rule this audit pass made looser rather than
        # stricter: it was a flat Jump and the sheet gives a helicopter beside
        # it. Written out because a loosening is the direction that strands
        # items, so if the audit row is wrong this is the test that has to
        # change with it. Reaching Starfish by air already costs a helicopter
        # and a way to the mainland, so the air route cannot open the island for
        # itself and there is no cycle.
        pool = data.hidden_package_name(54)
        self.assertEqual(pool,
                         "Hidden Package - Starfish Island - Northeast pool")
        self.assertNotIn(pool, data.LOCATION_ABILITY_REQUIREMENTS)
        self.assertEqual(data.LOCATION_ABILITY_ALTERNATIVES[pool],
                         [[data.AIR_VEHICLES_ITEM], [data.JUMP_ITEM]])
        self.collect_by_name(["Starfish Island Access"])
        self.assertFalse(self.can_reach_location(pool))
        # Both halves are walked, and the air one is put back afterwards rather
        # than left standing, since it is the loosening and a test that opened
        # the pool by jumping would say nothing about it.
        jump = self.collect_by_name([data.JUMP_ITEM])
        self.assertTrue(self.can_reach_location(pool))
        self.remove(jump)
        self.assertFalse(self.can_reach_location(pool))
        # A helicopter with nowhere to have come from does not open it: the route
        # is sourced, so it only pays once the mainland is reachable.
        self.collect_by_name([data.AIR_VEHICLES_ITEM])
        self.assertFalse(self.can_reach_location(pool))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location(pool))

    def test_the_unwalkable_packages_need_their_ability(self) -> None:
        # Five packages cannot be walked to at all: four want a jump and one is
        # reachable only from the air. Twenty-one more have several ways in, the
        # five inside Leaf Links among them. The remaining seventy-five need
        # nothing, which is what keeps an ability-locked seed wide, so the counts
        # are pinned here as well as the terms.
        self.assertEqual(len(data.PACKAGE_ABILITY_REQUIREMENTS), 5)
        self.assertEqual(len(data.PACKAGE_ABILITY_ALTERNATIVES), 21)
        awkward = (set(data.PACKAGE_ABILITY_REQUIREMENTS)
                   | set(data.PACKAGE_ABILITY_ALTERNATIVES))
        # Package 92 is in both tables, needing a jump and then either a car or a
        # helicopter, so twenty-five packages are awkward and not twenty-six.
        self.assertEqual(len(awkward), 25)
        self.assertEqual(data.HIDDEN_PACKAGE_COUNT - len(awkward), 75)
        self.collect_by_name(["Mainland Access", "Starfish Island Access"])
        for index, items in data.PACKAGE_ABILITY_REQUIREMENTS.items():
            name = data.hidden_package_name(index)
            with self.subTest(package=name):
                self.assertEqual(data.LOCATION_ABILITY_REQUIREMENTS[name], items)
                self.assertFalse(self.can_reach_location(name))
        for index in range(1, data.HIDDEN_PACKAGE_COUNT + 1):
            if index not in awkward:
                name = data.hidden_package_name(index)
                self.assertTrue(self.can_reach_location(name), name)
        self.collect_by_name([data.JUMP_ITEM, data.AIR_VEHICLES_ITEM])
        for index in data.PACKAGE_ABILITY_REQUIREMENTS:
            name = data.hidden_package_name(index)
            self.assertTrue(self.can_reach_location(name), name)

    def test_a_rampage_out_of_reach_takes_a_vehicle_and_its_weapon(self) -> None:
        # Two rampage icons cannot be walked to: 2 is reached by air or by road
        # and 25, out in the water, by air or by boat. Both keep the weapon their
        # class rule gives them, which the audit names for 25 and not for 2.
        self.collect_by_name(["Mainland Access"])
        for index, other in ((2, data.LAND_VEHICLES_ITEM),
                             (25, data.SEA_VEHICLES_ITEM)):
            name = data.rampage_name(index)
            with self.subTest(rampage=name):
                self.assertEqual(
                    data.RAMPAGE_ABILITY_ALTERNATIVES[index],
                    [[data.AIR_VEHICLES_ITEM], [other]])
                self.assertIn(data.WEAPON_EQUIP_ITEM,
                              data.LOCATION_ABILITY_REQUIREMENTS[name])
                self.assertFalse(self.can_reach_location(name))
        self.collect_by_name([data.WEAPON_EQUIP_ITEM])
        for index in data.RAMPAGE_ABILITY_ALTERNATIVES:
            # The weapon alone is not enough, since the icon is still out of
            # reach.
            self.assertFalse(self.can_reach_location(data.rampage_name(index)))
        self.collect_by_name([data.AIR_VEHICLES_ITEM])
        for index in data.RAMPAGE_ABILITY_ALTERNATIVES:
            name = data.rampage_name(index)
            self.assertTrue(self.can_reach_location(name), name)

    def test_a_package_with_two_ways_in_takes_either(self) -> None:
        # Package 7 sits on a roof, which the audit reaches by jumping a car up
        # or by landing a helicopter. Either is enough on its own, and neither is
        # required, so the fill may place one of them behind the other.
        self.assertEqual(data.PACKAGE_ABILITY_ALTERNATIVES[7],
                         [[data.AIR_VEHICLES_ITEM], [data.LAND_VEHICLES_ITEM]])
        name = data.hidden_package_name(7)
        self.assertFalse(self.can_reach_location(name))
        # The helicopter route carries where the helicopter is, so the air item
        # alone is not the route; the mainland comes with it.
        self.collect_by_name([data.AIR_VEHICLES_ITEM])
        self.assertFalse(self.can_reach_location(name))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location(name))
        self.remove_by_name([data.AIR_VEHICLES_ITEM])
        self.assertFalse(self.can_reach_location(name))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location(name))

    def test_a_route_of_two_abilities_takes_both(self) -> None:
        # One of package 86's three ways in is a running jump, which takes the
        # sprint and the jump together, so neither alone opens it while the other
        # two routes are shut.
        self.assertIn([data.SPRINT_ITEM, data.JUMP_ITEM],
                      data.PACKAGE_ABILITY_ALTERNATIVES[86])
        name = data.hidden_package_name(86)
        self.collect_by_name(["Mainland Access", data.SPRINT_ITEM])
        self.assertFalse(self.can_reach_location(name))
        self.collect_by_name([data.JUMP_ITEM])
        self.assertTrue(self.can_reach_location(name))

    def test_a_mission_route_propagates_down_its_strand(self) -> None:
        # Gun Runner opens with a weapon or a car, and Boomshine Saigon follows
        # it in Phil Cassidy's strand, so Boomshine Saigon carries that route
        # too. Read off the built thresholds, since Boomshine Saigon also needs a
        # weapon outright and reachability cannot separate the two.
        active_items = frozenset(
            item for items in data.ABILITY_LOCK_ITEMS.values() for item in items)
        route = [[(data.WEAPON_EQUIP_ITEM, 1)], [(data.LAND_VEHICLES_ITEM, 1)]]
        self.assertEqual(data.MISSION_ABILITY_ALTERNATIVES["Gun Runner"],
                         [[data.WEAPON_EQUIP_ITEM], [data.LAND_VEHICLES_ITEM]])
        for mission, giver in (("Gun Runner", "Phil Cassidy"),
                               ("Boomshine Saigon", "Phil Cassidy")):
            with self.subTest(mission=mission):
                self.assertIn((route, 1), rules._mission_thresholds(
                    mission, giver, active_items, False))
        # And Gun Runner itself, where the route is the whole requirement, so
        # either item opens it and neither is needed.
        self.collect_by_name(["Mainland Access", "Progressive Phil Cassidy"])
        self.assertFalse(self.can_reach_location("Gun Runner"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Gun Runner"))
        self.remove_by_name([data.LAND_VEHICLES_ITEM])
        self.assertFalse(self.can_reach_location("Gun Runner"))
        self.collect_by_name([data.WEAPON_EQUIP_ITEM])
        self.assertTrue(self.can_reach_location("Gun Runner"))

    def test_a_route_an_earlier_term_covers_gates_nothing(self) -> None:
        # A route is only as useful as the terms around it. Death Row opens with
        # a car or a helicopter, but it also inherits Mall Shootout, which needs
        # the car outright, so the car is required either way and the route
        # decides nothing. Measured rather than assumed, because a route that
        # cannot fail is worth knowing about: fifteen mission locations carry a
        # route, own or inherited, and three of them are live.
        active_items = frozenset(
            item for items in data.ABILITY_LOCK_ITEMS.values() for item in items)
        flat = {item for item, _count in rules._mission_requirements(
            "Death Row", "Death Row", active_items, data.CONTENT_SPLIT_OFF, False)}
        thresholds = rules._mission_thresholds("Death Row", "Death Row",
                                               active_items, False)
        self.assertIn(([[(data.LAND_VEHICLES_ITEM, 1)],
                        [(data.AIR_VEHICLES_ITEM, 1)]], 1), thresholds)
        # The car is a flat term besides, inherited from Mall Shootout, so one
        # side of the route is required whatever the other says.
        self.assertIn(data.LAND_VEHICLES_ITEM, flat)
        # Counted through the built thresholds rather than off the table, so a
        # route lost between the two fails here.
        carriers = [
            mission for mission, giver in MISSION_GIVER.items()
            if any(group in alternatives
                   for alternatives, _needed in rules._mission_thresholds(
                       mission, giver, active_items, False)
                   for group in [[(item, 1) for item in route]
                                 for routes in [
                                     data.LOCATION_ABILITY_ALTERNATIVES.get(name, [])
                                     for name in [mission, *rules._inherited_missions(
                                         mission, giver)]]
                                 for route in routes])
        ]
        self.assertEqual(len(carriers), 15)

    def test_a_predecessor_island_is_inherited(self) -> None:
        # Cap the Collector is played on the mainland and opens on three
        # Progressive Vercetti Protection, and those three missions are played
        # from the mansion, so it needs Starfish Island Access as well even
        # though its own location is not on the island. Without this the fill
        # could put that item behind it: the progressives can sit anywhere, so a
        # sweep could hold all three while the mansion is still shut, and the
        # strand could never be passed.
        self.collect_by_name(_MANSION_CHAIN)
        for predecessor in ("Shakedown", "Bar Brawl", "Cop Land"):
            self.assertEqual(LOCATION_REGIONS[predecessor], data.REGION_STARFISH)
        active_items = frozenset(
            item for items in data.ABILITY_LOCK_ITEMS.values() for item in items)
        # The island has a barrier and an audited route, so its requirement is a
        # one-of and not a flat term; either half of the rule may hold it.
        named = {item for item, _count in rules._mission_requirements(
            "Cap the Collector", "Vercetti Finale", active_items,
            data.CONTENT_SPLIT_OFF, False)}
        for groups, _needed in rules._mission_thresholds(
                "Cap the Collector", "Vercetti Finale", active_items, False):
            named.update(item for group in groups for item, _count in group)
        self.assertIn("Starfish Island Access", named)
        # Many missions inherit a predecessor from another island, and for most
        # of them that island is the start island, which costs nothing. Three are
        # left, and the finale names the mainland in its own right, so Death Row
        # and Cap the Collector are where inheritance is the only source of an
        # area item. This is the whole list rather than a spot check.
        elsewhere = {
            name: sorted({LOCATION_REGIONS[predecessor] for predecessor
                          in rules._inherited_missions(name, strand)
                          if LOCATION_REGIONS[predecessor] != LOCATION_REGIONS[name]
                          and data.region_access_groups(
                              LOCATION_REGIONS[predecessor], False,
                              routes_allowed=False)})
            for name, strand in MISSION_GIVER.items()}
        self.assertEqual({name: regions for name, regions in elsewhere.items()
                          if regions},
                         {"Death Row": [data.REGION_STARFISH],
                          "Cap the Collector": [data.REGION_STARFISH],
                          "Keep Your Friends Close...": [data.REGION_MAINLAND]})
        self.assertIn(data.REGION_MAINLAND,
                      data.MISSION_REGION_REQUIREMENTS["Keep Your Friends Close..."])

    def test_a_mission_requires_every_inherited_island(self) -> None:
        # The invariant behind those, over every mission and through the
        # built rule rather than through the gatherer: a mission cannot be
        # reachable while an island one of its predecessors is played on is still
        # shut, whichever direction the strands run. Read off the requirement
        # list and the thresholds together, so a term dropped anywhere between
        # the gatherer and the rule fails this too.
        active_items = frozenset(
            item for items in data.ABILITY_LOCK_ITEMS.values() for item in items)
        for split in (False, True):
            for mission, giver in MISSION_GIVER.items():
                flat = {item for item, _count in rules._mission_requirements(
                    mission, giver, active_items, data.CONTENT_SPLIT_OFF, split)}
                for groups, _needed in rules._mission_thresholds(
                        mission, giver, active_items, split):
                    flat.update(item for group in groups for item, _count in group)
                for predecessor in rules._inherited_missions(mission, giver):
                    region = LOCATION_REGIONS[predecessor]
                    if region == LOCATION_REGIONS[mission]:
                        # The region graph puts this location there already.
                        continue
                    for group in data.region_access_groups(region, split):
                        with self.subTest(mission=mission, predecessor=predecessor,
                                          split=split):
                            self.assertTrue(set(group) & flat, group)

    def test_the_printworks_edge_comes_and_goes_with_its_class(self) -> None:
        # Cap the Collector waits on Hit the Courier, which is a Printworks
        # mission, so the edge names a progressive that leaves the pool when the
        # properties class is off. It is carried only while the class is on,
        # since no rule may name an item that is not in the pool.
        self.assertEqual(data.PROPERTY_MISSION_PREREQUISITES,
                         {"Cap the Collector": [("Printworks", 2)]})
        for mission, edges in data.MISSION_PREREQUISITES.items():
            for strand, _count in edges:
                self.assertNotIn(strand, data.VENUE_STRANDS,
                                 f"{mission} names a venue strand unguarded")
        with_class = dict(rules._mission_requirements(
            "Cap the Collector", "Vercetti Finale", frozenset(),
            data.CONTENT_SPLIT_OFF, False, properties_enabled=True))
        without = dict(rules._mission_requirements(
            "Cap the Collector", "Vercetti Finale", frozenset(),
            data.CONTENT_SPLIT_OFF, False, properties_enabled=False))
        self.assertEqual(with_class["Progressive Printworks"], 2)
        self.assertNotIn("Progressive Printworks", without)

    def test_a_region_route_can_actually_open_that_region(self) -> None:
        # A route is worth nothing if reaching the mission it names already needs
        # the region the route opens. That is the mistake this whole stage nearly
        # shipped: All Hands On Deck! is played on the start island and still
        # needs the mainland, since Sir, Yes Sir! before it does, so a mainland
        # route out of it would have been satisfiable only by a player already
        # there. Asserted over every route rather than recorded per mission,
        # because a record of a belief is not a guard on it.
        for region in (data.REGION_VICE_CITY, data.REGION_MAINLAND,
                       data.REGION_STARFISH):
            for split in (False, True):
                for group in data.region_route_groups(region, split):
                    for item in group:
                        if not item.endswith(" Passed"):
                            continue
                        mission = item[:-len(" Passed")]
                        with self.subTest(region=region, mission=mission):
                            needed = set(rules._inherited_regions(
                                mission, MISSION_GIVER[mission]))
                            needed.add(LOCATION_REGIONS[mission])
                            self.assertNotIn(region, needed)

    def test_a_venue_event_still_pays_for_its_property(self) -> None:
        # G-spotlight is a Film Studio mission, so with the properties class off
        # its progressives and its ownership item are not in the pool and its
        # event cannot name them. What it must still name is the property-sale
        # requirements: the studio has to be bought in game, and the businesses go
        # on sale only when Shakedown passes, so without them the fill could put
        # Starfish Island Access or the wallet behind the very stunt jumps that
        # mission builds.
        active_items = frozenset(
            item for items in data.ABILITY_LOCK_ITEMS.values() for item in items)
        for properties_enabled in (True, False):
            requirements, thresholds = rules._event_terms(
                "G-spotlight", active_items, data.CONTENT_SPLIT_OFF, False,
                properties_enabled,
                *rules._property_sale_requirements(
                    active_items, data.CONTENT_SPLIT_OFF, False, properties_enabled),
            )
            # Both halves: the island has routes now, so its barrier is named in
            # a one-of rather than flat.
            named = {item for item, _count in requirements}
            named.update(item for groups, _needed in thresholds
                         for group in groups for item, _count in group)
            with self.subTest(properties_enabled=properties_enabled):
                # The sale requirements, whichever way the class is set.
                self.assertIn("Starfish Island Access", named)
                self.assertIn(data.WALLET_ITEM, named)
                self.assertIn("Progressive Vercetti Protection", named)
                # And the venue's own items only while the class puts them in the
                # pool.
                for item in ("Progressive Film Studio", "Film Studio Ownership"):
                    if properties_enabled:
                        self.assertIn(item, named)
                    else:
                        self.assertNotIn(item, named)

    def test_the_route_events_are_events_and_nothing_else(self) -> None:
        # Each route mission gets one event location: no address, so it is not a
        # check and no id table, reward mirror or filler count sees it, holding a
        # locked progression item nothing else can place.
        events = [location for location in self.multiworld.get_locations(self.player)
                  if location.address is None]
        self.assertEqual(len(events), len(data.ROUTE_MISSIONS))
        for location in events:
            with self.subTest(event=location.name):
                mission = location.name.removesuffix(" (event)")
                self.assertIn(mission, data.ROUTE_MISSIONS)
                self.assertEqual(location.parent_region.name,
                                 LOCATION_REGIONS[mission])
                self.assertNotIn(location.name, LOCATION_NAME_TO_ID)
                self.assertNotIn(location.name, self.world._reward_mirror())
                item = location.item
                self.assertEqual(item.name, data.mission_passed_item_name(mission))
                self.assertTrue(item.advancement)
                self.assertIsNone(item.code)
                self.assertNotIn(item.name, ITEM_NAME_TO_ID)
                self.assertNotIn(item.name, [pool.name for pool
                                             in self.multiworld.itempool])
        # And the event is only reachable where its mission is.
        self.assertFalse(self.multiworld.state.has(
            data.mission_passed_item_name(data.ROUTE_MISSIONS[0]), self.player))

    def test_a_route_mission_costs_what_reaching_it_costs(self) -> None:
        # A route names a mission, and what that route is worth is everything
        # reaching the mission takes, not the island it happens to sit on. This
        # is recorded per route mission because reading the island alone is the
        # easy mistake: All Hands On Deck! is played on the start island and
        # still needs the mainland, since Sir, Yes Sir! before it in Cortez's
        # strand does. So its boat reaches Starfish Island for a player who has
        # crossed to the mainland, the same much the helicopter route asks for,
        # and the invariant above is what keeps a route from claiming more.
        expected = {
            "All Hands On Deck!": {data.REGION_MAINLAND},
            "Phnom Penh '86": {data.REGION_STARFISH},
            "Rub Out": {data.REGION_STARFISH, data.REGION_MAINLAND},
            "G-spotlight": {data.REGION_VICE_CITY, data.REGION_MAINLAND},
            # The shop stock gates. The four Rosenberg and Cortez ones are on the
            # start island and cost no area item at all, which is what lets a
            # shop item behind one still open early.
            "Jury Fury": set(),
            "Riot": set(),
            "Treacherous Swine": set(),
            "Mall Shootout": set(),
            "Guardian Angels": set(),
            "The Chase": {data.REGION_STARFISH},
            "Bar Brawl": {data.REGION_STARFISH, data.REGION_MAINLAND},
            "Shakedown": {data.REGION_STARFISH, data.REGION_MAINLAND},
            # Phil's four stands, which Boomshine Saigon creates rather than
            # racks. Phil's Place is on the mainland and so is Gun Runner before
            # it, so the mainland is the whole of it.
            "Boomshine Saigon": {data.REGION_MAINLAND},
            # The three a collectible waits on rather than a shop.
            "Four Iron": set(),
            "Trojan Voodoo": {data.REGION_MAINLAND},
            "Loose Ends": {data.REGION_MAINLAND},
            # The knife outside the Malibu Club. The club is on the start island
            # and the strand's own missions before it are not, which is the same
            # shape as All Hands On Deck! above: the pickup sits where a player
            # who has never crossed can stand, and it takes the mainland anyway.
            "The Job": {data.REGION_VICE_CITY, data.REGION_MAINLAND},
        }
        for mission in data.ROUTE_MISSIONS:
            giver = MISSION_GIVER[mission]
            with self.subTest(mission=mission):
                needed = set(rules._inherited_regions(mission, giver))
                needed.add(LOCATION_REGIONS[mission])
                self.assertEqual(needed - {data.REGION_VICE_CITY},
                                 expected[mission] - {data.REGION_VICE_CITY})

    def test_neither_island_opens_without_an_area_item(self) -> None:
        # The routes reach Starfish Island from the mainland, never the mainland
        # from anywhere, so holding every progressive and no area item reaches
        # neither island.
        pool = {item.name for item in self.multiworld.itempool
                if item.player == self.player and item.name not in data.AREA_ITEMS}
        self.collect_by_name(sorted(pool))
        for name in ("Rub Out", "Shakedown", "Cap the Collector",
                     data.FINAL_MISSION, data.hidden_package_name(51)):
            self.assertFalse(self.can_reach_location(name), name)
        # Starfish Island Access opens its own island and stops there: the
        # mainland has a barrier and no route, so anything wanting the mainland
        # still waits. A package on the island is the check that does not, since
        # the missions there inherit the mainland through Death Row.
        self.collect_by_name(["Starfish Island Access"])
        self.assertTrue(self.can_reach_location(data.hidden_package_name(51)))
        for name in ("Rub Out", "Cap the Collector", data.FINAL_MISSION):
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name(["Mainland Access"])
        for name in ("Rub Out", "Cap the Collector", data.FINAL_MISSION):
            self.assertTrue(self.can_reach_location(name), name)
        # And the mainland reaches Starfish the other way, by helicopter, which
        # is the one route there is.
        self.assertEqual(
            data.region_route_groups(data.REGION_MAINLAND, False), [])
        self.assertIn([data.AIR_VEHICLES_ITEM, "Mainland Access"],
                      data.region_route_groups(data.REGION_STARFISH, False))

    def test_an_asset_slice_carries_nothing_a_threshold_cannot_hold(self) -> None:
        # The finale's asset groups carry lock terms and nothing else, because
        # they sit inside the finale's own threshold over groups, where a nested
        # threshold has no shape. So neither a region nor a several-routes
        # requirement can ride in a group, and neither has to: every region a
        # sliced mission needs is one the finale's own rule already requires, and
        # no optional asset's slice carries a route. The audit came close to
        # breaking the first half, since The Shootist, The Job, Recruitment Drive
        # and G-spotlight all gained the mainland and all sit in a slice.
        finale = data.STORY_GIVERS["Vercetti Finale"][-1]
        covered = set(rules._inherited_regions(finale, "Vercetti Finale"))
        covered.add(LOCATION_REGIONS[finale])
        for asset, progressive_count in data.FINALE_OPTIONAL_ASSETS.items():
            for mission in data.VENUE_STRANDS.get(asset, [])[:progressive_count]:
                with self.subTest(asset=asset, mission=mission):
                    for region in data.MISSION_REGION_REQUIREMENTS.get(mission, []):
                        self.assertIn(region, covered)
                    self.assertNotIn(mission, data.LOCATION_ABILITY_ALTERNATIVES)

    def test_the_fastest_boat_is_played_on_the_mainland(self) -> None:
        # Diaz's third, so its own region is the mansion's island, but the boat
        # it steals is in the Viceport boatyard and the audit says so. Nothing
        # else in Diaz's strand names the mainland, so without this entry the
        # fill could put Mainland Access itself behind the mission, and the two
        # missions after it inherit the same hole.
        self.assertIn(data.REGION_MAINLAND,
                      data.MISSION_REGION_REQUIREMENTS["The Fastest Boat"])
        self.assertEqual(LOCATION_REGIONS["The Fastest Boat"],
                         data.REGION_STARFISH)
        for mission in ("The Fastest Boat", "Supply & Demand", "Rub Out"):
            with self.subTest(mission=mission):
                self.assertIn(
                    data.REGION_MAINLAND,
                    rules._inherited_regions(mission, "Diaz"))

    def test_venue_race_mission_needs_its_vehicle(self) -> None:
        # The Driver is a forced car race, so its own rule names the car. No
        # Escape? opens the strand and needs one too, so reachability cannot tell
        # the two apart and the table entry is what pins the race itself.
        self.collect_by_name(_MANSION_CHAIN)
        self.assertIn(data.LAND_VEHICLES_ITEM,
                      data.MISSION_ABILITY_REQUIREMENTS["The Driver"])
        self.collect_by_name([
            "Progressive Malibu Club", "Malibu Club Ownership",
            "Progressive Vercetti Protection", "Starfish Island Access",
            data.WALLET_ITEM, data.WEAPON_EQUIP_ITEM, "Mainland Access",
            # The chain to the mansion wants the Cubans' boat as well.
            data.SEA_VEHICLES_ITEM,
        ])
        self.assertFalse(self.can_reach_location("No Escape?"))
        self.assertFalse(self.can_reach_location("The Driver"))
        # The Job follows The Driver in the strand, so it inherits the term.
        self.assertFalse(self.can_reach_location("The Job"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("No Escape?"))
        self.assertTrue(self.can_reach_location("The Driver"))
        self.assertTrue(self.can_reach_location("The Job"))

    def test_venue_activity_needs_its_vehicle(self) -> None:
        # A Sunshine Autos race is driven in the player's own car, and a venue
        # activity's rule is the only thing carrying that term (the races are
        # ruled by venue, not by the lock-term fallback), so it is pinned
        # through the rule rather than through the table alone. Without it the
        # fill could put Land Vehicles behind a race that needs it.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name([
            "Sunshine Autos Ownership", "Progressive Vercetti Protection",
            "Starfish Island Access", "Mainland Access", data.WALLET_ITEM,
            data.WEAPON_EQUIP_ITEM,
            # The chain wants the Cubans' boat, and the car is the subject, so
            # only the boat comes from the chain's cost here.
            data.SEA_VEHICLES_ITEM,
        ])
        for race in data.SUNSHINE_RACES:
            self.assertFalse(self.can_reach_location(race), race)
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        for race in data.SUNSHINE_RACES:
            self.assertTrue(self.can_reach_location(race), race)

    def test_slot_data_carries_the_ability_contract(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["ability_locks"], sorted(_ALL_ABILITY_LOCKS))
        config = slot_data["config_globals"]
        item_globals = slot_data["item_globals"]
        for name in data.ABILITY_ITEMS:
            self.assertEqual(config[str(scm.ability_lock_flag_global(name))], 1, name)
            self.assertEqual(
                item_globals[str(ITEM_NAME_TO_ID[name])],
                scm.ability_unlock_global(name), name,
            )


class TestAbilityLocksOff(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: ability_locks is empty.

    def test_no_ability_items_and_vanilla_flags(self) -> None:
        pool_names = {item.name for item in self.multiworld.itempool}
        precollected = {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        for name in data.ABILITY_ITEMS:
            self.assertNotIn(name, pool_names, name)
            self.assertNotIn(name, precollected, name)
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["ability_locks"], [])
        config = slot_data["config_globals"]
        for name in data.ABILITY_ITEMS:
            self.assertEqual(config[str(scm.ability_lock_flag_global(name))], 0, name)

    def test_a_route_nothing_locks_is_no_requirement(self) -> None:
        # A route whose items are none of them locked is always open, so the
        # whole several-routes requirement is free and no rule mentions it. Read
        # off the emitter with one key selected at a time, since a seed's options
        # cannot show both answers at once.
        vehicles = frozenset(data.ABILITY_LOCK_ITEMS["vehicles"])
        # Package 86's running jump route needs the sprint and the jump, neither
        # of which the vehicles key locks, so that route is free and the other
        # two stop mattering.
        self.assertEqual(rules._ability_alternative_thresholds(
            data.hidden_package_name(86), vehicles, False), [])
        # Package 7's routes are all vehicles, so it keeps its one-of, and each
        # air route keeps the source it names, which no key locks.
        self.assertEqual(
            rules._ability_alternative_thresholds(data.hidden_package_name(7),
                                                  vehicles, False),
            [([[(data.AIR_VEHICLES_ITEM, 1), ("Mainland Access", 1)],
               [(data.AIR_VEHICLES_ITEM, 1), ("Rub Out Passed", 1)],
               [(data.LAND_VEHICLES_ITEM, 1)]], 1)])
        # And with the crossings split, the mainland is named by each crossing
        # rather than by an item the seed does not have.
        split = rules._ability_alternative_thresholds(
            data.hidden_package_name(7), vehicles, True)
        named = {item for groups, _needed in split
                 for group in groups for item, _count in group}
        self.assertNotIn("Mainland Access", named)
        for crossing in data.MAINLAND_CROSSING_ITEMS:
            self.assertIn(crossing, named)
        # With every key selected, package 86 keeps all four routes: two ways to
        # a helicopter, the car, and the running jump.
        every_item = frozenset(item for items in data.ABILITY_LOCK_ITEMS.values()
                               for item in items)
        groups, needed = rules._ability_alternative_thresholds(
            data.hidden_package_name(86), every_item, False)[0]
        self.assertEqual(needed, 1)
        self.assertEqual(len(groups), 4)

    def test_no_ability_terms_without_the_locks(self) -> None:
        # With every key off a stunt jump needs only its region and a store
        # nothing at all: no rule may name an item that is not in the pool.
        self.collect_by_name(_MANSION_CHAIN)
        self.assertTrue(self.can_reach_location(data.robbable_store_name(1)))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location(data.stunt_jump_name(1)))
        # Nothing propagates through a strand either, for the same reason: the
        # predecessor's term is filtered out with its key.
        self.collect_by_name(["Progressive Avery"])
        self.assertTrue(self.can_reach_location("Two Bit Hit"))


class TestAbilityLocksWalletOnly(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"ability_locks": ["wallet"]}

    def test_only_the_wallet_locks(self) -> None:
        # The wallet term binds, and no vehicle term exists because the
        # vehicles key is off (its items are not in the pool).
        pool_names = {item.name for item in self.multiworld.itempool}
        self.assertIn(data.WALLET_ITEM, pool_names)
        self.assertNotIn(data.LAND_VEHICLES_ITEM, pool_names)
        self.assertFalse(self.can_reach_location("El Swanko Casa Purchase"))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location(data.stunt_jump_name(1)))
        self.collect_by_name([data.WALLET_ITEM])
        self.assertTrue(self.can_reach_location("El Swanko Casa Purchase"))

    def test_finale_carries_the_wallet_through_the_sale_requirements(self) -> None:
        # Vanilla asset completion spends money, so the finale must hold the
        # wallet term or the fill could strand Wallet behind Cap the Collector.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name([
            "Progressive Vercetti Finale", "Progressive Vercetti Protection",
            "Mainland Access", "Starfish Island Access",
        ])
        self.collect_by_name(_FINALE_ASSET_ITEMS)
        self.assertFalse(self.can_reach_location("Cap the Collector"))
        self.collect_by_name([data.WALLET_ITEM])
        self.assertTrue(self.can_reach_location("Cap the Collector"))


class TestAbilityLocksHundredPercent(WorldTestBase):
    # Every check class plus every lock: the widest rule surface. The
    # inherited default tests prove the 100 percent completion stays
    # satisfiable with every ability term active.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "goal": "hundred_percent",
        "ability_locks": _ALL_ABILITY_LOCKS,
    }


class TestContentLocksAllKeys(WorldTestBase):
    # Every class held. The inherited default tests prove the seed fills and
    # stays reachable with a term on every collectible and activity check.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"content_locks": _ALL_CONTENT_LOCKS}

    def test_every_key_puts_its_item_in_the_pool_as_progression(self) -> None:
        pool_names = {item.name for item in self.multiworld.itempool}
        for name in data.CONTENT_ITEMS:
            self.assertIn(name, pool_names, name)
            self.assertEqual(
                ITEM_CLASSIFICATIONS[name], ItemClassification.progression, name,
            )

    def test_each_class_waits_for_its_own_item(self) -> None:
        # A key holds its whole class and nothing else, so each item releases
        # exactly its own class. The safehouse purchase carries its term
        # directly, where a business purchase rides the sale requirements.
        pairs = [
            (data.hidden_package_name(1), data.HIDDEN_PACKAGES_ITEM),
            (data.rampage_name(1), data.RAMPAGES_ITEM),
            (data.robbable_store_name(1), data.ROBBABLE_STORES_ITEM),
            ("El Swanko Casa Purchase", data.PROPERTY_PURCHASES_ITEM),
        ]
        for location, _ in pairs:
            self.assertFalse(self.can_reach_location(location), location)
        for index, (location, item) in enumerate(pairs):
            with self.subTest(location=location):
                self.collect_by_name([item])
                self.assertTrue(self.can_reach_location(location), location)
                # The classes still held stay held.
                for later_location, _ in pairs[index + 1:]:
                    self.assertFalse(
                        self.can_reach_location(later_location), later_location,
                    )

    def test_a_business_purchase_needs_its_item_too(self) -> None:
        # A business purchase carries the term through the property-sale
        # requirements rather than its own table entry, so it needs pinning
        # separately from the safehouse path.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name([
            "Progressive Vercetti Protection", "Starfish Island Access",
            "Mainland Access",
        ])
        self.assertFalse(self.can_reach_location("Malibu Club Purchase"))
        self.collect_by_name([data.PROPERTY_PURCHASES_ITEM])
        self.assertTrue(self.can_reach_location("Malibu Club Purchase"))

    def test_a_stunt_jump_needs_its_item_beyond_the_mainland(self) -> None:
        self.collect_by_name(["Mainland Access"])
        self.assertFalse(self.can_reach_location(data.stunt_jump_name(1)))
        self.collect_by_name([data.STUNT_JUMPS_ITEM])
        self.assertTrue(self.can_reach_location(data.stunt_jump_name(1)))

    def test_the_lock_flags_and_unlock_globals_reach_the_mod(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["content_locks"], sorted(_ALL_CONTENT_LOCKS))
        config = slot_data["config_globals"]
        item_globals = slot_data["item_globals"]
        for name in data.CONTENT_ITEMS:
            self.assertEqual(config[str(scm.content_lock_flag_global(name))], 1, name)
            self.assertEqual(
                item_globals[str(ITEM_NAME_TO_ID[name])],
                scm.content_unlock_global(name), name,
            )


class TestContentLocksPerClass(WorldTestBase):
    # Every class held, split into one item per class per district. The
    # inherited default tests prove the seed still fills and stays reachable
    # with 42 progression items where there were 5.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "content_locks": _ALL_CONTENT_LOCKS,
        "split_content_locks": "per_class",
    }

    def test_the_pool_holds_the_district_items_and_not_the_class_ones(self) -> None:
        pool_names = {item.name for item in self.multiworld.itempool}
        for name in data.CONTENT_ITEMS:
            self.assertNotIn(name, pool_names, name)
        expected = data.content_items(frozenset(_ALL_CONTENT_LOCKS),
                                     data.CONTENT_SPLIT_PER_CLASS)
        self.assertEqual(len(expected), 42)
        for name in expected:
            self.assertIn(name, pool_names, name)
            self.assertEqual(
                ITEM_CLASSIFICATIONS[name], ItemClassification.progression, name,
            )

    def test_a_district_item_releases_its_district_and_no_other(self) -> None:
        # Package 1 is Ocean Beach and package 2 is Washington Beach, so one
        # item cannot open both: this is the whole point of the split, and it is
        # what a single class-wide term would silently undo.
        first = data.hidden_package_name(1)
        second = data.hidden_package_name(2)
        self.assertEqual(data.location_district(first), "Ocean Beach")
        self.assertEqual(data.location_district(second), "Washington Beach")
        self.assertFalse(self.can_reach_location(first))
        self.assertFalse(self.can_reach_location(second))
        self.collect_by_name(["Ocean Beach Hidden Packages"])
        self.assertTrue(self.can_reach_location(first))
        self.assertFalse(self.can_reach_location(second))
        self.collect_by_name(["Washington Beach Hidden Packages"])
        self.assertTrue(self.can_reach_location(second))

    def test_a_class_item_does_not_leak_across_classes(self) -> None:
        # Ocean Beach holds packages, rampages, jumps and properties, and each
        # class waits for its own item there. A district-wide term would open
        # all four at once, which is the per_district behaviour, not this one.
        self.collect_by_name(["Mainland Access", "Ocean Beach Hidden Packages"])
        self.assertTrue(self.can_reach_location(data.hidden_package_name(1)))
        rampage = next(
            data.rampage_name(index) for index in range(1, data.RAMPAGE_COUNT + 1)
            if data.location_district(data.rampage_name(index)) == "Ocean Beach"
        )
        self.assertFalse(self.can_reach_location(rampage))
        self.collect_by_name(["Ocean Beach Rampages"])
        self.assertTrue(self.can_reach_location(rampage))

    def test_a_business_purchase_needs_its_own_district(self) -> None:
        # A business purchase carries its content term through the property-sale
        # requirements, so the split has to reach it there rather than through
        # the location's own entry. The Malibu Club is Vice Point.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name([
            "Progressive Vercetti Protection", "Starfish Island Access",
            "Mainland Access",
        ])
        self.assertFalse(self.can_reach_location("Malibu Club Purchase"))
        self.collect_by_name(["Ocean Beach Property Purchases"])
        self.assertFalse(self.can_reach_location("Malibu Club Purchase"))
        self.collect_by_name(["Vice Point Property Purchases"])
        self.assertTrue(self.can_reach_location("Malibu Club Purchase"))

    def test_the_42_items_fit_the_pool(self) -> None:
        # 42 progression items where the whole locks put 5, so filler is what
        # gives way. create_items refuses a pool with more progression and useful
        # items than checks, so generating at all is the assertion; the counts
        # are here so a later class or item change says which side moved.
        pool_names = [item.name for item in self.multiworld.itempool]
        district_items = [name for name in pool_names
                          if name in DISTRICT_CONTENT_NAMES]
        self.assertEqual(len(district_items), 42)
        self.assertEqual(len(pool_names),
                         len(self.multiworld.get_unfilled_locations(self.player)))

    def test_the_fan_out_and_the_pickup_districts_reach_the_mod(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["split_content_locks"],
                         data.CONTENT_SPLIT_PER_CLASS)
        fan_out = slot_data["content_district_globals"]
        # A class-in-one-district item releases exactly one global, and it is
        # the one its own class and district name.
        item_id = str(ITEM_NAME_TO_ID["Ocean Beach Hidden Packages"])
        self.assertEqual(
            fan_out[item_id],
            [scm.district_unlock_global(data.HIDDEN_PACKAGES_ITEM, "Ocean Beach")],
        )
        # A whole-class item releases all eleven of its class's, which is what
        # lets one script gate serve every granularity.
        whole = str(ITEM_NAME_TO_ID[data.HIDDEN_PACKAGES_ITEM])
        self.assertEqual(len(fan_out[whole]), len(scm.DISTRICT_KEYS))
        # Every held pickup is placed, and no entry names a district or class
        # outside the block.
        entries = slot_data["content_districts"]
        self.assertEqual(len(entries), 150)
        for entry in entries:
            self.assertIn(entry["class"], range(len(scm.CONTENT_KEYS)))
            self.assertIn(entry["district"], range(len(scm.DISTRICT_KEYS)))


class TestContentLocksPerDistrict(WorldTestBase):
    # Every class held, split into one item per district covering all of them.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "content_locks": _ALL_CONTENT_LOCKS,
        "split_content_locks": "per_district",
    }

    def test_one_item_per_district_covers_every_class_there(self) -> None:
        pool_names = {item.name for item in self.multiworld.itempool}
        expected = data.content_items(frozenset(_ALL_CONTENT_LOCKS),
                                      data.CONTENT_SPLIT_PER_DISTRICT)
        self.assertEqual(len(expected), 11)
        for name in expected:
            self.assertIn(name, pool_names, name)
        for name in data.CONTENT_ITEMS:
            self.assertNotIn(name, pool_names, name)
        # One item, every class in that district: the package and the rampage
        # both open, where per_class would need two items.
        self.collect_by_name(["Mainland Access", "Ocean Beach Content"])
        self.assertTrue(self.can_reach_location(data.hidden_package_name(1)))
        rampage = next(
            data.rampage_name(index) for index in range(1, data.RAMPAGE_COUNT + 1)
            if data.location_district(data.rampage_name(index)) == "Ocean Beach"
        )
        self.assertTrue(self.can_reach_location(rampage))

    def test_a_district_item_releases_one_global_per_class_it_covers(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["split_content_locks"],
                         data.CONTENT_SPLIT_PER_DISTRICT)
        fan_out = slot_data["content_district_globals"]
        for district in data.CONTENT_DISTRICTS:
            item_id = str(ITEM_NAME_TO_ID[data.district_content_item_name(district)])
            covered = [item for item in data.CONTENT_ITEMS
                       if district in data.CONTENT_CLASS_DISTRICTS[item]]
            self.assertEqual(
                sorted(fan_out[item_id]),
                sorted(scm.district_unlock_global(item, district) for item in covered),
                district,
            )


class TestCommonMaximalLocks(WorldTestBase):
    # The option set a player is most likely to choose: every content key split
    # to its finest, three ability keys, the emergency class off, both draws on
    # and the world modifiers. Its start is one check wide, so the inherited
    # fill test is what proves the directed opener carries the seed.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "goal": "hidden_packages",
        "hidden_packages_required": 50,
        "enable_emergency_vehicles": False,
        "shuffle_emergency_rewards": True,
        "randomize_radio_stations": True,
        "split_mainland_access": True,
        "randomize_pickups": True,
        "ability_locks": ["vehicles", "weapon_equip", "wallet"],
        "starting_ability_unlock": True,
        "content_locks": _ALL_CONTENT_LOCKS,
        "split_content_locks": "per_class",
        "starting_content_unlock": True,
        "trap_percentage": 15,
        "death_link": True,
    }

    def test_the_start_is_one_check_wide(self) -> None:
        # The premise the rest of this class rests on: nothing but the first
        # mission is open on a new game, so the seed fills only because the
        # opener is directed into that one check.
        self.assertEqual(self.world._free_start_location_count(), 1)

    def test_the_directed_opener_is_the_strongest_content_item(self) -> None:
        # The selection rule rather than the item it lands on: whichever content
        # item opens the most of the start island is the one directed, so a seed
        # never spends its one open check on an unlock worth a check or two.
        location_rules = self.world._location_rules()
        state = CollectionState(self.multiworld)
        openings = {
            name: self.world._start_locations_opened_by(
                name, location_rules, state)
            for name in self.world._content_items()
        }
        directed = self.world.directed_opening_item
        self.assertEqual(openings[directed], max(openings.values()))
        self.assertGreaterEqual(openings[directed], MINIMUM_DIRECTED_SPHERE_ZERO)
        self.assertEqual(
            self.multiworld.local_early_items[self.player][directed], 1)

    def test_the_opener_stays_a_reward_in_the_pool(self) -> None:
        # An early item, not starting inventory: the opener is still what some
        # check pays out, which is what separates directing it from granting it.
        directed = self.world.directed_opening_item
        self.assertIn(directed, [item.name for item in self.multiworld.itempool])
        self.assertNotIn(directed, [
            item.name for item in self.multiworld.precollected_items[self.player]])


class TestContentLocksOff(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: content_locks is empty.

    def test_no_content_items_and_vanilla_flags(self) -> None:
        pool_names = {item.name for item in self.multiworld.itempool}
        precollected = {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        for name in data.CONTENT_ITEMS:
            self.assertNotIn(name, pool_names, name)
            self.assertNotIn(name, precollected, name)
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["content_locks"], [])
        config = slot_data["config_globals"]
        for name in data.CONTENT_ITEMS:
            self.assertEqual(config[str(scm.content_lock_flag_global(name))], 0, name)

    def test_no_content_terms_without_the_locks(self) -> None:
        # No rule may name an item that is not in the pool, so every class is
        # free within its region.
        self.assertTrue(self.can_reach_location(data.hidden_package_name(1)))
        self.assertTrue(self.can_reach_location(data.robbable_store_name(1)))
        self.assertTrue(self.can_reach_location("El Swanko Casa Purchase"))


class TestContentLockOnADisabledClass(WorldTestBase):
    # The case the toggle invariant is amended for: the properties class is
    # off, so its purchases are not checks and its items leave the pool, but
    # the key still holds the icons in game. Vanilla asset completion needs
    # properties bought, so the finale must carry the term even though no
    # purchase location exists to carry it.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "enable_properties": False, "content_locks": ["properties"],
    }

    def test_the_item_is_in_the_pool_without_its_class(self) -> None:
        pool_names = {item.name for item in self.multiworld.itempool}
        self.assertIn(data.PROPERTY_PURCHASES_ITEM, pool_names)
        for ownership in data.PROPERTY_OWNERSHIP_ITEMS:
            self.assertNotIn(ownership, pool_names, ownership)
        location_names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertNotIn("El Swanko Casa Purchase", location_names)

    def test_the_finale_carries_the_term_through_the_sale_requirements(self) -> None:
        # Nothing can be bought while the icons are held, so the finale's
        # vanilla asset prerequisite cannot be met without the item. Without
        # this the seed generates unbeatable.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name([
            "Progressive Vercetti Finale", "Progressive Vercetti Protection",
            "Mainland Access", "Starfish Island Access",
        ])
        self.assertFalse(self.can_reach_location("Cap the Collector"))
        self.collect_by_name([data.PROPERTY_PURCHASES_ITEM])
        self.assertTrue(self.can_reach_location("Cap the Collector"))


class TestContentLockOnADisabledCollectibleClass(WorldTestBase):
    # The non-properties half of the amended toggle invariant: rampages are not
    # checks this seed, but the key still holds their icons, so the item is in
    # the pool with no location to gate. It stays progression regardless, the
    # Sprint precedent.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "enable_rampages": False, "content_locks": ["rampages"],
    }

    def test_the_item_ships_without_its_locations(self) -> None:
        pool_names = {item.name for item in self.multiworld.itempool}
        self.assertIn(data.RAMPAGES_ITEM, pool_names)
        self.assertEqual(
            ITEM_CLASSIFICATIONS[data.RAMPAGES_ITEM], ItemClassification.progression,
        )
        location_names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertNotIn(data.rampage_name(1), location_names)

    def test_the_lock_flag_is_stamped_for_the_disabled_class(self) -> None:
        # The ASI has to hold the icons even though nothing is a check, so the
        # flag rides content_locks alone and never the class toggle.
        config = self.world.fill_slot_data()["config_globals"]
        self.assertEqual(
            config[str(scm.content_lock_flag_global(data.RAMPAGES_ITEM))], 1,
        )


class TestContentAndAbilityLocksCompose(WorldTestBase):
    # Both families on the same locations. Either lock alone still stops the
    # content, so the terms union rather than one superseding the other.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "content_locks": ["robbable_stores", "rampages"],
        "ability_locks": ["weapon_equip", "vehicles"],
    }

    def test_a_store_needs_both_items(self) -> None:
        self.assertFalse(self.can_reach_location(data.robbable_store_name(1)))
        self.collect_by_name([data.ROBBABLE_STORES_ITEM])
        self.assertFalse(self.can_reach_location(data.robbable_store_name(1)))
        self.collect_by_name([data.WEAPON_EQUIP_ITEM])
        self.assertTrue(self.can_reach_location(data.robbable_store_name(1)))

    def test_a_vehicle_rampage_keeps_its_own_ability_term(self) -> None:
        # The two run-them-down rampages take a land vehicle rather than the
        # weapon, and the content lock stacks on top of that split.
        vehicle_rampage = data.rampage_name(min(data.VEHICLE_RAMPAGE_INDICES))
        # Both area items, so the test reads the lock terms and not the island
        # the rampage happens to sit on.
        self.collect_by_name([
            "Mainland Access", "Starfish Island Access", data.RAMPAGES_ITEM,
        ])
        self.assertFalse(self.can_reach_location(vehicle_rampage))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location(vehicle_rampage))


class TestStartingUnlocksOn(WorldTestBase):
    # One lock item per family arrives as starting inventory, drawn by the seed.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "ability_locks": ["vehicles", "weapon_equip", "wallet"],
        "content_locks": ["rampages", "stunt_jumps", "robbable_stores"],
        "starting_ability_unlock": True,
        "starting_content_unlock": True,
    }

    def _precollected(self) -> list[str]:
        return [item.name for item in self.multiworld.precollected_items[self.player]]

    def test_one_ability_and_one_content_item_start_held(self) -> None:
        precollected = self._precollected()
        abilities = [name for name in precollected if name in data.ABILITY_ITEMS]
        contents = [name for name in precollected if name in data.CONTENT_ITEMS]
        self.assertEqual(len(abilities), 1)
        self.assertEqual(len(contents), 1)
        self.assertEqual(abilities[0], self.world.starting_ability_item)
        self.assertEqual(contents[0], self.world.starting_content_item)

    def test_the_draw_only_names_an_item_a_selected_key_offers(self) -> None:
        # The vehicles key offers three items, so the ability draw is over items
        # and may name any one of them; an unselected key can never be drawn.
        eligible_abilities = {
            data.LAND_VEHICLES_ITEM, data.SEA_VEHICLES_ITEM, data.AIR_VEHICLES_ITEM,
            data.WEAPON_EQUIP_ITEM, data.WALLET_ITEM,
        }
        self.assertIn(self.world.starting_ability_item, eligible_abilities)
        self.assertIn(self.world.starting_content_item, {
            data.RAMPAGES_ITEM, data.STUNT_JUMPS_ITEM, data.ROBBABLE_STORES_ITEM,
        })

    def test_a_started_item_leaves_the_pool(self) -> None:
        # Starting inventory instead of a pool item, never both: one copy of a
        # lock item exists, so the pool holds every other selected item and not
        # this one.
        pool = [item.name for item in self.multiworld.itempool]
        self.assertNotIn(self.world.starting_ability_item, pool)
        self.assertNotIn(self.world.starting_content_item, pool)
        for name in (data.RAMPAGES_ITEM, data.STUNT_JUMPS_ITEM,
                     data.ROBBABLE_STORES_ITEM):
            if name != self.world.starting_content_item:
                self.assertIn(name, pool, name)
        # The vehicles key owns three items and the draw takes one, so the other
        # two are still pool items: a removal that took the whole key would be
        # invisible in the precollect count alone.
        for name in (data.LAND_VEHICLES_ITEM, data.SEA_VEHICLES_ITEM,
                     data.AIR_VEHICLES_ITEM, data.WEAPON_EQUIP_ITEM,
                     data.WALLET_ITEM):
            if name != self.world.starting_ability_item:
                self.assertIn(name, pool, name)

    def test_both_draws_are_in_the_state_from_the_first_sphere(self) -> None:
        # Starting inventory is collected state, so every rule naming either
        # drawn item is satisfied before a single check is sent.
        self.assertTrue(
            self.multiworld.state.has(self.world.starting_ability_item, self.player))
        self.assertTrue(
            self.multiworld.state.has(self.world.starting_content_item, self.player))

    def test_the_pool_still_fills_every_location(self) -> None:
        # The draw takes an item out of the pool, and the filler slice has to
        # grow by exactly that much: the fill's own check only catches a pool
        # too large, never one item short.
        placed = [item for item in self.multiworld.itempool if item.player == self.player]
        self.assertEqual(len(placed), _check_count(self.multiworld, self.player))

    def test_slot_data_carries_both_draws(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertTrue(slot_data["starting_ability_unlock"])
        self.assertTrue(slot_data["starting_content_unlock"])
        self.assertEqual(slot_data["starting_ability_item"],
                         self.world.starting_ability_item)
        self.assertEqual(slot_data["starting_content_item"],
                         self.world.starting_content_item)


class TestStartingUnlockReleasesItsClass(WorldTestBase):
    # A single content key forces the draw, so what the release actually buys is
    # testable: the class opens with no item from the multiworld at all.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "content_locks": ["rampages"],
        "starting_content_unlock": True,
    }

    def test_a_start_island_rampage_needs_nothing_further(self) -> None:
        self.assertEqual(self.world.starting_content_item, data.RAMPAGES_ITEM)
        start_rampages = [
            data.rampage_name(index)
            for index in range(1, data.RAMPAGE_COUNT + 1)
            if LOCATION_REGIONS[data.rampage_name(index)] == data.REGION_VICE_CITY
            and index not in data.VEHICLE_RAMPAGE_INDICES
        ]
        self.assertTrue(start_rampages)
        for name in start_rampages:
            self.assertTrue(self.can_reach_location(name), name)


class TestStartingUnlocksWithoutKeys(WorldTestBase):
    # The option on with no key selected has nothing to draw from, which is a
    # quiet no-op rather than an error: a player turning locks off leaves it set.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "starting_ability_unlock": True,
        "starting_content_unlock": True,
    }

    def test_nothing_is_drawn_and_nothing_is_precollected(self) -> None:
        self.assertIsNone(self.world.starting_ability_item)
        self.assertIsNone(self.world.starting_content_item)
        precollected = {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        for name in data.ABILITY_ITEMS + data.CONTENT_ITEMS:
            self.assertNotIn(name, precollected, name)
        slot_data = self.world.fill_slot_data()
        self.assertIsNone(slot_data["starting_ability_item"])
        self.assertIsNone(slot_data["starting_content_item"])


class TestStartingContentUnlockStaysOnTheStartIsland(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "starting_content_unlock": True,
        "content_locks": ["hidden_packages", "rampages", "stunt_jumps",
                          "properties", "robbable_stores"],
        "split_content_locks": "per_district",
        "enable_hidden_packages": True, "enable_rampages": True,
        "enable_stunt_jumps": True, "enable_properties": True,
        "enable_robbable_stores": True,
    }

    def test_the_draw_never_hands_over_a_district_off_the_island(self) -> None:
        # A STARTING unlock has to be worth something at the start. Split per
        # district, most content items hold a district the player cannot reach on
        # a new game, so drawing one would hand over an item that does nothing
        # until the mainland opens.
        #
        # Asserted over many rolls rather than one. Six of the eleven districts
        # are off the island, so a single roll lands on the island about half the
        # time by luck: one assertion here passed with the filter deleted, which
        # is worse than no assertion. Re-seeding the world's own random and
        # re-drawing is what makes it bite.
        seen = set()
        for seed in range(40):
            self.world.random.seed(seed)
            self.world._choose_starting_unlocks(None)
            drawn = self.world.starting_content_item
            self.assertIsNotNone(drawn)
            district = data.content_item_district(drawn)
            self.assertIsNotNone(district, drawn)
            self.assertEqual(
                data.district_region(district), data.REGION_VICE_CITY,
                f"{drawn} holds {district}, which is off the start island")
            seen.add(district)
        # And the rolls really do vary, so this is not forty copies of one draw.
        self.assertGreater(len(seen), 1)

    def test_a_district_name_is_never_a_prefix_of_another(self) -> None:
        # content_item_district reads the leading district name off an item name,
        # which only works while no district name is a prefix of another followed
        # by a space. "Vice Point" and a hypothetical "Vice Point North" would
        # both match the shorter one, and the item would hold the wrong district.
        for district in district_data.DISTRICTS:
            for other in district_data.DISTRICTS:
                if district is other:
                    continue
                self.assertFalse(other.startswith(f"{district} "),
                                 f"{other} starts with {district}")

    def test_every_content_item_classifies(self) -> None:
        # It fails OPEN: a name matching no district returns None, and None reads
        # as a whole-class item, which reads as on the start island. So a district
        # item this stopped recognising would silently widen the draw rather than
        # raise. Every item is classified here so that cannot go unnoticed.
        every = frozenset(data.CONTENT_LOCK_ITEMS)
        whole_class = data.content_items(every, data.CONTENT_SPLIT_OFF)
        for name in whole_class:
            with self.subTest(name=name):
                self.assertIsNone(data.content_item_district(name))
                self.assertTrue(data.content_item_on_start_island(name))
        for split in (data.CONTENT_SPLIT_PER_DISTRICT, data.CONTENT_SPLIT_PER_CLASS):
            for name in data.content_items(every, split):
                with self.subTest(split=split, name=name):
                    district = data.content_item_district(name)
                    self.assertIn(district, district_data.DISTRICTS, name)
                    self.assertEqual(
                        data.content_item_on_start_island(name),
                        data.district_region(district) == data.REGION_VICE_CITY,
                        name)

    def test_a_seed_drawn_before_the_narrowing_keeps_its_item(self) -> None:
        # The narrowing decides what a NEW seed rolls. A seed already being
        # played carries its draw in slot_data, and an off-island name there is
        # still that seed's answer: dropping it would leave the item in the pool
        # while the tracker showed every Downtown location gated on something the
        # player was told they held.
        off_island = [name for name in self.world._content_items()
                      if not data.content_item_on_start_island(name)
                      and name != self.world.directed_opening_item]
        self.assertTrue(off_island)
        for name in off_island[:4]:
            with self.subTest(name=name):
                self.world._choose_starting_unlocks({"starting_content_item": name})
                self.assertEqual(self.world.starting_content_item, name)

    def test_a_replayed_name_the_seed_cannot_offer_is_still_dropped(self) -> None:
        # The wider list is the seed's own items, not everything: slot_data from a
        # different set of keys must not ask create_items for an item the pool
        # never had.
        self.world._choose_starting_unlocks(
            {"starting_content_item": "Hidden Packages"})
        self.assertIsNone(self.world.starting_content_item)

    def test_every_candidate_is_reachable_and_the_others_are_not_lost(self) -> None:
        # The filter narrows the draw, not the pool: the districts it excludes are
        # still held and still arrive as items later.
        candidates = [name for name in self.world._content_items()
                      if data.content_item_on_start_island(name)]
        excluded = [name for name in self.world._content_items()
                    if not data.content_item_on_start_island(name)]
        self.assertTrue(candidates)
        self.assertTrue(excluded)
        pool = {item.name for item in self.multiworld.itempool}
        pool |= {item.name for item in
                 self.multiworld.precollected_items[self.player]}
        for name in excluded:
            self.assertIn(name, pool, name)


class TestStartingUnlocksOff(WorldTestBase):
    # Locks selected, the draw off: every lock item waits in the pool.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "ability_locks": ["sprint", "wallet"],
        "content_locks": ["rampages", "properties"],
    }

    def test_every_lock_item_is_a_pool_item(self) -> None:
        self.assertIsNone(self.world.starting_ability_item)
        self.assertIsNone(self.world.starting_content_item)
        pool = [item.name for item in self.multiworld.itempool]
        for name in (data.SPRINT_ITEM, data.WALLET_ITEM, data.RAMPAGES_ITEM,
                     data.PROPERTY_PURCHASES_ITEM):
            self.assertIn(name, pool, name)
        slot_data = self.world.fill_slot_data()
        self.assertFalse(slot_data["starting_ability_unlock"])
        self.assertFalse(slot_data["starting_content_unlock"])


class TestStartingUnlocksRegeneration(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    auto_construct = False

    def _regenerate(self, slot_data: dict):
        # A whole generation with the passthrough in place, the way the tracker
        # runs it, so create_items sees the restored draw and not just
        # generate_early.
        tracker = setup_multiworld(GTAViceCityWorld, steps=())
        tracker.re_gen_passthrough = {GTAViceCityWorld.game: slot_data}
        for step in gen_steps:
            call_all(tracker, step)
        return tracker

    def test_a_tracker_regeneration_replays_the_played_draw(self) -> None:
        played = setup_multiworld(GTAViceCityWorld, seed=0, options={
            "ability_locks": ["vehicles"],
            "content_locks": ["rampages", "stunt_jumps"],
            "starting_ability_unlock": True,
            "starting_content_unlock": True,
        })
        world = played.worlds[1]
        slot_data = GTAViceCityWorld.interpret_slot_data(world.fill_slot_data())

        tracker = self._regenerate(slot_data)
        replayed = tracker.worlds[1]
        self.assertEqual(replayed.starting_ability_item, world.starting_ability_item)
        self.assertEqual(replayed.starting_content_item, world.starting_content_item)
        # The replay precollects the same two items, so the tracker reads the
        # played seed's reachability and not its own. Filler is not compared:
        # the tracker regenerates on its own seed, so its mirror sample and trap
        # draw legitimately differ.
        self.assertEqual(
            sorted(item.name for item in tracker.precollected_items[1]),
            sorted(item.name for item in played.precollected_items[1]),
        )
        pool = {item.name for item in tracker.itempool}
        self.assertNotIn(replayed.starting_ability_item, pool)
        self.assertNotIn(replayed.starting_content_item, pool)
        for name in (data.RAMPAGES_ITEM, data.STUNT_JUMPS_ITEM):
            if name != replayed.starting_content_item:
                self.assertIn(name, pool, name)

    def test_a_tracker_regeneration_replays_the_split_granularity(self) -> None:
        # A split seed's rules name district items, which only exist in the pool
        # while the granularity is restored too. Replayed at the wrong
        # granularity every collectible reads as gated on a whole-class item the
        # player never receives, so the tracker would show a seed nobody could
        # play.
        played = setup_multiworld(GTAViceCityWorld, seed=0, options={
            "content_locks": ["rampages", "stunt_jumps"],
            "split_content_locks": "per_class",
            "starting_content_unlock": True,
        })
        world = played.worlds[1]
        slot_data = GTAViceCityWorld.interpret_slot_data(world.fill_slot_data())
        self.assertEqual(slot_data["split_content_locks"],
                         data.CONTENT_SPLIT_PER_CLASS)

        tracker = self._regenerate(slot_data)
        replayed = tracker.worlds[1]
        self.assertEqual(replayed.options.split_content_locks.value,
                         data.CONTENT_SPLIT_PER_CLASS)
        self.assertEqual(replayed.starting_content_item, world.starting_content_item)
        pool = {item.name for item in tracker.itempool}
        precollected = {item.name for item in tracker.precollected_items[1]}
        for name in data.content_items(frozenset({"rampages", "stunt_jumps"}),
                                       data.CONTENT_SPLIT_PER_CLASS):
            self.assertIn(name, pool | precollected, name)
        # And the whole-class items stay out, since the split replaced them.
        self.assertNotIn(data.RAMPAGES_ITEM, pool)
        self.assertNotIn(data.STUNT_JUMPS_ITEM, pool)

    def test_a_draw_the_restored_keys_no_longer_offer_is_dropped(self) -> None:
        # Mismatched slot_data (hand-edited, or written by an older world) must
        # not ask create_items to precollect an item no key put in the pool.
        # Generation has to survive it, not merely report None.
        slot_data = dict(_TRACKER_SLOT_DATA)
        slot_data.update({
            "ability_locks": ["wallet"],
            "content_locks": ["rampages"],
            "starting_ability_unlock": True,
            "starting_content_unlock": True,
            "starting_ability_item": data.SEA_VEHICLES_ITEM,
            "starting_content_item": data.STUNT_JUMPS_ITEM,
        })
        tracker = self._regenerate(slot_data)
        replayed = tracker.worlds[1]
        self.assertIsNone(replayed.starting_ability_item)
        self.assertIsNone(replayed.starting_content_item)
        precollected = {item.name for item in tracker.precollected_items[1]}
        self.assertNotIn(data.SEA_VEHICLES_ITEM, precollected)
        self.assertNotIn(data.STUNT_JUMPS_ITEM, precollected)
        # The keys the restore did name still put their own items in the pool.
        pool = {item.name for item in tracker.itempool}
        self.assertIn(data.WALLET_ITEM, pool)
        self.assertIn(data.RAMPAGES_ITEM, pool)


class TestStrandAccess(WorldTestBase):
    game = "Grand Theft Auto Vice City"

    def test_a_strand_the_audit_chains_to_nothing_opens_on_its_own(self) -> None:
        # The Chase is Diaz's first mission, given from the mansion on Starfish
        # Island. The audit opens Diaz's strand "After An Old Friend", which
        # costs nothing, so its rule is a Diaz unlock plus the island and no
        # other strand's items. Nine of the twelve story strands are like this;
        # the three the audit does chain are pinned below.
        self.collect_by_name(["Progressive Diaz"])
        self.assertFalse(self.can_reach_location("The Chase"))
        self.collect_by_name(["Starfish Island Access"])
        self.assertTrue(self.can_reach_location("The Chase"))
        self.assertEqual(sorted(data.STRAND_PREREQUISITES),
                         ["Death Row", "Vercetti Finale", "Vercetti Protection"])

    def test_avery_unlocks_in_vanilla_play_order(self) -> None:
        # Avery's vanilla chain is Four Iron, Demolition Man, Two Bit Hit: his
        # launchers start missions 18, 19 and 20 in that order, and Four Iron's
        # pass is what starts Demolition Man's launcher. His mission threads are
        # named SERG1, SERG3, SERG2, so pairing launchers by thread name puts
        # Two Bit Hit second.
        self.collect_by_name(_MANSION_CHAIN)
        self.assertEqual(
            data.STORY_GIVERS["Avery"], ["Four Iron", "Demolition Man", "Two Bit Hit"])
        # Avery gives from the mainland. No ability key is selected here, so the
        # three carry no ability term and the order is the only thing under test.
        self.collect_by_name(["Mainland Access"])
        progressives = self.get_items_by_name("Progressive Avery")
        self.assertFalse(self.can_reach_location("Four Iron"))
        self.collect(progressives[0])
        self.assertTrue(self.can_reach_location("Four Iron"))
        self.assertFalse(self.can_reach_location("Demolition Man"))
        self.collect(progressives[1])
        self.assertTrue(self.can_reach_location("Demolition Man"))
        self.assertFalse(self.can_reach_location("Two Bit Hit"))
        self.collect(progressives[2])
        self.assertTrue(self.can_reach_location("Two Bit Hit"))

    def test_rub_out_requires_death_row(self) -> None:
        # Rub Out, Diaz's last mission, keeps the one mission-level cross-giver
        # edge: Lance must be rescued in Death Row first.
        # Death Row is played on the mainland and Rub Out inherits that across
        # the edge, so the crossing is collected here to leave the edge itself as
        # the thing under test. Its weapon is inherited too, and is covered where
        # the ability keys are on, in
        # test_a_cross_giver_edge_carries_what_it_implies.
        self.collect_by_name([name for name in _MANSION_CHAIN
                              if name != "Progressive Death Row"])
        self.collect_by_name(["Progressive Diaz", "Starfish Island Access",
                              "Mainland Access"])
        self.assertFalse(self.can_reach_location("Rub Out"))
        self.collect_by_name(["Progressive Death Row"])
        self.assertTrue(self.can_reach_location("Rub Out"))

    def test_final_mission_requires_the_protection_strand(self) -> None:
        # The finale keeps the one strand-level cross-giver edge: it sits
        # behind the protection strand. The asset items are collected up
        # front so the protection edge is the only thing under test.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name([
            "Progressive Vercetti Finale", "Mainland Access", "Starfish Island Access",
        ])
        self.collect_by_name(_FINALE_ASSET_ITEMS)
        self.assertFalse(self.can_reach_location(data.FINAL_MISSION))
        self.collect_by_name(["Progressive Vercetti Protection"])
        self.assertTrue(self.can_reach_location(data.FINAL_MISSION))


class TestSplitMainlandAccessOff(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: split_mainland_access is off.

    def test_one_item_opens_the_mainland_and_no_crossing_exists(self) -> None:
        pool_names = {item.name for item in self.multiworld.itempool}
        self.assertIn("Mainland Access", pool_names)
        for crossing in data.MAINLAND_CROSSING_ITEMS:
            self.assertNotIn(crossing, pool_names, crossing)
        self.assertFalse(self.multiworld.get_region("Mainland", self.player).can_reach(
            self.multiworld.state))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.multiworld.get_region("Mainland", self.player).can_reach(
            self.multiworld.state))

    def test_slot_data_says_the_crossings_are_whole(self) -> None:
        self.assertFalse(self.world.fill_slot_data()["split_mainland_access"])

    def test_one_route_is_shipped_for_the_asi_to_announce(self) -> None:
        # The ASI cannot tell the setting from item_globals, which maps every
        # area item either way, so it reads the crossings from here. One mainland
        # entry means they are whole, and Starfish Island is always its own row:
        # the page was silent about that crossing before, which is the one a
        # player asks about as often as any bridge.
        routes = self.world.fill_slot_data()["mainland_routes"]
        self.assertEqual(routes, [
            {"global": scm.unlock_global("Mainland Access"),
             "label": "The mainland", "needs_global": 0, "needs_label": ""},
            {"global": scm.unlock_global("Starfish Island Access"),
             "label": "Starfish Island", "needs_global": 0, "needs_label": ""},
        ])


class TestSplitMainlandAccessOn(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "split_mainland_access": True,
        "enable_hidden_packages": True, "enable_rampages": True,
    }

    def _mainland_reachable(self) -> bool:
        return self.multiworld.get_region("Mainland", self.player).can_reach(
            self.multiworld.state)

    def test_the_crossings_replace_mainland_access_in_the_pool(self) -> None:
        pool_names = {item.name for item in self.multiworld.itempool}
        self.assertNotIn("Mainland Access", pool_names)
        for crossing in data.MAINLAND_CROSSING_ITEMS:
            self.assertIn(crossing, pool_names, crossing)
            self.assertEqual(
                ITEM_CLASSIFICATIONS[crossing],
                ItemClassification.progression, crossing,
            )

    def test_any_one_bridge_opens_the_whole_mainland(self) -> None:
        # One crossing is enough: the west island is roamable once the player is
        # on it, so the split decides where they cross, not whether they can.
        self.assertFalse(self._mainland_reachable())
        self.collect_by_name(["Leaf Links Bridge"])
        self.assertTrue(self._mainland_reachable())
        self.assertTrue(self.can_reach_location(data.hidden_package_name(56)))
        self.assertTrue(self.can_reach_location(
            data.rampage_name(2)))

    def test_each_bridge_opens_it_on_its_own(self) -> None:
        # Every crossing is a whole answer by itself, so the fill may place the
        # mainland behind any one of them.
        for crossing in ["Prawn Island Bridge", "Leaf Links Bridge",
                         "Ocean Beach Bridge"]:
            with self.subTest(crossing=crossing):
                self.remove_by_name(data.MAINLAND_CROSSING_ITEMS)
                self.assertFalse(self._mainland_reachable())
                self.collect_by_name([crossing])
                self.assertTrue(self._mainland_reachable())
        self.remove_by_name(data.MAINLAND_CROSSING_ITEMS)

    def test_death_row_needs_the_bridge_its_drive_uses(self) -> None:
        # Death Row is the one mission the mainland is not enough for: its drive
        # only works across the Leaf Links bridge, so reaching the west island by
        # any other crossing leaves it uncompletable. Everything inheriting it
        # carries the same term, which is most of the game.
        self.assertEqual(data.MISSION_CROSSING_REQUIREMENTS,
                         {"Death Row": "Leaf Links Bridge"})
        self.collect_by_name(["Progressive Death Row", "Progressive Cortez",
                              "Progressive Diaz", "Progressive Rosenberg",
                              "Starfish Island Access", "Ocean Beach Bridge",
                              "Prawn Island Bridge"])
        self.assertTrue(self._mainland_reachable())
        self.assertFalse(self.can_reach_location("Death Row"))
        self.collect_by_name(["Leaf Links Bridge"])
        self.assertTrue(self.can_reach_location("Death Row"))

    def test_the_causeway_needs_the_island_it_stands_on(self) -> None:
        # The west gate is on Starfish Island, so that crossing is the one
        # behind two items; holding it alone reaches nothing.
        self.collect_by_name(["Starfish Island Causeway"])
        self.assertFalse(self._mainland_reachable())
        self.collect_by_name(["Starfish Island Access"])
        self.assertTrue(self._mainland_reachable())

    def test_starfish_access_alone_still_opens_no_crossing(self) -> None:
        # The island and the mainland stay independent: reaching Starfish must
        # not imply reaching the west island, which is what the vanilla west
        # gate being a separate barrier means.
        self.collect_by_name(["Starfish Island Access"])
        self.assertFalse(self._mainland_reachable())

    def test_the_last_mission_needs_a_way_across(self) -> None:
        # Keep Your Friends Close... sits on Starfish but its launcher waits on
        # Cap the Collector, which is on the mainland, so its own rule carries
        # the crossing choice as a threshold rather than a single item. A crossing
        # is the only way to the mainland there is: the island has audited routes
        # and the mainland has none, so nothing stands in for a bridge.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name([
            "Progressive Vercetti Finale", "Progressive Vercetti Protection",
            "Starfish Island Access",
        ])
        self.collect_by_name(_FINALE_ASSET_ITEMS)
        self.assertFalse(self.can_reach_location(data.FINAL_MISSION))
        # The Leaf Links bridge in particular, since the finale inherits Death
        # Row, whose drive only works across that one. Any other crossing reaches
        # the mainland and still leaves the finale shut.
        self.collect_by_name(["Ocean Beach Bridge"])
        self.assertFalse(self.can_reach_location(data.FINAL_MISSION))
        self.collect_by_name(["Leaf Links Bridge"])
        self.assertTrue(self.can_reach_location(data.FINAL_MISSION))

    def test_slot_data_says_the_crossings_are_split(self) -> None:
        self.assertTrue(self.world.fill_slot_data()["split_mainland_access"])

    def test_every_route_is_shipped_with_what_it_needs(self) -> None:
        # One entry per crossing, each naming the global its item writes and the
        # name to show. Only the causeway carries a second requirement, and the
        # ASI reads it to know the difference between a route that opened and an
        # item that opened nothing yet.
        routes = self.world.fill_slot_data()["mainland_routes"]
        # The mainland crossings, then Starfish Island last, because it is the
        # one a mainland route can depend on.
        self.assertEqual([route["label"] for route in routes],
                         [*data.MAINLAND_CROSSING_ITEMS, "Starfish Island"])
        self.assertEqual(routes[-1]["global"],
                         scm.unlock_global("Starfish Island Access"))
        for route in routes[:-1]:
            self.assertEqual(route["global"], scm.unlock_global(route["label"]))
        needs = {route["label"]: (route["needs_global"], route["needs_label"])
                 for route in routes}
        self.assertEqual(needs["Prawn Island Bridge"], (0, ""))
        self.assertEqual(needs["Leaf Links Bridge"], (0, ""))
        self.assertEqual(needs["Ocean Beach Bridge"], (0, ""))
        self.assertEqual(
            needs["Starfish Island Causeway"],
            (scm.unlock_global("Starfish Island Access"), "Starfish Island Access"))

    def test_a_regeneration_reads_back_the_split(self) -> None:
        # The passthrough decides whether a Universal Tracker regeneration builds
        # the crossings or Mainland Access, so a missing read-back would have the
        # tracker gate the mainland on an item the played seed never handed out.
        slot_data = GTAViceCityWorld.interpret_slot_data(self.world.fill_slot_data())
        tracker = setup_multiworld(GTAViceCityWorld, steps=())
        tracker.re_gen_passthrough = {GTAViceCityWorld.game: slot_data}
        for step in gen_steps:
            call_all(tracker, step)
        pool_names = {item.name for item in tracker.itempool}
        self.assertNotIn("Mainland Access", pool_names)
        for crossing in data.MAINLAND_CROSSING_ITEMS:
            self.assertIn(crossing, pool_names, crossing)


class TestMainlandGating(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "enable_hidden_packages": True, "enable_rampages": True,
        "enable_emergency_vehicles": True,
    }

    def test_mainland_checks_need_mainland_access(self) -> None:
        # Collectibles and emergency milestones carry no rule beyond their region,
        # so a start-island check is reachable with an empty inventory while its
        # mainland counterpart waits on Mainland Access. Covers a rampage (per
        # pickup coordinate), the hidden-package count threshold, and the emergency
        # upper-half pacing.
        for start_name in [data.rampage_name(1),
                            data.rampage_name(34),
                            data.hidden_package_name(1), "Paramedic Level 06"]:
            self.assertTrue(self.can_reach_location(start_name), start_name)
        # Package 56 is Downtown. Package 3 used to stand here and the audit
        # moved it to Ocean Beach, which is the start island.
        mainland = [data.rampage_name(2),
                    data.rampage_name(33),
                    data.hidden_package_name(56), "Paramedic Level 07"]
        for name in mainland:
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name(["Mainland Access"])
        for name in mainland:
            self.assertTrue(self.can_reach_location(name), name)

    def test_mainland_giver_mission_needs_mainland_access(self) -> None:
        # Phil Cassidy is a mainland giver, so his first mission needs its own
        # unlock AND Mainland Access, not the unlock alone.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name(["Progressive Phil Cassidy"])
        self.assertFalse(self.can_reach_location("Gun Runner"))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location("Gun Runner"))

    def test_mr_black_payphones_split_by_island(self) -> None:
        # Mr. Black's payphones span both islands. With his full unlock strand,
        # Road Kill (start island) is reachable but Loose Ends (mainland) still
        # waits on Mainland Access.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name(["Progressive Mr. Black"])
        self.assertTrue(self.can_reach_location("Road Kill"))
        self.assertFalse(self.can_reach_location("Loose Ends"))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location("Loose Ends"))


class TestStarfishGating(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "enable_hidden_packages": True, "enable_rampages": True,
    }

    def test_starfish_checks_need_a_way_onto_the_island(self) -> None:
        # Starfish Island is its own region, and the island's gates open on
        # Starfish Island Access. That is the barrier, not the only way in: the
        # audit flies a helicopter over from the mainland and sails a boat from
        # Cortez's last mission, so a check on the island waits for one of those
        # and not for the item alone.
        starfish = [data.hidden_package_name(51), data.rampage_name(14)]
        for name in starfish:
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name(["Starfish Island Access"])
        for name in starfish:
            self.assertTrue(self.can_reach_location(name), name)
        self.remove_by_name(["Starfish Island Access"])
        for name in starfish:
            self.assertFalse(self.can_reach_location(name), name)
        # The helicopter route, which with no vehicles key selected is the
        # mainland and nothing else.
        self.collect_by_name(["Mainland Access"])
        for name in starfish:
            self.assertTrue(self.can_reach_location(name), name)

    def test_starfish_access_alone_leaves_the_mainland_sealed(self) -> None:
        # The island's west gate opens only with both area items, so Starfish
        # Island Access alone never opens a walkable route onto the mainland.
        self.collect_by_name(["Starfish Island Access"])
        self.assertFalse(self.can_reach_location(data.hidden_package_name(56)))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location(data.hidden_package_name(56)))

    def test_mansion_giver_missions_sit_on_the_island(self) -> None:
        # Diaz and Vercetti Protection give from the mansion, so their first
        # missions need Starfish Island Access besides their own unlock.
        # Neither area item to begin with: the mainland one reaches the island
        # too, by the audit's helicopter route.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name(["Progressive Diaz", "Progressive Vercetti Protection"])
        for name in ["The Chase", "Shakedown"]:
            self.assertFalse(self.can_reach_location(name), name)
        # The mainland comes with them: Shakedown inherits it through Death Row,
        # and The Chase is the first mission of the strand Death Row waits on.
        self.collect_by_name(["Starfish Island Access", "Mainland Access"])
        for name in ["The Chase", "Shakedown"]:
            self.assertTrue(self.can_reach_location(name), name)

    def test_finale_needs_a_way_onto_both_islands(self) -> None:
        # Keep Your Friends Close... starts at the mansion but only activates
        # once Cap the Collector (mainland) passes, so it needs both islands. The
        # asset items are collected up front so the area edge is the only thing
        # under test. It needs both, and neither item stands in for the other:
        # the island's barrier is not the only way onto the island, but the
        # mainland's is the only way onto the mainland.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name([
            "Progressive Vercetti Finale", "Progressive Vercetti Protection",
        ])
        self.collect_by_name(_FINALE_ASSET_ITEMS)
        self.collect_by_name(["Starfish Island Access"])
        self.assertFalse(self.can_reach_location(data.FINAL_MISSION))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location(data.FINAL_MISSION))
        self.assertTrue(self.can_reach_location("Cap the Collector"))


class TestHiddenPackagesGoalNeedsMainland(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"goal": "hidden_packages", "hidden_packages_required": 80}

    def test_high_package_goal_pulls_in_the_mainland(self) -> None:
        # The 100 Package Fragment macguffins are progression, so the fill must make
        # all of them reachable, which pulls in Mainland Access and the mainland
        # locations. A mainland package location stays gated until Mainland
        # Access; the default solvability tests prove the goal seed still beats.
        self.assertFalse(self.can_reach_location(data.hidden_package_name(76)))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location(data.hidden_package_name(76)))


class TestPropertyAccess(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_properties": True}

    def test_business_purchase_needs_the_shakedown_items(self) -> None:
        # A business goes on sale only when Shakedown passes, so its purchase
        # requires everything logic needs to pass Shakedown: its unlock item
        # and Starfish Island Access, since Shakedown gives from the mansion,
        # and the mainland, since the chain that opens the mansion crosses it.
        # The price itself is grindable money and needs no item.
        # Neither area item is held to begin with, since either one reaches the
        # mansion: the island's barrier directly, or the mainland and then the
        # audit's helicopter route across.
        self.collect_by_name(_MANSION_CHAIN)
        self.assertFalse(self.can_reach_location("Malibu Club Purchase"))
        self.collect_by_name(["Progressive Vercetti Protection"])
        self.assertFalse(self.can_reach_location("Malibu Club Purchase"))
        self.collect_by_name(["Starfish Island Access", "Mainland Access"])
        self.assertTrue(self.can_reach_location("Malibu Club Purchase"))

    def test_every_purchase_gates_on_a_way_to_both_islands(self) -> None:
        # Every business purchase gates on reaching the mainland as well as the
        # mansion, wherever the business stands, so the fill cannot strand a
        # crossing behind one: a business goes on sale when Shakedown passes, and
        # the chain that opens the mansion runs through Death Row on the mainland.
        # Either area item is a way to both islands, its own barrier directly and
        # the other island by helicopter, so this withholds both and then hands
        # over one. A purchase still says which island it is on through its
        # region, which is what gates the location itself.
        self.assertEqual(LOCATION_REGIONS["Kaufman Cabs Purchase"],
                         data.REGION_MAINLAND)
        self.assertEqual(LOCATION_REGIONS["Malibu Club Purchase"],
                         data.REGION_VICE_CITY)
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name(["Progressive Vercetti Protection"])
        for purchase in ("Malibu Club Purchase", "Kaufman Cabs Purchase"):
            self.assertFalse(self.can_reach_location(purchase), purchase)
        self.collect_by_name(["Mainland Access"])
        for purchase in ("Malibu Club Purchase", "Kaufman Cabs Purchase"):
            self.assertTrue(self.can_reach_location(purchase), purchase)

    def test_safehouse_purchase_is_free(self) -> None:
        # A safehouse is for sale from a new game, so a start-island safehouse
        # purchase is reachable with an empty inventory.
        self.assertTrue(self.can_reach_location("El Swanko Casa Purchase"))

    def test_venue_mission_needs_the_property_bought_and_owned(self) -> None:
        # No Escape? is the Malibu Club's first mission. The club must be
        # bought (it goes on sale only after Shakedown, so the mission needs
        # the Shakedown items) and owned (the building arrives as its
        # ownership item), besides its own progressive.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name(["Progressive Malibu Club", "Starfish Island Access",
                              "Mainland Access"])
        self.assertFalse(self.can_reach_location("No Escape?"))
        self.collect_by_name(["Progressive Vercetti Protection"])
        self.assertFalse(self.can_reach_location("No Escape?"))
        self.collect_by_name(["Malibu Club Ownership"])
        self.assertTrue(self.can_reach_location("No Escape?"))

    def _collect_sunshine_base(self) -> None:
        # Everything the Sunshine Autos lot needs except its own progressive:
        # the showroom bought (the Shakedown items plus Starfish Island Access,
        # since Shakedown gives from the mansion), owned, and on the mainland.
        self.collect_by_name([
            "Progressive Vercetti Protection", "Starfish Island Access",
            "Mainland Access", "Sunshine Autos Ownership",
        ])

    def test_sunshine_races_are_flat_behind_the_showroom(self) -> None:
        # The showroom menu wraps all six races freely from the first visit, so
        # they carry no progressive: buying and owning the lot opens every one
        # of them at once, and the entry fees are money.
        self.collect_by_name(_MANSION_CHAIN)
        for race in data.SUNSHINE_RACES:
            self.assertFalse(self.can_reach_location(race), race)
        self._collect_sunshine_base()
        for race in data.SUNSHINE_RACES:
            self.assertTrue(self.can_reach_location(race), race)

    def test_import_lists_are_a_progressive_ladder(self) -> None:
        # The four lists are the venue's strand, in the order vanilla already
        # chains them (each list's recognition thread starts the next), so list
        # n needs the first n unlocks. The races share the lot and need none.
        self.collect_by_name(_MANSION_CHAIN)
        lists = data.VENUE_STRANDS["Sunshine Autos"]
        self.assertEqual(len(lists), 4)
        progressives = self.get_items_by_name("Progressive Sunshine Autos")
        self.assertEqual(len(progressives), 4)
        self._collect_sunshine_base()
        for step, name in enumerate(lists):
            self.assertFalse(self.can_reach_location(name), name)
            self.collect(progressives[step])
            self.assertTrue(self.can_reach_location(name), name)
        for race in data.SUNSHINE_RACES:
            self.assertTrue(self.can_reach_location(race), race)

    def test_ownership_items_are_in_the_pool(self) -> None:
        item_names = {item.name for item in self.multiworld.itempool}
        for ownership in data.PROPERTY_OWNERSHIP_ITEMS:
            self.assertIn(ownership, item_names, ownership)

    def test_ownership_classification_splits_business_from_safehouse(self) -> None:
        # Business ownerships gate venue missions or the finale's asset
        # threshold, so logic may require them; safehouse ownerships gate only
        # a save point and garage, which no location needs.
        for ownership in data.BUSINESS_OWNERSHIP_ITEMS:
            self.assertEqual(
                ITEM_CLASSIFICATIONS[ownership], ItemClassification.progression, ownership,
            )
        for ownership in data.SAFEHOUSE_OWNERSHIP_ITEMS:
            self.assertEqual(
                ITEM_CLASSIFICATIONS[ownership], ItemClassification.useful, ownership,
            )

    def test_safehouse_purchase_needs_no_ownership(self) -> None:
        # Buying stays a pure money-for-check trade: the ownership item gates
        # what the safehouse provides, never the purchase itself.
        self.assertTrue(self.can_reach_location("El Swanko Casa Purchase"))


class TestFinaleAssetThreshold(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_properties": True}

    def _collect_finale_base(self) -> None:
        # The chain first: the finale sits behind the protection strand, which
        # sits behind Diaz, so a test that skipped it would find Cap the
        # Collector unreachable for that reason and prove nothing about assets.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name([
            "Progressive Vercetti Finale", "Progressive Vercetti Protection",
            "Mainland Access", "Starfish Island Access",
        ])

    def test_finale_needs_the_printworks_asset(self) -> None:
        # Cap the Collector keeps its vanilla prerequisite: Hit the Courier
        # passed is individually mandatory, so the Printworks items are too.
        self.collect_by_name(_MANSION_CHAIN)
        self._collect_finale_base()
        self.collect_by_name([
            "Malibu Club Ownership", "Progressive Malibu Club",
            "Film Studio Ownership", "Progressive Film Studio",
            "Kaufman Cabs Ownership", "Progressive Kaufman Cabs",
            "Cherry Popper Ownership", "Progressive Cherry Popper",
            "Boatyard Ownership", "Progressive Boatyard",
            "Sunshine Autos Ownership", "Pole Position Ownership",
        ])
        self.assertFalse(self.can_reach_location("Cap the Collector"))
        self.collect_by_name(["Printworks Ownership", "Progressive Printworks"])
        self.assertTrue(self.can_reach_location("Cap the Collector"))

    def test_finale_needs_enough_optional_assets(self) -> None:
        # Seven of the nine assets must be completable. Printworks and the
        # estate are mandatory, leaving five of the seven optional assets;
        # four are one short, and an ownership-only asset crosses the line.
        self.collect_by_name(_MANSION_CHAIN)
        self._collect_finale_base()
        self.collect_by_name(["Printworks Ownership", "Progressive Printworks"])
        self.assertFalse(self.can_reach_location("Cap the Collector"))
        self.collect_by_name([
            "Malibu Club Ownership", "Progressive Malibu Club",
            "Film Studio Ownership", "Progressive Film Studio",
            "Kaufman Cabs Ownership", "Progressive Kaufman Cabs",
            "Cherry Popper Ownership", "Progressive Cherry Popper",
        ])
        self.assertFalse(self.can_reach_location("Cap the Collector"))
        self.collect_by_name(["Pole Position Ownership"])
        self.assertTrue(self.can_reach_location("Cap the Collector"))
        # The last mission chains through Cap the Collector in game, so it
        # carries the same asset terms and is reachable with the same set.
        self.assertTrue(self.can_reach_location(data.FINAL_MISSION))

    def test_an_asset_needs_its_ownership_not_just_missions(self) -> None:
        # Progressives alone complete nothing: an asset counts only while its
        # property is owned, so ownership items cannot be swapped for extra
        # mission unlocks.
        self._collect_finale_base()
        self.collect_by_name([
            "Printworks Ownership", "Progressive Printworks",
            "Progressive Malibu Club", "Progressive Film Studio",
            "Progressive Kaufman Cabs", "Progressive Cherry Popper",
            "Progressive Boatyard",
        ])
        self.assertFalse(self.can_reach_location("Cap the Collector"))

    def test_optional_asset_table_matches_the_strands(self) -> None:
        # Each optional asset that completes through its venue strand needs
        # every progressive of that strand (the asset completes on the last
        # mission). Two are deliberately different: Pole Position has no
        # missions at all, so it is ownership-only, and Sunshine Autos completes
        # on the FIRST of its four import garage lists, so it takes one.
        for asset, progressive_count in data.FINALE_OPTIONAL_ASSETS.items():
            self.assertIn(data.ownership_item_name(asset), data.BUSINESS_OWNERSHIP_ITEMS)
            if asset == "Pole Position":
                self.assertEqual(progressive_count, 0, asset)
            elif asset == "Sunshine Autos":
                self.assertEqual(progressive_count, 1, asset)
                self.assertEqual(len(data.VENUE_STRANDS[asset]), 4, asset)
            else:
                self.assertEqual(progressive_count, len(data.VENUE_STRANDS[asset]), asset)
        self.assertNotIn("Printworks", data.FINALE_OPTIONAL_ASSETS)
        self.assertEqual(
            data.FINALE_OPTIONAL_ASSETS_REQUIRED, data.FINALE_ASSET_THRESHOLD - 2,
        )


class TestPropertiesTightestPool(WorldTestBase):
    # The tightest properties pool: the class brings 34 items (19 venue
    # progressives, 15 ownerships) against 40 locations, so it carries six spare
    # homes for another class's items. The inherited default tests prove it
    # fills and stays beatable through the finale's asset threshold.
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = dict(_TIGHTEST_OPTIONS, enable_properties=True)


class TestFinaleWithoutProperties(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_properties": False}

    def test_finale_keeps_the_sale_requirements_when_the_class_is_off(self) -> None:
        # With the properties class off the asset items leave the pool and
        # assets complete vanilla-style with grindable money, so no ownership
        # or venue items appear in the rule. But the FIN1 gate still reads the
        # vanilla flags, and Shakedown and Cop Land are given from the
        # mansion, so the finale must keep Starfish Island Access or the fill
        # could strand that item behind Cap the Collector, an in-game
        # deadlock.
        # The mansion is reachable from the mainland too, by the audit's
        # helicopter route, so neither area item is held to begin with.
        self.collect_by_name(_MANSION_CHAIN)
        self.collect_by_name([
            "Progressive Vercetti Finale", "Progressive Vercetti Protection",
        ])
        self.assertFalse(self.can_reach_location("Cap the Collector"))
        self.collect_by_name(["Starfish Island Access", "Mainland Access"])
        self.assertTrue(self.can_reach_location("Cap the Collector"))
        self.assertTrue(self.can_reach_location(data.FINAL_MISSION))


class TestDeferredClassIslands(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "enable_robbable_stores": True, "enable_side_events": True,
        "enable_stunt_jumps": True,
    }

    def test_mainland_members_need_mainland_access(self) -> None:
        # A mainland store (coordinate-derived), a mainland side event, and a stunt
        # jump (provisionally mainland) wait on Mainland Access; a start-island
        # store and chopper checkpoint do not. This closes the loop where the fill
        # could otherwise strand Mainland Access behind a mainland-only check.
        # A start-island store, an RC race and an activity, all free from the
        # start. A chopper checkpoint is not one of them: the audit puts each
        # behind the mission whose helicopter it flies.
        for start_name in [data.robbable_store_name(1), "RC Bandit Race",
                           "Cone Crazy"]:
            self.assertTrue(self.can_reach_location(start_name), start_name)
        mainland = [data.robbable_store_name(3), "Hotring", data.stunt_jump_name(1)]
        for name in mainland:
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name(["Mainland Access"])
        for name in mainland:
            self.assertTrue(self.can_reach_location(name), name)


class TestPropertiesToggle(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_properties": False}

    def test_venue_items_and_locations_absent(self) -> None:
        # Properties is the first optional class with progression items, so a
        # disabled class must drop both its locations and its venue progressive
        # items from the pool.
        item_names = {item.name for item in self.multiworld.itempool}
        item_names |= {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        self.assertNotIn("Progressive Malibu Club", item_names)
        for ownership in data.PROPERTY_OWNERSHIP_ITEMS:
            self.assertNotIn(ownership, item_names, ownership)
        location_names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertNotIn("No Escape?", location_names)
        self.assertNotIn("Malibu Club Purchase", location_names)

    def test_config_globals_carry_the_vanilla_collapse(self) -> None:
        # With the class off the static property gates must reduce to
        # purchase-only, so the client stamps the venue unlock globals maxed
        # and every ownership global to 1 through config_globals.
        config = self.world.fill_slot_data()["config_globals"]
        for venue, missions in data.VENUE_STRANDS.items():
            self.assertEqual(config[str(scm.unlock_global(venue))], len(missions), venue)
        for ownership in data.PROPERTY_OWNERSHIP_ITEMS:
            self.assertEqual(config[str(scm.ownership_global(ownership))], 1, ownership)


class TestPropertiesOnConfigGlobals(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_properties": True}

    def test_no_vanilla_collapse_while_the_class_is_on(self) -> None:
        # With the class on the ownership globals are item-driven, so the
        # config stamp must not touch them or the gates would open for free.
        config = self.world.fill_slot_data()["config_globals"]
        for ownership in data.PROPERTY_OWNERSHIP_ITEMS:
            self.assertNotIn(str(scm.ownership_global(ownership)), config, ownership)
        for venue in data.VENUE_STRANDS:
            self.assertNotIn(str(scm.unlock_global(venue)), config, venue)


class TestEmergencyRewardShuffle(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"shuffle_emergency_rewards": True}

    def test_reward_items_enter_the_pool_when_shuffled(self) -> None:
        item_names = {item.name for item in self.multiworld.itempool}
        item_names |= {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        for reward in data.EMERGENCY_REWARD_ITEMS:
            self.assertIn(reward, item_names)

    def test_taxi_reward_is_named_for_the_jump(self) -> None:
        # The vanilla reward makes taxis jump; the opcode's nitro wording does
        # not describe it, so the item name pins the player-facing effect.
        self.assertEqual(data.EMERGENCY_REWARD_BY_ACTIVITY["Taxi"], "Taxi Jump Ability")
        self.assertIn("Taxi Jump Ability", data.EMERGENCY_REWARD_ITEMS)


class TestEmergencyRewardsUnshuffled(WorldTestBase):
    game = "Grand Theft Auto Vice City"

    def test_reward_items_absent_when_not_shuffled(self) -> None:
        # Shuffle defaults off, so the five ability items grant vanilla and stay
        # out of the pool even with emergency vehicles enabled.
        item_names = {item.name for item in self.multiworld.itempool}
        item_names |= {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        for reward in data.EMERGENCY_REWARD_ITEMS:
            self.assertNotIn(reward, item_names)


class TestEmergencyRewardsWithoutTheVehiclesClass(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "shuffle_emergency_rewards": True, "enable_emergency_vehicles": False,
    }

    def test_reward_items_are_pooled_whatever_the_class_says(self) -> None:
        # The reward shuffle is independent of the check class. Whether the levels
        # are checks and who hands over the rewards are different questions, and
        # this option answers only the second: the chains still play, they just
        # stop paying out, and the payout comes from the multiworld.
        #
        # This used to assert the opposite, on the reasoning that there was
        # nothing to complete. There is: the emergency chains exist in the game
        # whether or not their levels are AP locations.
        item_names = {item.name for item in self.multiworld.itempool}
        item_names |= {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        for reward in data.EMERGENCY_REWARD_ITEMS:
            self.assertIn(reward, item_names)


class TestConfigFlagsShuffleWithoutVehicles(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "shuffle_emergency_rewards": True, "enable_emergency_vehicles": False,
    }

    def test_the_flag_follows_the_option_alone(self) -> None:
        # The flag does two things at once, suppress the vanilla grant and arm the
        # applier, so it must never be set without the items that replace what it
        # suppresses. That is the hazard the old coupling was guarding against,
        # and it is closed by construction now: the flag and the items are driven
        # by the same option, so they cannot disagree. Asserted together here
        # rather than separately, because it is the pairing that matters.
        config = self.world.fill_slot_data()["config_globals"]
        self.assertEqual(config[str(scm.EMERGENCY_SHUFFLED_GLOBAL)], 1)
        pooled = {item.name for item in self.multiworld.itempool}
        pooled |= {item.name for item in
                   self.multiworld.precollected_items[self.player]}
        for reward in data.EMERGENCY_REWARD_ITEMS:
            self.assertIn(reward, pooled, reward)
        self.assertEqual(config[str(scm.PACKAGES_SHUFFLED_GLOBAL)], 1)


class TestConfigFlagsShuffled(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"shuffle_emergency_rewards": True}

    def test_emergency_flag_on_when_shuffled_and_vehicles_on(self) -> None:
        config = self.world.fill_slot_data()["config_globals"]
        self.assertEqual(config[str(scm.EMERGENCY_SHUFFLED_GLOBAL)], 1)


class TestClassCashFlagsAllOn(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options, which turn on every class that has a cash flag. The
    # pickup class defaults OFF and has no cash flag of its own, so the four
    # flags below are still the whole set.

    def test_enabled_classes_stamp_their_cash_flags(self) -> None:
        # With a class enabled its one-time completion cash is suppressed in
        # the main.scm (the AP check is the reward), so the flag stamps one.
        config = self.world.fill_slot_data()["config_globals"]
        self.assertEqual(config[str(scm.SIDE_EVENTS_CASH_GLOBAL)], 1)
        self.assertEqual(config[str(scm.STUNT_JUMPS_CASH_GLOBAL)], 1)
        self.assertEqual(config[str(scm.RAMPAGES_CASH_GLOBAL)], 1)
        self.assertEqual(config[str(scm.PROPERTIES_CASH_GLOBAL)], 1)


class TestClassCashFlagsAllOff(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "enable_side_events": False, "enable_stunt_jumps": False,
        "enable_rampages": False, "enable_properties": False,
    }

    def test_disabled_classes_pay_vanilla(self) -> None:
        # With a class off its cash flag stamps zero, so every payout in the
        # main.scm falls through to the vanilla add: the toggle invariant.
        config = self.world.fill_slot_data()["config_globals"]
        self.assertEqual(config[str(scm.SIDE_EVENTS_CASH_GLOBAL)], 0)
        self.assertEqual(config[str(scm.STUNT_JUMPS_CASH_GLOBAL)], 0)
        self.assertEqual(config[str(scm.RAMPAGES_CASH_GLOBAL)], 0)
        self.assertEqual(config[str(scm.PROPERTIES_CASH_GLOBAL)], 0)


class TestRejections(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    auto_construct = False

    def _assert_rejected(self, options: dict, because: str) -> None:
        # `because` pins which guard fired, so a test cannot keep passing on a
        # different refusal once the item or location math moves.
        self.options = options
        with self.assertRaises(OptionError) as raised:
            self.world_setup()
        self.assertIn(because, str(raised.exception))

    def test_a_starting_draw_never_decides_whether_a_seed_generates(self) -> None:
        # The option docs promise that the draws only ever loosen: the guard
        # measures what is open with no item at all, so a config refused without
        # a draw is refused with it and one accepted without a draw is accepted
        # with it. Both halves need holding. The draw takes a content item out of
        # the pool, so without the opener being reserved first it could take the
        # very item a narrow seed is directed to place, and with heavy ability
        # locks the held packages are often the only class that opens the start.
        refused = dict(_TIGHTEST_OPTIONS, ability_locks=_ALL_ABILITY_LOCKS)
        self._assert_rejected(dict(refused, starting_ability_unlock=True),
                              "no held content class opens enough")
        accepted = {
            "content_locks": ["hidden_packages"],
            "ability_locks": ["vehicles", "weapon_equip", "wallet"],
        }
        for draws in ({}, {"starting_content_unlock": True,
                           "starting_ability_unlock": True}):
            with self.subTest(**draws):
                self.options = dict(accepted, **draws)
                self.world_setup()
                self._assert_opener_carries_the_start()
                self.assertNotEqual(self.world.starting_content_item,
                                    self.world.directed_opening_item)

    def test_the_hundred_percent_goal_generates_with_pickups_on(self) -> None:
        # This was refused while nothing reported a pickup, because the client
        # holds that goal until no location is missing. The watcher reports them
        # now, so the refusal went with its reason rather than outliving it.
        self.assertTrue(data.MOD_REPORTS_PICKUPS)
        self.options = {
            "enable_pickups": True, "goal": "hundred_percent",
            "enable_hidden_packages": True, "enable_rampages": True,
            "enable_stunt_jumps": True, "enable_emergency_vehicles": True,
            "enable_properties": True, "enable_robbable_stores": True,
            "enable_side_events": True}
        self.world_setup()
        self.assertEqual(self.world.options.goal.current_key, "hundred_percent")

    def test_any_goal_generates_with_pickups_on(self) -> None:
        # The class is meant to be playable, so a seed carrying it has to
        # generate rather than refuse.
        self.options = {"enable_pickups": True}
        self.world_setup()
        self.assertTrue(self.world.options.enable_pickups.value)

    def test_story_missions_plus_pickups_generates(self) -> None:
        # 110 slots is plenty of room, and while they were excluded from holding
        # progression they were not room at all, so this refused. They sit on
        # their verified island now and hold anything, so it generates: 44 story
        # checks plus 110 pickups, and the 53 on the start island are sphere-0
        # room in their own right.
        self.options = dict(_STORY_ONLY_OPTIONS, enable_pickups=True)
        self.world_setup()
        self.assertGreaterEqual(self.world._free_start_location_count(),
                                MINIMUM_SPHERE_ZERO)
        distribute_items_restrictive(self.multiworld)
        self.assertTrue(self.multiworld.can_beat_game())

    def test_story_missions_plus_pickups_survives_the_locks(self) -> None:
        # The same with every ability key selected, which is the narrowest shape
        # the option space allows and the one that used to refuse.
        self.options = dict(_STORY_ONLY_OPTIONS, enable_pickups=True,
                            ability_locks=_ALL_ABILITY_LOCKS)
        self.world_setup()
        distribute_items_restrictive(self.multiworld)
        self.assertTrue(self.multiworld.can_beat_game())

    def _generation_outcome(self, options: dict) -> str:
        """How this configuration ends: filled, or the refusal it gives."""
        self.options = options
        try:
            self.world_setup()
        except OptionError as error:
            # The message names the counts, so comparing it compares them.
            return f"refused: {error}"
        return "generated"

    def test_hundred_percent_rejects_with_a_class_off(self) -> None:
        # The 100 percent goal is a solvability contract: every stat
        # contributor must be a check, so generation must refuse the goal
        # unless every class the stat counts is enabled. The pickup class is not
        # one of them, which TestHundredPercentAllClasses holds.
        self._assert_rejected({"goal": "hundred_percent", "enable_side_events": False},
                              "100 percent goal requires every check class")

    def test_hidden_packages_goal_rejects_without_packages(self) -> None:
        self._assert_rejected({"goal": "hidden_packages", "enable_hidden_packages": False},
                              "hidden-packages goal needs the hidden")

    def test_story_only_rejects_on_item_math(self) -> None:
        # With every collectible class off, the story pool's progressive
        # unlocks and the two area items outnumber the 44 story checks, so a
        # solo seed has nowhere to put the surplus.
        self._assert_rejected(dict(_STORY_ONLY_OPTIONS), "45 progression and useful items")

    def test_story_only_rejects_with_extra_useful_items(self) -> None:
        # Each world modifier adds pool items without adding checks, so an
        # already over-full story-only pool only gets worse.
        for extra in ({"randomize_radio_stations": True}, {"shuffle_minimap": True},
                      {"ability_locks": _ALL_ABILITY_LOCKS}):
            with self.subTest(**extra):
                self._assert_rejected(dict(_STORY_ONLY_OPTIONS, **extra),
                                      "progression and useful items")

    def test_properties_absorbs_the_story_only_surplus(self) -> None:
        # Story-only is refused because its 45 progression and useful items
        # outnumber its 44 checks. The properties class takes that surplus: it
        # brings 34 items (19 venue progressives, 15 ownerships) against 40
        # locations, because the six Sunshine Autos races carry no item at all
        # and the four import garage lists share one progressive. The margin is
        # what makes the pair generate, so it is pinned here rather than left to
        # the absence of a rejection test.
        self.options = dict(_STORY_ONLY_OPTIONS, enable_properties=True)
        self.world_setup()
        checks = [location
                  for location in self.multiworld.get_locations(self.player)
                  if location.address is not None]
        self.assertEqual(len(checks), 84)
        self.assertEqual(len(self.multiworld.itempool), len(checks))

    def test_locks_can_narrow_the_start_to_a_refusal(self) -> None:
        # A lock puts its class's checks behind an item, so a seed whose only
        # collectible class is locked leaves the first mission alone reachable.
        # The fill would then chain strictly through that one check, which it
        # survives only by luck of the seed.
        for locks in (_ALL_ABILITY_LOCKS, ["weapon_equip"]):
            with self.subTest(ability_locks=locks):
                self._assert_rejected(dict(_TIGHTEST_OPTIONS, ability_locks=locks),
                                      "only 1 check is reachable")

    def test_content_locks_stay_wide_with_every_class_enabled(self) -> None:
        # Every content key with no ability key and no class disabled still
        # leaves a wide start, measured at 35. This does NOT generalise: turn
        # the other start-island classes off and a single locked class refuses
        # the seed with no ability key involved, which is the "content lock,
        # packages only" row in scripts/fuzz_fill.py. The claim holds for this
        # configuration only. The assertion pins the threshold rather than the
        # 35, so adding a class does not make the test brittle.
        self.options = {"content_locks": _ALL_CONTENT_LOCKS}
        self.world_setup()
        self.assertGreaterEqual(self.world._free_start_location_count(),
                                MINIMUM_SPHERE_ZERO)

    def test_lock_combinations_that_close_the_start_island_are_widened(self) -> None:
        # These are measured, not derived. The first row is every key of both
        # families; the three after it are far smaller, so closing the start
        # does not take every key. Nor does it take both families: content locks
        # plus disabled classes close the start with no ability key at all.
        # Hidden packages are the class the ability terms barely touch, seven of
        # the hundred, so holding them is what tips an ability-locked seed over.
        # The neighbouring
        # content=[hidden_packages, rampages, robbable_stores] with
        # ability=[vehicles] leaves a free count of 6 and needs no widening, so
        # the boundary is not simply "how many keys".
        #
        # Every row here holds a content class whose item clears the floor, so
        # every row generates on a directed opener rather than being refused.
        for content, ability in (
            (_ALL_CONTENT_LOCKS, _ALL_ABILITY_LOCKS),
            (["hidden_packages"], ["vehicles", "weapon_equip", "wallet"]),
            (["hidden_packages", "properties"], ["vehicles", "weapon_equip"]),
            (["hidden_packages", "rampages", "robbable_stores", "properties"],
             ["vehicles"]),
        ):
            with self.subTest(content_locks=content, ability_locks=ability):
                self.options = {"content_locks": content, "ability_locks": ability}
                self.world_setup()
                self.assertLess(self.world._free_start_location_count(),
                                MINIMUM_SPHERE_ZERO)
                self._assert_opener_carries_the_start()

    def _assert_opener_carries_the_start(self) -> None:
        # What a directed seed must hold: the opener is one of this seed's own
        # content items, the fill is told to place it early and locally, and it
        # opens enough of the start island on its own to clear the floor the
        # fuzzer pinned.
        directed = self.world.directed_opening_item
        self.assertIsNotNone(directed)
        self.assertIn(directed, self.world._content_items())
        self.assertEqual(
            self.multiworld.local_early_items[self.player][directed], 1)
        self.assertGreaterEqual(
            self.world._start_locations_opened_by(
                directed, self.world._location_rules(),
                CollectionState(self.multiworld)),
            MINIMUM_DIRECTED_SPHERE_ZERO)

    def test_the_directed_opener_is_never_an_ability_or_area_item(self) -> None:
        # Land Vehicles opens the start island wider than most content items do,
        # and a crossing opens the mainland whole, so both would carry a narrow
        # seed. Neither is eligible: they are milestones a seed is meant to wait
        # for, and the opening check must not hand one over.
        ineligible = set(data.AREA_ITEMS)
        for items in data.ABILITY_LOCK_ITEMS.values():
            ineligible.update(items)
        for options in (
            {"content_locks": _ALL_CONTENT_LOCKS, "ability_locks": _ALL_ABILITY_LOCKS},
            {"content_locks": _ALL_CONTENT_LOCKS, "ability_locks": ["vehicles"],
             "split_content_locks": "per_class"},
            dict(_STORY_ONLY_OPTIONS, enable_robbable_stores=True,
                 content_locks=["robbable_stores"]),
        ):
            with self.subTest(**options):
                self.options = options
                self.world_setup()
                self._assert_opener_carries_the_start()
                self.assertNotIn(self.world.directed_opening_item, ineligible)

    def test_the_opener_floor_refuses_a_key_that_opens_too_little(self) -> None:
        # The floor's own branch. The other refusal tests never reach it: they
        # select no content key, so there is no opener to weigh in the first
        # place. Here a key IS selected and its item still opens too little,
        # because an ability key ANDs a term onto the class the content key
        # holds. Directing such an item measures WORSE than leaving the fill to
        # choose, 31 to 33 of 60 seeds against 53, since it spends the only open
        # check on nothing, so these are refused rather than widened.
        #
        # The last row is the one that pins the constant rather than merely the
        # branch: its opener is worth exactly the two checks the 60-seed ladder
        # measured at 31 to 33. The rows above it are worth one.
        rows = (
            (dict(_TIGHTEST_OPTIONS, ability_locks=_ALL_ABILITY_LOCKS,
                  content_locks=["properties"]), 1),
            (dict(_TIGHTEST_OPTIONS, ability_locks=_ALL_ABILITY_LOCKS,
                  content_locks=["rampages"]), 1),
            (dict(_TIGHTEST_OPTIONS, ability_locks=_ALL_ABILITY_LOCKS,
                  content_locks=["robbable_stores"]), 1),
            (dict(_STORY_ONLY_OPTIONS, enable_rampages=True,
                  ability_locks=["weapon_equip"], content_locks=["rampages"]), 2),
        )
        for options, opened in rows:
            with self.subTest(content_locks=sorted(options["content_locks"]),
                              ability_locks=sorted(options["ability_locks"])):
                # Only as far as the opener, since create_items is what refuses.
                multiworld = setup_multiworld(GTAViceCityWorld, steps=(),
                                              options=options)
                call_all(multiworld, "generate_early")
                opener = multiworld.worlds[1]._best_start_opener()
                self.assertIsNotNone(opener)
                self.assertEqual(opener[1], opened)
                self.assertLess(opener[1], MINIMUM_DIRECTED_SPHERE_ZERO)
                self._assert_rejected(options, "no held content class opens enough")

    def test_the_opener_floor_admits_the_tightest_usable_opener(self) -> None:
        # The accept side of the floor, and the mirror of the refusal above.
        # Every other widened shape in the suite scores 14 or more, so without
        # this row raising the floor would turn hundreds of narrow shapes into
        # refusals with nothing failing. This is the tightest shape that
        # generates: its opener is worth exactly six checks. Six is as close as
        # the floor can be pinned from above, because no shape in the option
        # space scores three or five, and the shapes scoring four are refused on
        # item math before the start is ever measured.
        self.options = dict(_STORY_ONLY_OPTIONS, enable_properties=True,
                            content_locks=["properties"],
                            split_content_locks="off")
        self.world_setup()
        self.assertEqual(self.world._free_start_location_count(), 1)
        opener = self.world._best_start_opener()
        self.assertEqual(opener[0], "Property Purchases")
        self.assertEqual(opener[1], 6)
        self._assert_opener_carries_the_start()
        distribute_items_restrictive(self.multiworld)
        self.assertTrue(self.multiworld.can_beat_game())

    def test_a_narrow_seed_with_no_content_class_is_still_refused(self) -> None:
        # The opener is drawn from the content items the seed's own keys put in
        # the pool, so a start narrowed by ability keys alone has nothing to
        # direct and the refusal is what is left.
        self._assert_rejected(
            dict(_TIGHTEST_OPTIONS, ability_locks=_ALL_ABILITY_LOCKS),
            "no held content class opens enough",
        )

    def test_every_class_alone_leaves_a_wide_start(self) -> None:
        # The counterpart to the lock refusals: a class whose checks all sit on
        # the mainland would put nothing in the start region and narrow the seed
        # with no lock involved. Every class spreads across both islands, so one
        # class alone is enough to keep the start wide, and the measured floor is
        # the properties at 6. This is what closes that route, so it is asserted
        # per class rather than inferred from the district tables.
        for key, (option_name, _names) in data.optional_check_classes().items():
            with self.subTest(check_class=key):
                self.options = dict(_STORY_ONLY_OPTIONS, **{option_name: True})
                # world_setup raises on a narrow start, so reaching the assertion
                # is most of the answer; the assertion says which way it failed.
                # The patch is what lets the pickup class take its turn: without
                # it generation refuses the option outright, which the rejection
                # test covers instead.
                self.world_setup()
                self.assertGreaterEqual(self.world._free_start_location_count(),
                                        MINIMUM_SPHERE_ZERO)

    def test_a_narrow_seed_generates_in_a_multiworld(self) -> None:
        # Options a solo seed refuses reach the fill when another world is
        # present. can_beat_game sweeps from an empty state through the items
        # as placed, so it reads the placement; a state built from the item
        # pool would hold every progression item regardless of where it landed
        # and could not tell a good fill from a bad one.
        narrow = dict(_TIGHTEST_OPTIONS, ability_locks=_ALL_ABILITY_LOCKS)
        for seed in range(4):
            with self.subTest(seed=seed):
                multiworld = setup_multiworld([GTAViceCityWorld, GTAViceCityWorld],
                                              seed=seed, options=[narrow, narrow])
                self.assertLess(multiworld.worlds[1]._free_start_location_count(),
                                MINIMUM_SPHERE_ZERO)
                distribute_items_restrictive(multiworld)
                self.assertTrue(multiworld.can_beat_game())

    def test_a_narrow_slot_is_widened_inside_a_multiworld_too(self) -> None:
        # The refusal is solo only, because refusing would abort everyone's
        # generation over one slot's options. Widening is not: it costs the
        # other worlds nothing and it closes the one case the solo-only refusal
        # leaves open, a partner world too small to lend the fill room.
        narrow = {"content_locks": _ALL_CONTENT_LOCKS,
                  "ability_locks": _ALL_ABILITY_LOCKS,
                  "split_content_locks": "per_class"}
        multiworld = setup_multiworld([GTAViceCityWorld, GTAViceCityWorld],
                                      seed=0, options=[narrow, narrow])
        for player in (1, 2):
            directed = multiworld.worlds[player].directed_opening_item
            self.assertIsNotNone(directed)
            self.assertEqual(multiworld.local_early_items[player][directed], 1)
        distribute_items_restrictive(multiworld)
        self.assertTrue(multiworld.can_beat_game())

    def test_a_narrow_slot_regenerates_for_the_tracker(self) -> None:
        # The Universal Tracker replays a played seed's options on its own solo
        # multiworld, so a slot that generated inside a real multiworld meets
        # the solo guard on the way back. It must stand down there, or the
        # tracker cannot open a seed that generated perfectly well. The
        # passthrough goes through interpret_slot_data, the hook the tracker
        # itself calls, so this follows if that hook stops being the identity.
        narrow = dict(_TIGHTEST_OPTIONS, ability_locks=_ALL_ABILITY_LOCKS)
        played = setup_multiworld([GTAViceCityWorld, GTAViceCityWorld],
                                  seed=0, options=[narrow, narrow])
        slot_data = GTAViceCityWorld.interpret_slot_data(
            played.worlds[1].fill_slot_data())

        tracker = setup_multiworld(GTAViceCityWorld, steps=())
        tracker.re_gen_passthrough = {GTAViceCityWorld.game: slot_data}
        for step in gen_steps:
            call_all(tracker, step)
        # The regenerated world is the narrow one, so the test still covers the
        # guard's path if the options it is built from ever widen.
        self.assertLess(tracker.worlds[1]._free_start_location_count(),
                        MINIMUM_SPHERE_ZERO)
        self.assertEqual(
            {location.name for location in tracker.get_locations(1)},
            {location.name for location in played.get_locations(1)},
        )

    def test_a_replay_never_rolls_a_draw_the_seed_did_not_make(self) -> None:
        # The opener is kept out of the content draw, so a seed can draw NOTHING
        # with the option on and a key selected: the opener was the only content
        # item there was. slot_data then carries null, which reads the same as a
        # field it never carried, and rolling on either hands the tracker an item
        # the played seed left in its pool, showing every check of that class in
        # logic from the first frame. Only the replay flag separates the two, and
        # only this test holds it: put the draw back on "restored is not None"
        # and everything else still passes.
        options = {"content_locks": ["hidden_packages"],
                   "ability_locks": ["vehicles", "weapon_equip", "wallet"],
                   "starting_content_unlock": True}
        played = setup_multiworld(GTAViceCityWorld, gen_steps, seed=0,
                                 options=options)
        world = played.worlds[1]
        self.assertIsNone(world.starting_content_item)
        self.assertEqual(world.directed_opening_item, "Hidden Packages")
        self.assertIn("Hidden Packages",
                      [item.name for item in played.itempool])

        slot_data = GTAViceCityWorld.interpret_slot_data(world.fill_slot_data())
        self.assertIsNone(slot_data["starting_content_item"])
        tracker = setup_multiworld(GTAViceCityWorld, steps=())
        tracker.re_gen_passthrough = {GTAViceCityWorld.game: slot_data}
        for step in gen_steps:
            call_all(tracker, step)
        self.assertIsNone(tracker.worlds[1].starting_content_item)
        self.assertNotIn("Hidden Packages",
                         [item.name for item in tracker.precollected_items[1]])
        self.assertIn("Hidden Packages",
                      [item.name for item in tracker.itempool])

    def test_packages_keep_a_locked_seed_wide(self) -> None:
        # The counterpart to the refusals above: an ability term touches only
        # seven of the hundred hidden packages, so with them on every lock key
        # can be selected and the start stays wide enough.
        self.options = {"ability_locks": _ALL_ABILITY_LOCKS}
        self.world_setup()
        self.assertGreaterEqual(self.world._free_start_location_count(),
                                MINIMUM_SPHERE_ZERO)


class TestTables(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    run_default_tests = False

    def test_the_opening_mission_is_free_and_first(self) -> None:
        # add_markers.py holds every managed marker and every managed launcher
        # start until the game's opening mission is done, reading the vanilla flag
        # that mission sets. The gate is only right while the opening mission is
        # the sphere-0 giver's first: that is the one story mission with no unlock
        # of its own, and the one APMARK leaves on its vanilla marker, so it stays
        # playable while everything else waits. Reordering that strand would leave
        # the gate holding the map behind a mission the player cannot start.
        opening = data.STORY_GIVERS[data.SPHERE_ZERO_GIVER][0]
        self.assertEqual(opening, "An Old Friend")
        # And it carries no requirement under ANY option combination, so no item
        # can be placed behind it. Checked against every lock key selected rather
        # than this world's options, where no key is: a lock term added to the
        # opening mission would gate the whole map behind an item in any seed
        # selecting that key, since the map now waits on this mission.
        for properties in (True, False):
            for split in (False, True):
                built = rules.build_location_rules(
                    properties_enabled=properties,
                    ability_locks=frozenset(_ALL_ABILITY_LOCKS),
                    content_locks=frozenset(_ALL_CONTENT_LOCKS),
                    split_mainland_access=split,
                )
                self.assertNotIn(opening, built, (properties, split))

    def test_the_in_game_passed_gates_cannot_outrun_logic(self) -> None:
        # build_scm.py and add_markers.py gate the strands in this table on a
        # vanilla mission having PASSED, not on the items that open it: the
        # protection strand gives from the estate Rub Out hands over, and on the
        # unlock alone its markers stand in Diaz's mansion while he still owns
        # it. Logic never names a pass, it holds the progressive stand-in, so
        # such a gate is only safe while every mission of the strand inherits
        # the named mission, since inheriting it is what puts everything passing
        # it takes into the strand's own rule. Without that a seed could call a
        # protection mission reachable while Rub Out is not yet passable, and
        # the marker the mod holds back would never come.
        active_items = frozenset(
            item for items in data.ABILITY_LOCK_ITEMS.values() for item in items)
        for strand, prerequisite in data.IN_GAME_PASSED_PREREQUISITES.items():
            self.assertIn(strand, STRAND_MISSIONS)
            self.assertIn(prerequisite, STORY_MISSION_NAMES)
            giver = MISSION_GIVER[prerequisite]
            for mission in STRAND_MISSIONS[strand]:
                for split in (False, True):
                    for properties in (True, False):
                        with self.subTest(mission=mission, split=split,
                                          properties=properties):
                            self.assertIn(prerequisite, rules._inherited_missions(
                                mission, strand, properties))
                            carried = dict(rules._mission_requirements(
                                mission, strand, active_items,
                                data.CONTENT_SPLIT_OFF, split, properties))
                            for item, count in rules._mission_requirements(
                                    prerequisite, giver, active_items,
                                    data.CONTENT_SPLIT_OFF, split, properties):
                                self.assertGreaterEqual(
                                    carried.get(item, 0), count,
                                    f"{mission} misses {item} from {prerequisite}")
                            # And the one-of half, which a split seed puts the
                            # mainland in and which propagates the same way.
                            thresholds = rules._mission_thresholds(
                                mission, strand, active_items, split, properties)
                            for threshold in rules._mission_thresholds(
                                    prerequisite, giver, active_items, split,
                                    properties):
                                self.assertIn(threshold, thresholds,
                                              f"{mission} misses a route "
                                              f"from {prerequisite}")

    def test_ids_are_unique(self) -> None:
        self.assertEqual(len(ITEM_NAME_TO_ID), len(set(ITEM_NAME_TO_ID.values())))
        self.assertEqual(len(LOCATION_NAME_TO_ID), len(set(LOCATION_NAME_TO_ID.values())))

    def test_item_and_location_ids_do_not_overlap(self) -> None:
        self.assertTrue(
            set(ITEM_NAME_TO_ID.values()).isdisjoint(LOCATION_NAME_TO_ID.values())
        )

    def test_all_story_missions_are_locations(self) -> None:
        for mission in STORY_MISSION_NAMES:
            self.assertIn(mission, LOCATION_NAME_TO_ID)
        self.assertEqual(len(PACKAGE_NAMES), data.HIDDEN_PACKAGE_COUNT)

    def test_final_mission_exists(self) -> None:
        self.assertIn(data.FINAL_MISSION, LOCATION_NAME_TO_ID)

    def test_optional_class_counts(self) -> None:
        classes = data.optional_check_classes()
        self.assertEqual(len(classes["hidden_packages"][1]), 100)
        self.assertEqual(len(classes["rampages"][1]), 35)
        self.assertEqual(len(classes["stunt_jumps"][1]), 36)
        self.assertEqual(len(classes["emergency_vehicles"][1]), 56)
        self.assertEqual(len(classes["side_events"][1]), 14)
        self.assertEqual(len(classes["robbable_stores"][1]), 15)
        # 15 property purchases, the venue mission strands, and the six
        # Sunshine Autos races, which are venue activities rather than a strand.
        self.assertEqual(len(classes["properties"][1]), 40)
        # 110 the init mission places and six a mission leaves behind.
        self.assertEqual(len(classes["pickups"][1]), 116)
        # 32 the six shop threads sell and Phil's four in-shop pickups.
        self.assertEqual(len(classes["shops"][1]), 36)

    def test_venue_strands_are_not_story_missions(self) -> None:
        # The venue strands moved to the Properties class, so their missions
        # are no longer always-on story checks.
        for mission in ["No Escape?", "Recruitment Drive", "Cabmaggedon"]:
            self.assertNotIn(mission, STORY_MISSION_NAMES)

    def test_every_route_names_something_the_seed_has(self) -> None:
        # A route may name three kinds of thing: an ability its key locks, an area
        # item the seed's crossings setting actually puts in the pool, or the
        # event standing for a mission passed. Anything else is in no pool, and a
        # route naming it is either never satisfied or, once the emitter filters
        # it away, drops the whole several-routes requirement and fails loose.
        # Crouch is excluded with the useful items: a rule may not need one.
        #
        # Checked per crossings setting, because that is what decides which item
        # names the mainland. Baking Mainland Access into the sources was a real
        # bug, and a check against every area item would have blessed it.
        lockable = {item for items in data.ABILITY_LOCK_ITEMS.values()
                    for item in items if item not in data.ABILITY_USEFUL_ITEMS}
        events = {data.mission_passed_item_name(mission)
                  for mission in data.ROUTE_MISSIONS}
        for split in (False, True):
            area = (set(data.MAINLAND_CROSSING_ITEMS) if split
                    else {data.AREA_ITEM_BY_REGION[data.REGION_MAINLAND]})
            area.add(data.AREA_ITEM_BY_REGION[data.REGION_STARFISH])
            allowed = lockable | area | events
            for location, routes in data.LOCATION_ABILITY_ALTERNATIVES.items():
                sourced = (data.sourced_routes(routes, split)
                           if location in data.SOURCED_ROUTE_LOCATIONS else routes)
                with self.subTest(location=location, split=split):
                    self.assertGreaterEqual(len(sourced), 2)
                    for route in sourced:
                        self.assertTrue(route)
                        for item in route:
                            self.assertIn(item, allowed)

    def test_a_mission_a_check_waits_on_has_an_event(self) -> None:
        # A location naming a mission needs that mission to be one of the events,
        # or the term would name an item nothing places. Four groups are in the
        # table and nothing else: the chopper checkpoints, five stunt jumps, the
        # three pickups inside Diaz's mansion, and the thirteen shop items whose
        # stock a mission racks.
        self.assertEqual(sorted(data.LOCATION_MISSION_REQUIREMENTS), sorted([
            "Downtown Chopper Checkpoint", "Little Haiti Chopper Checkpoint",
            "Ocean Beach Chopper Checkpoint", "Vice Point Chopper Checkpoint",
            *(data.stunt_jump_name(index) for index in (12, 13, 14, 25, 26)),
            *(data.pickup_name(index)
              for index in (61, 62, 101, 110, 111, 112, 113, 114, 115)),
            *(data.shop_data.shop_item_name(item)
              for item in data.shop_data.SHOP_ITEMS
              if (item.thread, item.script_global)
              in data.shop_data.SHOP_STOCK_MISSIONS),
        ]))
        # Thirteen the script gates out of stock, plus Phil's four, which the
        # mission does not gate so much as create.
        self.assertEqual(len(data.shop_data.SHOP_STOCK_MISSIONS), 17)
        for location, missions in data.LOCATION_MISSION_REQUIREMENTS.items():
            with self.subTest(location=location):
                self.assertTrue(missions)
                for mission in missions:
                    self.assertIn(mission, data.ROUTE_MISSIONS)
        # The two G-spotlight groups: the ramps that mission builds and the one
        # checkpoint whose helicopter it leaves.
        for index in (12, 13, 14):
            self.assertEqual(
                data.LOCATION_MISSION_REQUIREMENTS[data.stunt_jump_name(index)],
                ["G-spotlight"])
        for index in (25, 26):
            self.assertEqual(
                data.LOCATION_MISSION_REQUIREMENTS[data.stunt_jump_name(index)],
                ["All Hands On Deck!"])
        self.assertEqual(
            data.LOCATION_MISSION_REQUIREMENTS["Downtown Chopper Checkpoint"],
            ["G-spotlight"])

    def test_each_shop_stock_gate_names_the_mission_that_racks_it(self) -> None:
        # Thirteen decompile facts, one per gated item, written out here rather
        # than read off the table the rules read: a wrong mission on any row is
        # a check gated behind the wrong half of the story and nothing else can
        # see it. Each shop thread guards the item's price with the vanilla flag
        # in the comment and prints the out-of-stock line while it is zero, so
        # the flag's setter thread is the gate.
        self.assertEqual(data.shop_data.SHOP_STOCK_MISSIONS, {
            ("AMMU1", 891): "Mall Shootout",       # $902, COL2
            ("AMMU1", 892): "Guardian Angels",     # $903, GENERL3
            ("AMMU1", 893): "Jury Fury",           # $867, LAWYER3
            ("AMMU2", 891): "The Chase",           # $868, BARON1
            ("AMMU2", 895): "Jury Fury",           # $867, LAWYER3
            ("AMMU3", 889): "Rub Out",             # $907, BARON5
            ("AMMU3", 890): "Rub Out",             # $906, BARON5
            ("AMMU3", 891): "Bar Brawl",           # $848, PROTEC2
            ("AMMU3", 892): "Rub Out",             # $855, BARON5
            ("AMMU3", 893): "Shakedown",           # $856, PROTEC1
            ("HARD1", 878): "Riot",                # $904, LAWYER4
            ("HARD1", 879): "Treacherous Swine",   # $905, GENERL1
            ("HARD2", 879): "The Chase",           # $874, BARON1
            # Not out-of-stock gating at all: PHIL2 creates these four stands,
            # so before Boomshine Saigon passes there is nothing on the wall.
            ("PHIL", 4345): "Boomshine Saigon",    # PHIL2
            ("PHIL", 4346): "Boomshine Saigon",    # PHIL2
            ("PHIL", 4347): "Boomshine Saigon",    # PHIL2
            ("PHIL", 4348): "Boomshine Saigon",    # PHIL2
        })
        # And each key names a row that exists, so a typo cannot silently gate
        # nothing. The Vice Point sniper is deliberately absent: its flag is the
        # one the crossing sets, so shop_item_region carries it instead.
        rows = {(item.thread, item.script_global)
                for item in data.shop_data.SHOP_ITEMS}
        self.assertLessEqual(set(data.shop_data.SHOP_STOCK_MISSIONS), rows)
        self.assertFalse(set(data.shop_data.SHOP_STOCK_MISSIONS)
                         & data.shop_data.CROSSING_STOCKED_ITEMS)

    def test_a_weapon_is_called_what_the_pc_game_calls_it(self) -> None:
        # The two names a rename got wrong by reaching for the common spelling.
        # american.gxt on the PC lists the weapons as ".357, Uz-1, Tec 9, M4,
        # Mac, MP, Kruger, Sniper rifle", so there is no Ruger and no MP5; those
        # are the other platform's names. Pinned by literal, since the game text
        # is not on hand here and a location name is what a player reads.
        self.assertEqual(data.rampage_name(6), "Rampage - Washington Beach - MP")
        self.assertEqual(data.rampage_name(15), "Rampage - Little Havana - Kruger")
        self.assertEqual(data.PICKUP_MODEL_NAMES[276], "Kruger")
        for name in list(data.RAMPAGE_NAMES) + list(data.PICKUP_MODEL_NAMES.values()):
            self.assertNotIn("Ruger", name)
            self.assertNotIn("MP5", name)

    def test_vehicle_rampages_are_the_unnamed_weapon_ones(self) -> None:
        # The ASI holds the weapon rampage icons by coordinate while this
        # table splits them by index, two hand-written mirrors of one
        # decompile fact. A rampage the RAMPAGE controller hands no weapon is
        # named for the vehicle it wants instead, so the two views must agree or
        # an icon gets sunk for a check whose rule says Land Vehicles.
        named_for_a_vehicle = {
            index for index in range(1, data.RAMPAGE_COUNT + 1)
            if data.rampage_name(index).endswith(" - Vehicle")
        }
        self.assertEqual(named_for_a_vehicle, set(data.VEHICLE_RAMPAGE_INDICES))
        # And each side of the split carries the ability its kill frenzy needs.
        for index in range(1, data.RAMPAGE_COUNT + 1):
            # The class rule, which five rampages then add to: three drive-bys
            # need the car as well as the weapon, one is only reachable from the
            # air, and one of the run-them-down pair takes a jump to its icon.
            expected = (data.LAND_VEHICLES_ITEM if index in data.VEHICLE_RAMPAGE_INDICES
                        else data.WEAPON_EQUIP_ITEM)
            self.assertEqual(
                data.LOCATION_ABILITY_REQUIREMENTS[data.rampage_name(index)],
                [expected, *(item for item in
                             data.RAMPAGE_ABILITY_EXTRAS.get(index, [])
                             if item != expected)],
                index,
            )

    def test_package_rewards_are_named_as_spawns(self) -> None:
        # Every non-cash package reward re-gates a respawning safehouse pickup
        # or vehicle, so its name says Spawn; a bare weapon name would read as
        # an inventory grant.
        for reward in data.PACKAGE_REWARD_ITEMS:
            if reward == data.PACKAGE_CASH_REWARD:
                continue
            self.assertTrue(reward.endswith(" Spawn"), reward)


class TestReservedGlobals(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    run_default_tests = False

    def test_all_reserved_globals_are_above_the_vanilla_maximum(self) -> None:
        # Vanilla packs globals up to $8583; the reserved block must clear it.
        self.assertGreater(scm.RESERVED_BASE, 8583)
        for global_index in scm.item_globals().values():
            self.assertGreaterEqual(global_index, scm.UNLOCK_BASE)
        self.assertGreater(scm.highest_reserved_global(), scm.COMPLETION_BASE)

    def test_the_finale_flag_tops_the_block_and_collides_with_nothing(self) -> None:
        # The finale raises this while the mansion siege runs so the ASI keeps the
        # ambient pickup layout off the pool for it. It tops the reserved block and
        # is what sizes it, so the marker scratch above starts one higher.
        #
        # NOT taken from the unused space lower down, which looks free and is not:
        # build_scm.py uses every one of those globals for scratch, and its package
        # watcher touches RESERVED_BASE + 6 a hundred and one times, once to
        # write the collected count and a hundred to compare against it.
        self.assertEqual(scm.FINALE_ACTIVE_GLOBAL, scm.FINALE_WARP_GLOBAL + 1)
        self.assertEqual(scm.highest_reserved_global(), scm.FINALE_ACTIVE_GLOBAL)

        # And it is not a global the WORLD uses for anything else. Gathered from
        # the accessors rather than from a written-down list, so a block growing
        # over it fails here.
        #
        # This set reaches no further than the world: the SCM's own scratch band
        # and the marker scratch above the block are build_scm.py's and
        # add_markers.py's, and what holds the flag clear of those is the equality
        # above plus scripts/check_scm_mirrors.py comparing all three mirrors.
        taken = set(range(scm.SEED_HASH_BASE,
                          scm.SEED_HASH_BASE + scm.SEED_HASH_GLOBAL_COUNT))
        taken.add(scm.APPLIED_INDEX_GLOBAL)
        taken |= {scm.unlock_global(key) for key in scm.UNLOCK_KEYS}
        taken |= set(scm.completion_watch().keys())
        taken |= {scm.reward_global(key) for key in scm.REWARD_KEYS}
        taken |= {scm.ownership_global(key) for key in scm.OWNERSHIP_KEYS}
        taken |= {scm.ability_lock_flag_global(name) for name in scm.ABILITY_KEYS}
        taken |= {scm.ability_unlock_global(name) for name in scm.ABILITY_KEYS}
        taken |= set(scm.unlocked_district_globals(
            frozenset(data.CONTENT_LOCK_ITEMS)))
        taken |= {scm.PACKAGES_SHUFFLED_GLOBAL, scm.EMERGENCY_SHUFFLED_GLOBAL,
                  scm.MINIMAP_SHUFFLED_GLOBAL, scm.MINIMAP_UNLOCK_GLOBAL,
                  scm.RADIO_RANDOMIZED_GLOBAL, scm.RADIO_REQUEST_GLOBAL,
                  scm.FINALE_WARP_GLOBAL}
        self.assertNotIn(scm.FINALE_ACTIVE_GLOBAL, taken)

        # It is not stamped by the config either. The applier leaves a stamped
        # global alone in both directions, and a flag the finale raises has to be
        # writable by the script.
        for keys in (frozenset(), frozenset(data.CONTENT_LOCK_ITEMS)):
            self.assertNotIn(scm.FINALE_ACTIVE_GLOBAL,
                             scm.unlocked_district_globals(keys))
        # And it is above every completion global, so the marker scratch the mod
        # sizes from the top of the block cannot reach down onto it.
        self.assertGreater(scm.FINALE_ACTIVE_GLOBAL,
                           max(scm.completion_watch().keys()))

    def test_no_reserved_global_collisions(self) -> None:
        seed_hash = set(range(scm.SEED_HASH_BASE, scm.SEED_HASH_BASE + scm.SEED_HASH_GLOBAL_COUNT))
        unlocks = {scm.unlock_global(key) for key in scm.UNLOCK_KEYS}
        completions = set(scm.completion_watch().keys())
        self.assertEqual(len(unlocks), len(scm.UNLOCK_KEYS))
        self.assertEqual(len(completions), len(LOCATION_NAME_TO_ID))
        rewards = {scm.reward_global(key) for key in scm.REWARD_KEYS}
        config = {scm.PACKAGES_SHUFFLED_GLOBAL, scm.EMERGENCY_SHUFFLED_GLOBAL,
                  scm.MINIMAP_SHUFFLED_GLOBAL}
        ownership = {scm.ownership_global(key) for key in scm.OWNERSHIP_KEYS}
        minimap = {scm.MINIMAP_UNLOCK_GLOBAL}
        finale = {scm.FINALE_WARP_GLOBAL}
        ability = (
            {scm.ability_lock_flag_global(name) for name in scm.ABILITY_KEYS}
            | {scm.ability_unlock_global(name) for name in scm.ABILITY_KEYS}
        )
        self.assertEqual(len(rewards), len(scm.REWARD_KEYS))
        self.assertEqual(len(ownership), len(scm.OWNERSHIP_KEYS))
        self.assertEqual(len(ability), 2 * len(scm.ABILITY_KEYS))
        self.assertTrue(seed_hash.isdisjoint(unlocks))
        self.assertTrue(seed_hash.isdisjoint(completions))
        self.assertTrue(unlocks.isdisjoint(completions))
        # The reward, config-flag, ownership, minimap, and ability blocks must
        # not collide with anything else, and must stay within the declared
        # reserved block the foundation sizes.
        self.assertTrue(rewards.isdisjoint(seed_hash | unlocks | completions | config))
        self.assertTrue(config.isdisjoint(seed_hash | unlocks | completions | rewards))
        self.assertTrue(
            ownership.isdisjoint(seed_hash | unlocks | completions | rewards | config)
        )
        self.assertTrue(minimap.isdisjoint(
            seed_hash | unlocks | completions | rewards | config | ownership
        ))
        self.assertTrue(ability.isdisjoint(
            seed_hash | unlocks | completions | rewards | config | ownership | minimap
        ))
        self.assertTrue(finale.isdisjoint(
            seed_hash | unlocks | completions | rewards | config | ownership
            | minimap | ability
        ))
        for global_index in rewards | config | ownership | minimap | ability | finale:
            self.assertLessEqual(global_index, scm.highest_reserved_global())
        self.assertNotIn(scm.APPLIED_INDEX_GLOBAL, unlocks | completions | rewards | config)

    def test_lock_globals_match_the_hand_written_mirrors(self) -> None:
        # The ASI hard-codes the ability bases (scm_ability_locks.hpp) and the
        # SCM build scripts hard-code both blocks, the top, and the marker
        # scratch that follows it, while this module derives them. Inserting a
        # reserved global earlier would shift the Python side alone and
        # silently break every lock, so the contract is pinned here: update
        # every place together.
        # The bribe help flag is deliberately a VANILLA index: the mod stamps a
        # flag the script owns, so it must stay clear of the reserved block.
        self.assertLess(data.BRIBE_HELP_SHOWN_FLAG, scm.RESERVED_BASE)
        # build_scm.py mirrors this block as UNLOCK_FIRST, UNLOCK_LAST, the
        # window its play-order guard groups the mission table by. A strand
        # whose unlock fell outside it would leave that strand unchecked.
        self.assertEqual(scm.UNLOCK_BASE, 9010)
        strand_unlocks = [scm.unlock_global(strand) for strand in data.progressive_strands()]
        self.assertGreaterEqual(min(strand_unlocks), 9010)
        self.assertLessEqual(max(strand_unlocks), 9029)
        # build_scm.py's area watcher hard-codes these five: the mainland flip
        # reads Mainland Access OR the crossing whose barrier each branch opens,
        # which is how one static script serves both split_mainland_access
        # settings. An area item inserted earlier would repoint every branch at
        # another crossing, so they are pinned by literal here.
        self.assertEqual(scm.unlock_global("Mainland Access"), 9030)
        self.assertEqual(scm.unlock_global("Starfish Island Access"), 9031)
        self.assertEqual(scm.unlock_global("Prawn Island Bridge"), 9032)
        self.assertEqual(scm.unlock_global("Leaf Links Bridge"), 9033)
        self.assertEqual(scm.unlock_global("Ocean Beach Bridge"), 9034)
        self.assertEqual(scm.unlock_global("Starfish Island Causeway"), 9035)

    def test_the_mainland_alternatives_are_what_a_gate_must_accept(self) -> None:
        # build_scm.py and add_markers.py hold these five as MAINLAND_UNLOCKS, the
        # globals a mainland gate expands to with if-or, and build_scm.py asserts
        # at build time that no gate names one of them directly. That matters
        # because Mainland Access and the crossings are alternatives: a gate
        # naming one alone holds forever under the setting that never writes it,
        # which is how the finale's launcher gate came to be unsatisfiable with
        # the split on. Pinned by literal, so adding a crossing fails here.
        alternatives = ["Mainland Access", *data.MAINLAND_CROSSING_ITEMS]
        self.assertEqual([scm.unlock_global(name) for name in alternatives],
                         [9030, 9032, 9033, 9034, 9035])
        # And under either setting, every BARRIER into the mainland is one of
        # them. The audit's helicopter and boat routes are not barriers and no
        # gate implements them: they are things a player does in a world the gate
        # has already opened or not, so routes_allowed is off here.
        for split in (False, True):
            groups = data.region_access_groups(data.REGION_MAINLAND, split,
                                               routes_allowed=False)
            self.assertTrue(groups, split)
            for group in groups:
                self.assertIn(group[0], alternatives, group)
        # The ASI hard-codes the packages-shuffled index too
        # (scm_game_state.cpp): it gates taking back the package cash the
        # executable pays, which no script gate can reach.
        self.assertEqual(scm.PACKAGES_SHUFFLED_GLOBAL, 9543)
        # The shops flag, which build_scm.py mirrors by literal as SHOPS_ENABLED
        # and every piece of the shop withholding reads before it changes the
        # world. It sits directly below the ability locks, so a shift moves both.
        self.assertEqual(scm.SHOPS_ENABLED_GLOBAL, 9586)
        self.assertEqual(scm.ABILITY_LOCK_FLAG_BASE, 9587)
        self.assertEqual(scm.ABILITY_UNLOCK_BASE, 9595)
        self.assertEqual(scm.CONTENT_LOCK_FLAG_BASE, 9603)
        self.assertEqual(scm.CONTENT_UNLOCK_BASE, 9608)
        # The district content unlocks, the block every content gate and every
        # content hold actually reads. build_scm.py mirrors the base and the
        # class-major stride by literal, so a shift here has to move with it.
        self.assertEqual(scm.DISTRICT_UNLOCK_BASE, 9613)
        self.assertEqual(scm.DISTRICT_UNLOCK_COUNT, 55)
        # The finale warp flag, hard-coded in the ASI (scm_game_state.cpp) and in
        # build_scm.py, which reads it in the APFIN watcher and in the mission
        # branch that jumps to the ending cutscene. It is also the foundation's
        # sizing line, which add_markers.py anchors on, so a shift here moves
        # four files at once.
        self.assertEqual(scm.FINALE_WARP_GLOBAL, 9668)
        self.assertEqual(scm.FINALE_ACTIVE_GLOBAL, 9669)
        self.assertEqual(scm.highest_reserved_global(), 9669)
        self.assertEqual(scm.ABILITY_KEYS, data.ABILITY_ITEMS)
        self.assertEqual(scm.CONTENT_KEYS, data.CONTENT_ITEMS)

    def test_story_completion_globals_match_the_hand_written_mirror(self) -> None:
        # build_scm.py and add_markers.py pair each story launcher with its gate
        # count and completion global by literal. The Avery strand is the one
        # whose thread names do not follow its play order (SERG1, SERG3, SERG2),
        # so a reordered strand there repoints a launcher's completion write at
        # another mission's check. Pinned by literal, so that shift fails here:
        # update the script tables in the same change.
        self.assertEqual(scm.completion_global("An Old Friend"), 9036)
        self.assertEqual(scm.completion_global("Four Iron"), 9052)
        self.assertEqual(scm.completion_global("Demolition Man"), 9053)
        self.assertEqual(scm.completion_global("Two Bit Hit"), 9054)

    def test_side_event_completion_globals_match_the_hand_written_mirrors(self) -> None:
        # build_scm.py hard-codes these in two tables: SIDE_EVENTS (win flag ->
        # completion global, for the APACT watcher) and SIDE_EVENT_CASH_SITES
        # (the payout lines to gate on the same global). A location added or
        # reordered anywhere earlier in the table shifts every completion global
        # here, which would silently point each event's payout guard at another
        # event. Pinned by literal, so that shift fails here instead: update the
        # script tables in the same change.
        expected = {
            "Hotring": 9307, "Bloodring": 9308, "Dirtring": 9309,
            "Downtown Chopper Checkpoint": 9310,
            "Ocean Beach Chopper Checkpoint": 9311,
            "Vice Point Chopper Checkpoint": 9312,
            "Little Haiti Chopper Checkpoint": 9313,
            "RC Bandit Race": 9314, "RC Baron Race": 9315,
            "RC Raider Pickup": 9316,
            "Trial by Dirt": 9317, "Test Track": 9318,
            "PCJ Playground": 9319, "Cone Crazy": 9320,
        }
        self.assertEqual(sorted(expected), sorted(data.SIDE_EVENTS))
        for name, global_index in expected.items():
            self.assertEqual(scm.completion_global(name), global_index, name)
        # Every payout guard also reads the class-cash flag, so that a seed with
        # the class off pays vanilla; the same shift argument applies to it.
        self.assertEqual(scm.SIDE_EVENTS_CASH_GLOBAL, 9582)

    def test_property_ownership_globals_match_the_hand_written_mirrors(self) -> None:
        # Each of these gates what its property gives: a safehouse's save
        # pickup, garage, save-house radar icon and "you can save here" text, or
        # a business's save pickup. build_scm.py writes down only the base of the
        # block and derives every gate from where the property's buy cutscene
        # sits in its purchase table, so it cannot pair a property with another
        # property's item; the base itself is what this pins. A location or an
        # area item added anywhere earlier shifts the whole block, and the script
        # would then gate all fifteen properties on the wrong items. Pinned by
        # literal, so that shift fails here rather than in game, and the fix is
        # to move build_scm.py's OWNERSHIP_BASE with it.
        businesses = {
            "Printworks": 9565,
            "Sunshine Autos": 9566,
            "Film Studio": 9567,
            "Cherry Popper": 9568,
            "Kaufman Cabs": 9569,
            "Malibu Club": 9570,
            "Boatyard": 9571,
            "Pole Position": 9572,
        }
        safehouses = {
            "El Swanko Casa": 9573,
            "Links View Apartment": 9574,
            "Hyman Condo": 9575,
            "Ocean Heights Apartment": 9576,
            "1102 Washington Street": 9577,
            "3321 Vice Point": 9578,
            "Skumole Shack": 9579,
        }
        for properties, items in ((businesses, data.BUSINESS_OWNERSHIP_ITEMS),
                                  (safehouses, data.SAFEHOUSE_OWNERSHIP_ITEMS)):
            self.assertEqual(
                sorted(data.ownership_item_name(name) for name in properties),
                sorted(items),
            )
            for name, global_index in properties.items():
                self.assertEqual(
                    scm.ownership_global(data.ownership_item_name(name)),
                    global_index, name,
                )

    def test_every_holdable_pickup_is_placed_unambiguously(self) -> None:
        # The ASI puts a pool entry in a district by matching its position
        # within one unit, and its fallback for an unmatched entry is to hold it
        # while any district of its class is held. That is the safe direction but
        # it disagrees with logic, which gates that location on one district's
        # item alone, so the fallback must never be reached: every holdable
        # pickup needs a row, and no two rows of one class may sit close enough
        # to match the same entry.
        entries = scm.content_districts()
        self.assertEqual(len(entries), data.HIDDEN_PACKAGE_COUNT
                         + data.RAMPAGE_COUNT + len(data.PROPERTY_PURCHASES))
        by_class: dict[int, list[tuple[float, float]]] = {}
        for entry in entries:
            by_class.setdefault(entry["class"], []).append((entry["x"], entry["y"]))
        for class_index, points in by_class.items():
            with self.subTest(content=scm.CONTENT_KEYS[class_index]):
                closest = min(
                    ((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2) ** 0.5
                    for index, left in enumerate(points)
                    for right in points[index + 1:]
                )
                self.assertGreater(closest, 1.0)

    def test_the_district_stamp_is_the_whole_toggle_invariant(self) -> None:
        # Every district unlock is released by an item or by this stamp, and
        # nothing else: each script gate is a bare "$district >= 1" and the ASI
        # holds a pickup on the same read, so a global neither covered nor
        # stamped reads held forever. With no key selected that means the whole
        # block has to be stamped, which is the toggle invariant itself; the
        # lock flags no longer decide anything.
        block = {scm.DISTRICT_UNLOCK_BASE + offset
                 for offset in range(scm.DISTRICT_UNLOCK_COUNT)}
        self.assertEqual(set(scm.unlocked_district_globals(frozenset())), block)
        for key in data.CONTENT_LOCK_ITEMS:
            with self.subTest(key=key):
                selected = frozenset({key})
                stamped = set(scm.unlocked_district_globals(selected))
                covered = {
                    global_index
                    for item_name in data.content_items(selected,
                                                        data.CONTENT_SPLIT_PER_CLASS)
                    for global_index in scm.content_district_globals()[
                        ITEM_NAME_TO_ID[item_name]]
                }
                # Exactly one of the two reaches every global: an item covers it
                # or the stamp does, never neither and never both.
                self.assertEqual(stamped | covered, block, key)
                self.assertEqual(stamped & covered, set(), key)

    def test_every_district_global_is_reachable_at_every_granularity(self) -> None:
        # The same accounting for whole classes and for district-wide items. A
        # class-district pair holding no content is covered by the stamp in every
        # mode, since no item names it: 13 of the 55, which the ASI would
        # otherwise read as a class held forever on the status page.
        block = {scm.DISTRICT_UNLOCK_BASE + offset
                 for offset in range(scm.DISTRICT_UNLOCK_COUNT)}
        every = frozenset(data.CONTENT_LOCK_ITEMS)
        stamped = set(scm.unlocked_district_globals(every))
        self.assertEqual(len(stamped), 13)
        for split in (data.CONTENT_SPLIT_OFF, data.CONTENT_SPLIT_PER_DISTRICT,
                      data.CONTENT_SPLIT_PER_CLASS):
            with self.subTest(split=split):
                covered = {
                    global_index
                    for item_name in data.content_items(every, split)
                    for global_index in scm.content_district_globals()[
                        ITEM_NAME_TO_ID[item_name]]
                }
                self.assertEqual(stamped | covered, block, split)

    def test_the_stamp_tells_absent_and_released_apart(self) -> None:
        # Both stamped values pass every gate, which all ask ">= 1", so the game
        # plays the same either way. The status page is what needs them apart: a
        # district holding none of a class is not a district where that class
        # became available, and reading it as released told the player there were
        # rampages waiting in Leaf Links.
        absent_pairs = {
            scm.district_unlock_global(content_item, district)
            for content_item in scm.CONTENT_KEYS
            for district in scm.DISTRICT_KEYS
            if district not in data.CONTENT_CLASS_DISTRICTS[content_item]
        }
        self.assertEqual(len(absent_pairs), 13)
        one_key = frozenset({sorted(data.CONTENT_LOCK_ITEMS)[0]})
        for selected in (frozenset(), frozenset(data.CONTENT_LOCK_ITEMS), one_key):
            with self.subTest(selected=sorted(selected)):
                stamped = scm.unlocked_district_globals(selected)
                for global_index, value in stamped.items():
                    self.assertGreaterEqual(value, 1, global_index)
                    self.assertEqual(
                        value,
                        (scm.DISTRICT_ABSENT if global_index in absent_pairs
                         else scm.DISTRICT_RELEASED),
                        global_index)
                # Absence is a fact about the city, so it is stamped whatever the
                # seed selected. Released depends on the selection.
                self.assertTrue(absent_pairs.issubset(stamped))

    def test_no_district_global_is_stamped_the_held_value(self) -> None:
        # Zero is held, and the stamp exists to release. Stamping one would hold
        # content no item can ever release, so the class would sit part-held on
        # the page forever and a pickup there would never come back.
        for selected in (frozenset(), frozenset(data.CONTENT_LOCK_ITEMS)):
            with self.subTest(selected=sorted(selected)):
                values = set(scm.unlocked_district_globals(selected).values())
                self.assertNotIn(0, values)
                self.assertLessEqual(values, {scm.DISTRICT_RELEASED,
                                              scm.DISTRICT_ABSENT})

    def test_package_districts_stay_where_the_audit_put_them(self) -> None:
        # A package's district decides which item releases it and which district
        # global the ASI joins its pickup to, so a drift here moves a check to
        # another part of town. The jump and store tables are pinned by literal
        # because build_scm.py transcribes them; these are pinned by count plus
        # the boundary cases, which is what actually moves: package 4 sits nine
        # units from rampage 25 and the audit puts both in Viceport, and packages
        # 41 and 42 are the pair inside the Film Studio walls on Prawn Island.
        counts = collections.Counter(district_data.PACKAGE_DISTRICTS)
        self.assertEqual(dict(counts), {
            "Ocean Beach": 7,
            "Washington Beach": 11,
            "Vice Point": 21,
            "Starfish Island": 5,
            "Prawn Island": 5,
            "Leaf Links": 5,
            "Downtown": 8,
            "Little Haiti": 8,
            "Little Havana": 7,
            "Viceport": 9,
            "Escobar International": 14,
        })
        self.assertEqual(district_data.PACKAGE_DISTRICTS[3], "Viceport")
        self.assertEqual(district_data.PACKAGE_DISTRICTS[40], "Prawn Island")
        self.assertEqual(district_data.PACKAGE_DISTRICTS[41], "Prawn Island")

    def test_the_junk_yard_holds_nothing_a_content_key_covers(self) -> None:
        # It is a district because a pickup name says so, and pickups are no
        # content class, so it holds nothing lockable. That is what keeps it out
        # of the district unlock grid, and out of the item pool at every
        # granularity: a district item covering nothing would be an item the
        # player receives for no reason and a global no gate reads.
        self.assertIn("Junk Yard", district_data.DISTRICTS)
        self.assertIn("Junk Yard", data.MAINLAND_DISTRICTS)
        for table in data.CONTENT_DISTRICT_TABLES.values():
            self.assertNotIn("Junk Yard", table)
        self.assertNotIn("Junk Yard", data.CONTENT_DISTRICTS)
        self.assertNotIn("Junk Yard", scm.DISTRICT_KEYS)
        self.assertNotIn(data.district_content_item_name("Junk Yard"),
                         data.all_district_content_items())
        # Two ambient slots are what it does hold, and both are on the mainland
        # like the district itself.
        slots = [index for index, district
                 in enumerate(district_data.PICKUP_DISTRICTS)
                 if district == "Junk Yard"]
        self.assertEqual(len(slots), 2)
        for index in slots:
            self.assertEqual(data.pickup_region(index), data.REGION_MAINLAND)

    def test_every_district_is_on_a_named_island(self) -> None:
        # Which island a district is on is what gates every collectible in it,
        # and it is derived rather than stored, so an unclassified district would
        # read as the start island and let the fill strand a crossing item behind
        # a mainland check. The three sets partition the districts, and an
        # unknown one raises rather than defaulting.
        islands = (data.MAINLAND_DISTRICTS, data.STARFISH_DISTRICTS,
                   data.START_ISLAND_DISTRICTS)
        self.assertEqual(set().union(*islands), set(district_data.DISTRICTS))
        self.assertEqual(sum(len(island) for island in islands),
                         len(district_data.DISTRICTS))
        for district in district_data.DISTRICTS:
            with self.subTest(district=district):
                self.assertIn(data.district_region(district),
                              (data.REGION_MAINLAND, data.REGION_STARFISH,
                               data.REGION_VICE_CITY))
        with self.assertRaises(ValueError):
            data.district_region("Vice Beach")

    def test_a_location_name_names_the_district_that_releases_it(self) -> None:
        # Every content location reads "<class> - <district> - <where>", and the
        # district in that name has to be the one the district table puts it in,
        # because with the locks split by district the item a player receives is
        # named for that district too. A name disagreeing with the table would
        # send them to the wrong side of town holding the right item, which no
        # other check catches: the two came from one audit but are stored apart,
        # names by class table and districts by index.
        for accessor, count in ((data.hidden_package_name, data.HIDDEN_PACKAGE_COUNT),
                                (data.rampage_name, data.RAMPAGE_COUNT),
                                (data.stunt_jump_name, data.STUNT_JUMP_COUNT),
                                (data.robbable_store_name, data.ROBBABLE_STORE_COUNT)):
            for index in range(1, count + 1):
                name = accessor(index)
                with self.subTest(location=name):
                    parts = name.split(" - ")
                    self.assertEqual(len(parts), 3, name)
                    # A name may say a landmark inside its district where that is
                    # the better direction to give a player; the fold table is
                    # the only licence for it, so an ordinary mismatch still
                    # fails here.
                    named = district_data.NAME_DISTRICT_FOLDS.get(parts[1], parts[1])
                    self.assertEqual(named, data.location_district(name), name)
        # The pickups are the same fact stored the same way apart, a name table
        # beside an index-keyed district table, and no content key covers them so
        # location_district answers None: their district table is what to compare
        # against, and what it decides is the island each slot gates on.
        for index, name in enumerate(data.PICKUP_NAMES):
            with self.subTest(location=name):
                parts = name.split(" - ")
                self.assertEqual(parts[0], "Pickup", name)
                self.assertEqual(parts[1], district_data.PICKUP_DISTRICTS[index],
                                 name)

    def test_no_two_locations_share_a_name(self) -> None:
        # The rename replaced 186 numbered names with sentences, and the id table
        # silently collapses a duplicate: the second one takes the first one's id
        # and a check goes missing. Comparing the dict against itself would say
        # nothing, since it is built from this very list, so the raw list is what
        # is counted, and it covers the story missions too.
        duplicates = sorted(
            {name for name in ORDERED_LOCATION_NAMES
             if ORDERED_LOCATION_NAMES.count(name) > 1}
        )
        self.assertEqual(duplicates, [])
        self.assertEqual(len(ORDERED_LOCATION_NAMES), len(LOCATION_NAME_TO_ID))

    def test_district_tables_match_the_hand_written_mirrors(self) -> None:
        # build_scm.py transcribes three tables out of district_data.py, because
        # it cannot import the world: the district order, which fixes every
        # district unlock global, and the district of each stunt jump and each
        # store, which decides the global each of the 53 per-site gates reads. A
        # district reordered or a jump remapped would gate the wrong part of
        # town, silently and only in game, so both copies are pinned here: when
        # this fails, the generated data moved and build_scm.py must move with
        # it.
        #
        # The mirrored list is scm.DISTRICT_KEYS, the districts that hold
        # something a content key covers. The Junk Yard is on the map and in
        # district_data.DISTRICTS but holds only ambient pickups, so it has no
        # column in the grid and is not here.
        districts = [
            "Ocean Beach", "Washington Beach",
            "Vice Point", "Starfish Island",
            "Prawn Island", "Leaf Links",
            "Downtown", "Little Haiti",
            "Little Havana", "Viceport",
            "Escobar International",
        ]
        self.assertEqual(scm.DISTRICT_KEYS, districts)
        self.assertEqual(district_data.DISTRICTS,
                         [*districts[:8], "Junk Yard", *districts[8:]])
        jumps = [
            "Escobar International", "Escobar International", "Escobar International",
            "Escobar International", "Escobar International", "Escobar International",
            "Escobar International", "Escobar International", "Prawn Island",
            "Vice Point", "Downtown", "Downtown",
            "Downtown", "Downtown", "Little Haiti",
            "Little Haiti", "Little Haiti", "Little Havana",
            "Ocean Beach", "Ocean Beach", "Washington Beach",
            "Ocean Beach", "Ocean Beach", "Ocean Beach",
            "Ocean Beach", "Ocean Beach", "Ocean Beach",
            "Ocean Beach", "Vice Point", "Washington Beach",
            "Washington Beach", "Washington Beach", "Washington Beach",
            "Washington Beach", "Washington Beach", "Starfish Island",
        ]
        self.assertEqual(district_data.STUNT_JUMP_DISTRICTS, jumps)
        stores = [
            "Washington Beach", "Vice Point", "Little Havana",
            "Little Havana", "Downtown", "Downtown",
            "Little Haiti", "Vice Point", "Vice Point",
            "Vice Point", "Vice Point", "Vice Point",
            "Vice Point", "Little Havana", "Little Havana",
        ]
        self.assertEqual(district_data.STORE_DISTRICTS, stores)
        # The block those tables index into. build_scm.py mirrors the base and
        # derives the stride from the class count, so both are pinned.
        self.assertEqual(scm.DISTRICT_UNLOCK_BASE, 9613)
        self.assertEqual(len(scm.DISTRICT_KEYS), len(districts))
        self.assertEqual(scm.CONTENT_KEYS.index(data.STUNT_JUMPS_ITEM), 2)
        self.assertEqual(scm.CONTENT_KEYS.index(data.ROBBABLE_STORES_ITEM), 4)

    def test_every_lockable_location_has_a_district(self) -> None:
        # A location with a content class but no district would fall out of the
        # split silently: content_item_for would return the class item and that
        # location would answer to an item no seed places once split.
        for location, class_item in data.LOCATION_CONTENT_CLASS.items():
            with self.subTest(location=location):
                district = data.location_district(location)
                self.assertIsNotNone(district, location)
                self.assertIn(district, district_data.DISTRICTS, location)
                self.assertIn(district, data.CONTENT_CLASS_DISTRICTS[class_item])

    def test_sunshine_completion_globals_match_the_hand_written_mirrors(self) -> None:
        # build_scm.py hard-codes these in three tables: SUNSHINE_IMPORT_LISTS
        # (the gate and completion write at each :IMPORTn_87 recognition block),
        # SUNSHINE_RACE_WINS (win flag -> completion global, for the APACT
        # watcher, mirrored again in add_markers.py's CLEO copy), and
        # SUNSHINE_RACE_PRIZES (the payout line to gate on the same global). A
        # location added or reordered anywhere earlier shifts every global here,
        # which would point each race's payout guard at another race. Pinned by
        # literal, so that shift fails here: update the script tables with it.
        expected = {
            "Sunshine Autos Import List 1": 9366,
            "Sunshine Autos Import List 2": 9367,
            "Sunshine Autos Import List 3": 9368,
            "Sunshine Autos Import List 4": 9369,
            "Sunshine Autos Race: Terminal Velocity": 9370,
            "Sunshine Autos Race: Ocean Drive": 9371,
            "Sunshine Autos Race: Border Run": 9372,
            "Sunshine Autos Race: Capital Cruise": 9373,
            "Sunshine Autos Race: Tour!": 9374,
            "Sunshine Autos Race: V.C. Endurance": 9375,
        }
        self.assertEqual(
            sorted(expected),
            sorted(data.VENUE_STRANDS["Sunshine Autos"] + data.SUNSHINE_RACES),
        )
        for name, global_index in expected.items():
            self.assertEqual(scm.completion_global(name), global_index, name)
        # The race payout guards read the properties class-cash flag, so a seed
        # with the class off pays vanilla; the same shift argument applies to it.
        self.assertEqual(scm.PROPERTIES_CASH_GLOBAL, 9585)

    def test_the_script_gated_content_items_keep_their_offsets(self) -> None:
        # The two classes with no icon for the ASI to hold gate in the script
        # instead, and build_scm.py indexes the district block by their position
        # in CONTENT_ITEMS (stunt jumps at 2, robbable stores at 4) times the
        # district count. Reordering CONTENT_ITEMS would point all 53 of those
        # gates at another class.
        self.assertEqual(scm.CONTENT_KEYS.index(data.STUNT_JUMPS_ITEM), 2)
        self.assertEqual(scm.CONTENT_KEYS.index(data.ROBBABLE_STORES_ITEM), 4)

    def test_item_globals_cover_every_progression_item(self) -> None:
        mapping = scm.item_globals()
        for strand in data.progressive_strands():
            self.assertIn(ITEM_NAME_TO_ID[data.progressive_item_name(strand)], mapping)
        for area_item in data.AREA_ITEMS:
            self.assertIn(ITEM_NAME_TO_ID[area_item], mapping)
        for ownership in data.PROPERTY_OWNERSHIP_ITEMS:
            self.assertEqual(
                mapping[ITEM_NAME_TO_ID[ownership]], scm.ownership_global(ownership),
            )

    def test_one_shot_effects_are_disjoint_from_count_globals(self) -> None:
        # A one-shot effect (consumable or trap) is applied once past the
        # applied-index; a reward/unlock item counts into a global. No item may
        # be both, or it would double.
        effect_ids = set(scm.item_effects().keys())
        count_ids = set(scm.item_globals().keys())
        self.assertTrue(effect_ids.isdisjoint(count_ids))
        # Every effect names a known type: the five consumables plus the six
        # trap types the ASI knows how to apply.
        known_types = {
            "cash", "weapon", "health", "armor", "clear_wanted",
            "trap_wanted", "trap_hostile_peds",
            "trap_weather", "trap_speed_up", "trap_slow_down", "trap_drunk",
        }
        for effect in scm.item_effects().values():
            self.assertIn(effect[0], known_types)

    def test_completion_watch_covers_every_location(self) -> None:
        watch = scm.completion_watch()
        self.assertEqual(sorted(watch.values()), sorted(LOCATION_NAME_TO_ID.values()))


class TestSlotData(WorldTestBase):
    game = "Grand Theft Auto Vice City"

    def test_slot_data_is_json_shaped_and_complete(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["goal"], "final_mission")
        self.assertTrue(slot_data["item_globals"])
        self.assertTrue(slot_data["completion_watch"])
        # JSON object keys are strings.
        for key in list(slot_data["item_globals"]) + list(slot_data["completion_watch"]):
            self.assertIsInstance(key, str)

    def test_package_coords_carry_every_package(self) -> None:
        # The ASI matches a collected pickup to its package by coordinate, so
        # slot_data carries one [x, y, z] per package, keyed by that package's
        # completion global (string key for JSON), all 100 present.
        coords = self.world.fill_slot_data()["package_coords"]
        self.assertEqual(len(coords), data.HIDDEN_PACKAGE_COUNT)
        for key, value in coords.items():
            self.assertIsInstance(key, str)
            self.assertEqual(len(value), 3)
        # Package 1's completion global maps to the first placed coordinate.
        first_global = str(scm.completion_global(data.hidden_package_name(1)))
        self.assertEqual(coords[first_global], list(data.PACKAGE_COORDS[0]))


class TestClassToggles(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_side_events": False}

    def test_disabled_class_removes_its_locations(self) -> None:
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        for side_event in data.SIDE_EVENTS:
            self.assertNotIn(side_event, names)

    def test_enabled_class_keeps_its_locations(self) -> None:
        # Rampages stay on (default), so a rampage check exists this seed.
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertIn(data.rampage_name(1), names)


class TestHiddenPackagesOffSendsNoCoords(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_hidden_packages": False}

    def test_no_package_coords_when_class_disabled(self) -> None:
        # With packages off their locations do not exist, so the ASI must get no
        # coordinates to detect and cannot report a package location.
        self.assertEqual(self.world.fill_slot_data()["package_coords"], {})
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertNotIn(data.hidden_package_name(1), names)

    def test_the_shuffled_flag_is_zero_so_the_package_cash_pays_vanilla(self) -> None:
        # The ASI reads this flag to decide whether to take back the package cash
        # the executable pays (a hundred each, a hundred thousand at the last
        # one). At zero it never fires, which is the toggle invariant: with the
        # class off the packages are vanilla, payouts included.
        config = self.world.fill_slot_data()["config_globals"]
        self.assertEqual(config[str(scm.PACKAGES_SHUFFLED_GLOBAL)], 0)


class TestRampagesStuntsSplit(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_rampages": True, "enable_stunt_jumps": False}

    def test_the_two_toggles_are_independent(self) -> None:
        # Rampages on, stunt jumps off: only the rampage locations exist.
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertIn(data.rampage_name(1), names)
        self.assertIn(data.rampage_name(data.RAMPAGE_COUNT), names)
        self.assertNotIn(data.stunt_jump_name(1), names)
        self.assertNotIn(data.stunt_jump_name(data.STUNT_JUMP_COUNT), names)


class TestTraps(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options carry trap_percentage = 15.

    def test_default_seed_has_traps_classified_as_traps(self) -> None:
        traps = [item for item in self.multiworld.itempool
                 if item.name in data.TRAP_ITEMS and item.player == self.player]
        self.assertGreater(len(traps), 0)
        # Traps carry the trap classification and never advance logic.
        self.assertTrue(all(item.classification == ItemClassification.trap for item in traps))
        self.assertTrue(all(not item.advancement for item in traps))

    def test_effects_carry_every_trap_type(self) -> None:
        # The item-effect contract sent to the ASI names every trap effect type.
        types = {effect[0] for effect in scm.item_effects().values()}
        for trap_type in ("trap_wanted", "trap_hostile_peds",
                          "trap_weather", "trap_speed_up", "trap_slow_down",
                          "trap_drunk"):
            self.assertIn(trap_type, types)

    def test_weather_traps_carry_their_engine_weather_id(self) -> None:
        # Both weather traps share the trap_weather type; the param is the
        # eWeather id the ASI forces, so the two items stay distinguishable.
        self.assertEqual(
            scm.item_effects()[ITEM_NAME_TO_ID["Stormy Weather Trap"]],
            ["trap_weather", data.WEATHER_RAINY],
        )
        self.assertEqual(
            scm.item_effects()[ITEM_NAME_TO_ID["Foggy Weather Trap"]],
            ["trap_weather", data.WEATHER_FOGGY],
        )

    def test_drunk_vision_trap_carries_its_duration(self) -> None:
        # Drunk vision is a timed trap: the param is the seconds the ASI holds
        # the drunk effect before letting it fade.
        self.assertEqual(
            scm.item_effects()[ITEM_NAME_TO_ID["Drunk Vision Trap"]],
            ["trap_drunk", data.TRAP_DURATION_SECONDS],
        )


class TestRemoveWantedLevelFiller(WorldTestBase):
    game = "Grand Theft Auto Vice City"

    def test_it_is_a_one_shot_clear_wanted_consumable(self) -> None:
        # The wanted-level clear (like the LEAVEMEALONE cheat) is plain filler,
        # never progression or a trap, and it rides the one-shot item-effect path
        # as clear_wanted, so the ASI applies it once past the applied-index.
        self.assertIn("Remove Wanted Level", data.FILLER_ITEMS)
        self.assertEqual(
            ITEM_CLASSIFICATIONS["Remove Wanted Level"], ItemClassification.filler,
        )
        effect = scm.item_effects()[ITEM_NAME_TO_ID["Remove Wanted Level"]]
        self.assertEqual(effect, ["clear_wanted"])


class TestTrapsDisabled(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"trap_percentage": 0}

    def test_zero_percent_places_no_traps(self) -> None:
        names = {item.name for item in self.multiworld.itempool}
        for trap in data.TRAP_ITEMS:
            self.assertNotIn(trap, names)


class TestTrapsAll(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"trap_percentage": 100}

    def test_all_filler_becomes_traps(self) -> None:
        # At 100 percent every filler slot is a trap, so trap items are present
        # and no plain filler remains. Progression and useful items are untouched,
        # so the seed still solves through the default reachability tests.
        pool_names = [item.name for item in self.multiworld.itempool
                      if item.player == self.player]
        self.assertGreater(len([n for n in pool_names if n in data.TRAP_ITEMS]), 0)
        self.assertEqual([n for n in pool_names if n in data.FILLER_ITEMS], [])


def _rampage_only_cash() -> set[str]:
    # Cash denominations paid only by rampages (no mission, package, side event,
    # or stunt jump pays the same amount), so their presence tracks the rampage
    # class exactly. Robust to later reward-value edits.
    rampage_names = {data.rampage_name(index) for index in range(1, data.RAMPAGE_COUNT + 1)}
    rampage_values = {data.LOCATION_REWARD[name] for name in rampage_names}
    other_values = {amount for name, amount in data.LOCATION_REWARD.items()
                    if amount > 0 and name not in rampage_names}
    return {data.cash_item_name(value) for value in rampage_values - other_values}


# The cash denominations, for tests that mean "a cash item" rather than any
# filler. Named for their amount alone, so there is no prefix to match on.
_CASH_FILLER_NAMES: frozenset[str] = frozenset(
    data.cash_item_name(amount) for amount in data.CASH_VALUES
)


class TestRewardData(WorldTestBase):
    game = "Grand Theft Auto Vice City"

    def test_stunt_and_rampage_reward_curves(self) -> None:
        # Stunt jumps pay $100 * n, except the final jump which pays $10,000.
        self.assertEqual(data.stunt_jump_reward(1), 100)
        self.assertEqual(data.stunt_jump_reward(35), 3500)
        self.assertEqual(data.stunt_jump_reward(data.STUNT_JUMP_COUNT), 10_000)
        # Rampages pay $50 * n, except the final rampage which pays a flat
        # $1,000 (the RAMPAGE thread's own numbers).
        self.assertEqual(data.rampage_reward(1), 50)
        self.assertEqual(data.rampage_reward(34), 1_700)
        self.assertEqual(data.rampage_reward(data.RAMPAGE_COUNT), 1_000)

    def test_every_location_has_exactly_one_reward_entry(self) -> None:
        # The mirror needs one reward per location: a missing key would KeyError
        # at generation, an extra one would drift from the location set.
        self.assertEqual(set(data.LOCATION_REWARD), set(LOCATION_NAME_TO_ID))

    def test_mission_rewards_cover_every_mission(self) -> None:
        missions = [m for missions in data.STORY_GIVERS.values() for m in missions]
        missions += [m for missions in data.VENUE_STRANDS.values() for m in missions]
        missions += [a for activities in data.VENUE_ACTIVITIES.values()
                     for a in activities]
        self.assertEqual(set(data.MISSION_REWARDS), set(missions))
        self.assertTrue(all(isinstance(amount, int) and amount >= 0
                            for amount in data.MISSION_REWARDS.values()))

    def test_sunshine_activities_mirror_their_vanilla_cash(self) -> None:
        # A race pays its prize on every win and the mod suppresses the first
        # win only, so the prize is exactly what the check eats and the mirror
        # returns it. An import list pays no cash of its own (it raises the
        # asset's daily take), so it draws generic filler. The amounts are the
        # showroom's own, in menu order.
        prizes = dict(zip(data.SUNSHINE_RACES,
                          (400, 2000, 4000, 8000, 20000, 40000), strict=True))
        for race, prize in prizes.items():
            self.assertEqual(data.LOCATION_REWARD[race], prize, race)
            self.assertEqual(data.mirror_item(race), data.cash_item_name(prize), race)
        for import_list in data.VENUE_STRANDS["Sunshine Autos"]:
            self.assertEqual(data.LOCATION_REWARD[import_list], 0, import_list)
            self.assertIsNone(data.mirror_item(import_list), import_list)

    def test_mirror_item_is_cash_when_paid_and_none_when_free(self) -> None:
        # A paying check mirrors to a cash item; a no-reward check mirrors to
        # generic filler (None).
        self.assertEqual(data.mirror_item(data.hidden_package_name(1)),
                         data.cash_item_name(data.package_cash_reward(1)))
        self.assertEqual(data.mirror_item(data.rampage_name(1)),
                         data.cash_item_name(data.rampage_reward(1)))
        self.assertIsNone(data.mirror_item("Printworks Purchase"))
        self.assertIsNone(data.mirror_item(data.emergency_name("Paramedic", 1)))

    def test_package_cash_is_a_graded_spread(self) -> None:
        # A deliberate variance spread, not vanilla: 40 x $100, 30 x $250,
        # 20 x $500, 10 x $1,000, summing to every package.
        self.assertEqual(sum(count for _amount, count in data.PACKAGE_CASH_TIERS),
                         data.HIDDEN_PACKAGE_COUNT)
        values = [data.LOCATION_REWARD[data.hidden_package_name(index)]
                  for index in range(1, data.HIDDEN_PACKAGE_COUNT + 1)]
        for amount, count in data.PACKAGE_CASH_TIERS:
            self.assertEqual(sum(1 for value in values if value == amount), count)

    def test_cash_items_are_filler_with_a_cash_effect(self) -> None:
        # Every mirrored denomination is a filler item riding the one-shot cash
        # effect the ASI already applies; none gates logic.
        self.assertTrue(data.CASH_VALUES)
        for amount in data.CASH_VALUES:
            name = data.cash_item_name(amount)
            self.assertIn(name, data.FILLER_ITEMS)
            self.assertEqual(ITEM_CLASSIFICATIONS[name], ItemClassification.filler)
            self.assertEqual(scm.item_effects()[ITEM_NAME_TO_ID[name]], ["cash", amount])


class TestRewardMirror(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: hidden packages, rampages, stunt jumps, side events on.

    def test_mirror_has_one_entry_per_enabled_location(self) -> None:
        self.assertEqual(len(self.world._reward_mirror()),
                         _check_count(self.multiworld, self.player))

    def test_itempool_fills_every_location(self) -> None:
        placed = [item for item in self.multiworld.itempool if item.player == self.player]
        self.assertEqual(len(placed), _check_count(self.multiworld, self.player))

    def test_a_cash_item_is_named_for_its_amount(self) -> None:
        # The amount alone, thousands separators kept, no prefix. The
        # hundredth-package bonus is named the same way, which is what puts the
        # two in one namespace.
        self.assertEqual(data.cash_item_name(100), "$100")
        self.assertEqual(data.cash_item_name(50_000), "$50,000")
        self.assertEqual(data.PACKAGE_CASH_REWARD, "$100,000")

    def test_no_two_items_share_a_name(self) -> None:
        # ITEM_NAME_TO_ID and CONSUMABLE_EFFECTS are both dicts, so two items
        # sharing a name silently become one item and every id after it shifts.
        # data.py asserts the one collision the naming makes likely, the package
        # bonus against a denomination; this covers every pair, and it holds in
        # the frozen build, which compiles asserts away.
        # Raw length against the dict's: comparing two unique counts would say
        # nothing, since the dict is built from this very list.
        self.assertEqual(len(ORDERED_ITEM_NAMES), len(ITEM_NAME_TO_ID))
        duplicates = sorted({name for name in ORDERED_ITEM_NAMES
                             if ORDERED_ITEM_NAMES.count(name) > 1})
        self.assertEqual(duplicates, [])
        self.assertNotIn(data.PACKAGE_CASH_REWARD, data.FILLER_ITEMS)
        # Every one-shot amount keeps its own entry, for the same reason.
        one_shots = [*_CASH_FILLER_NAMES, data.PACKAGE_CASH_REWARD]
        self.assertEqual(len(set(one_shots)), len(one_shots))
        for name in one_shots:
            self.assertIn(name, data.CONSUMABLE_EFFECTS, name)

    def test_filler_cash_is_bounded_by_the_reward_mirror(self) -> None:
        # Total filler cash can never exceed the sum of every mirrored reward, and
        # sampling only ever removes entries, so money is bounded, not arbitrary.
        cash_total = sum(
            data.CONSUMABLE_EFFECTS[item.name][1]
            for item in self.multiworld.itempool
            if item.player == self.player and item.name in _CASH_FILLER_NAMES
        )
        self.assertGreater(cash_total, 0)
        self.assertLessEqual(cash_total, sum(data.LOCATION_REWARD.values()))

    def test_filler_gives_way_from_the_smallest_amount_up(self) -> None:
        # There are always more mirror entries than filler slots, since
        # progression and useful items take slots first, so something is always
        # dropped. What survives is the money that matters: asked for ten slots,
        # the mirror hands back the entries of the ten best-paying checks and
        # nothing else, so a seed never spends a scarce slot on a hundred-dollar
        # item while thousands go unplaced. The wider the item pool grows, the
        # further up this order the cut lands.
        ranked = sorted(self.world._enabled_locations(),
                        key=lambda name: (-data.LOCATION_REWARD[name], name))
        kept = self.world._filler_entries(10)
        self.assertEqual(
            sorted(kept, key=str),
            sorted((data.mirror_item(name) for name in ranked[:10]), key=str),
        )

    def test_rampage_cash_present_when_rampages_on(self) -> None:
        mirror = set(self.world._reward_mirror())
        self.assertTrue(_rampage_only_cash())
        self.assertTrue(_rampage_only_cash().issubset(mirror))


class TestRewardMirrorClassOff(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_rampages": False}

    def test_disabling_a_class_drops_its_mirrored_cash(self) -> None:
        # With rampages off their locations do not exist, so no rampage-only cash
        # denomination enters the mirror.
        mirror = set(self.world._reward_mirror())
        self.assertTrue(_rampage_only_cash().isdisjoint(mirror))
