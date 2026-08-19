"""Generation and solvability tests for GTA: Vice City.

Run through scripts/run_tests.py, which links this world into a real
Archipelago checkout and invokes pytest.
"""

from __future__ import annotations

import io
import math
import random
from typing import ClassVar

from BaseClasses import CollectionState, ItemClassification
from Fill import distribute_items_restrictive
from Options import OptionError
from test.bases import WorldTestBase
from test.general import gen_steps, setup_multiworld
from worlds.AutoWorld import call_all

from .. import MINIMUM_SPHERE_ZERO, GTAViceCityWorld, data, scm
from ..items import ITEM_CLASSIFICATIONS, ITEM_NAME_TO_ID
from ..locations import (
    LOCATION_NAME_TO_ID,
    LOCATION_REGIONS,
    MISSION_GIVER,
    PACKAGE_NAMES,
    STORY_MISSION_NAMES,
    STRAND_MISSIONS,
)
from ..options import CHECK_CLASS_OPTIONS

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
        # $9460 up is SCM-internal (marker handles and visibility flags, whose
        # bases live in add_markers.py); the reserved contract must never grow
        # into it.
        self.assertLess(scm.highest_reserved_global(), 9460)


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
        # The in-shop cost lookup misreads on the bribe model, so the
        # permutation keeps bribes off shop-type slots.
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
        self.assertEqual(len(layout), len(data.PICKUP_SLOTS))
        for slot_index, row in enumerate(layout):
            x, y, z, pickup_type, _model, _ammo = data.PICKUP_SLOTS[slot_index]
            source = data.PICKUP_SLOTS[self.world.pickup_permutation[slot_index]]
            self.assertEqual(row, [x, y, z, pickup_type, source[4], source[5]])

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


_ALL_ABILITY_LOCKS: list[str] = [
    "sprint", "jump", "crouch", "vehicles", "weapon_equip", "wallet",
]

_ALL_CONTENT_LOCKS: list[str] = [
    "hidden_packages", "rampages", "stunt_jumps", "properties",
    "robbable_stores",
]


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
        self.assertFalse(self.can_reach_location("Unique Stunt Jump 01"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Unique Stunt Jump 01"))

    def test_emergency_level_needs_a_land_vehicle(self) -> None:
        self.assertFalse(self.can_reach_location("Paramedic Level 01"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Paramedic Level 01"))

    def test_chopper_checkpoint_needs_an_air_vehicle(self) -> None:
        # A start-island checkpoint: the helicopter is the requirement, not a
        # land vehicle.
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertFalse(self.can_reach_location("Ocean Beach Chopper Checkpoint"))
        self.collect_by_name([data.AIR_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Ocean Beach Chopper Checkpoint"))

    def test_warp_seated_side_events_need_no_vehicle(self) -> None:
        # Hotring and Bloodring take the player on foot and warp them into the
        # event car, which no lock constrains, so they carry no term. Dirtring
        # sets the player down beside a Sanchez to mount, so it does.
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location("Hotring"))
        self.assertTrue(self.can_reach_location("Bloodring"))
        self.assertFalse(self.can_reach_location("Dirtring"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Dirtring"))

    def test_robbable_store_needs_weapon_equip(self) -> None:
        self.assertFalse(self.can_reach_location("Robbable Store 01"))
        self.collect_by_name([data.WEAPON_EQUIP_ITEM])
        self.assertTrue(self.can_reach_location("Robbable Store 01"))

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
        self.assertEqual(data.FINALE_OPTIONAL_ASSETS["Sunshine Autos"], 1)
        self.assertIn(
            data.LAND_VEHICLES_ITEM,
            data.ASSET_ABILITY_REQUIREMENTS["Sunshine Autos"],
        )
        self.assertIn(
            data.LAND_VEHICLES_ITEM,
            data.MISSION_ABILITY_REQUIREMENTS["Sunshine Autos Import List 1"],
        )
        # And in the built rule, with Sunshine Autos as the deciding asset
        # rather than a passenger: hold the mandatory Printworks plus exactly
        # four optional assets that need no land vehicle (Kaufman Cabs,
        # Cherry Popper and Pole Position carry no ability term at all, and
        # Boatyard needs only the boat), so the threshold of five rests on
        # Sunshine Autos alone and Land Vehicles is what completes it.
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
        ])
        self.assertFalse(self.can_reach_location("Cap the Collector"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Cap the Collector"))

    def test_purchases_need_the_wallet(self) -> None:
        # A safehouse is for sale from a new game but locked money still blocks
        # paying; a business purchase carries the wallet through the sale
        # requirements.
        self.assertFalse(self.can_reach_location("El Swanko Casa Purchase"))
        self.collect_by_name([
            "Progressive Vercetti Protection", "Starfish Island Access",
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
        self.collect_by_name(["Progressive Avery"])
        self.assertFalse(self.can_reach_location("Demolition Man"))
        self.assertFalse(self.can_reach_location("Two Bit Hit"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Demolition Man"))
        self.assertTrue(self.can_reach_location("Two Bit Hit"))

    def test_a_first_mission_term_reaches_the_whole_strand(self) -> None:
        # Umberto's first mission is the one carrying the term, so every later
        # mission of his strand inherits it.
        self.collect_by_name(["Progressive Umberto Robina", "Mainland Access"])
        self.assertFalse(self.can_reach_location("Stunt Boat Challenge"))
        self.assertFalse(self.can_reach_location("Trojan Voodoo"))
        self.collect_by_name([data.SEA_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("Stunt Boat Challenge"))
        self.assertTrue(self.can_reach_location("Trojan Voodoo"))

    def test_a_strand_first_mission_inherits_nothing(self) -> None:
        # Propagation runs forward only: Four Iron opens on its unlock alone
        # even though Demolition Man behind it carries a term.
        self.collect_by_name(["Progressive Avery"])
        self.assertTrue(self.can_reach_location("Four Iron"))

    def test_cross_giver_edges_point_at_termless_missions(self) -> None:
        # Propagation stops at the strand boundary, so a cross-giver edge names
        # the target strand's progressive count alone. That is sound only while
        # the missions the count implies carry no lock or area requirement of
        # their own; an edge onto a locked mission would put that lock's item
        # behind the lock again, which is what propagation exists to prevent.
        for mission, giver in MISSION_GIVER.items():
            edges = (list(data.MISSION_PREREQUISITES.get(mission, []))
                     + list(data.STRAND_PREREQUISITES.get(giver, [])))
            for target_strand, count in edges:
                for implied in STRAND_MISSIONS[target_strand][:count]:
                    self.assertEqual(
                        data.LOCATION_ABILITY_REQUIREMENTS.get(implied, []), [],
                        f"{mission} implies {implied}")
                    self.assertEqual(
                        data.LOCATION_CONTENT_REQUIREMENTS.get(implied, []), [],
                        f"{mission} implies {implied}")
                    self.assertEqual(
                        data.MISSION_REGION_REQUIREMENTS.get(implied, []), [],
                        f"{mission} implies {implied}")

    def test_venue_race_mission_needs_its_vehicle(self) -> None:
        # The Driver is a forced car race, so it needs Land Vehicles on top of
        # the venue's own requirements.
        self.collect_by_name([
            "Progressive Malibu Club", "Malibu Club Ownership",
            "Progressive Vercetti Protection", "Starfish Island Access",
            data.WALLET_ITEM,
        ])
        self.assertTrue(self.can_reach_location("No Escape?"))
        self.assertFalse(self.can_reach_location("The Driver"))
        # The Job follows The Driver in the strand, so it inherits the term.
        self.assertFalse(self.can_reach_location("The Job"))
        self.collect_by_name([data.LAND_VEHICLES_ITEM])
        self.assertTrue(self.can_reach_location("The Driver"))
        self.assertTrue(self.can_reach_location("The Job"))

    def test_venue_activity_needs_its_vehicle(self) -> None:
        # A Sunshine Autos race is driven in the player's own car, and a venue
        # activity's rule is the only thing carrying that term (the races are
        # ruled by venue, not by the lock-term fallback), so it is pinned
        # through the rule rather than through the table alone. Without it the
        # fill could put Land Vehicles behind a race that needs it.
        self.collect_by_name([
            "Sunshine Autos Ownership", "Progressive Vercetti Protection",
            "Starfish Island Access", "Mainland Access", data.WALLET_ITEM,
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

    def test_no_ability_terms_without_the_locks(self) -> None:
        # With every key off a stunt jump needs only its region and a store
        # nothing at all: no rule may name an item that is not in the pool.
        self.assertTrue(self.can_reach_location("Robbable Store 01"))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location("Unique Stunt Jump 01"))
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
        self.assertTrue(self.can_reach_location("Unique Stunt Jump 01"))
        self.collect_by_name([data.WALLET_ITEM])
        self.assertTrue(self.can_reach_location("El Swanko Casa Purchase"))

    def test_finale_carries_the_wallet_through_the_sale_requirements(self) -> None:
        # Vanilla asset completion spends money, so the finale must hold the
        # wallet term or the fill could strand Wallet behind Cap the Collector.
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
            ("Robbable Store 01", data.ROBBABLE_STORES_ITEM),
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
        self.collect_by_name([
            "Progressive Vercetti Protection", "Starfish Island Access",
        ])
        self.assertFalse(self.can_reach_location("Malibu Club Purchase"))
        self.collect_by_name([data.PROPERTY_PURCHASES_ITEM])
        self.assertTrue(self.can_reach_location("Malibu Club Purchase"))

    def test_a_stunt_jump_needs_its_item_beyond_the_mainland(self) -> None:
        self.collect_by_name(["Mainland Access"])
        self.assertFalse(self.can_reach_location("Unique Stunt Jump 01"))
        self.collect_by_name([data.STUNT_JUMPS_ITEM])
        self.assertTrue(self.can_reach_location("Unique Stunt Jump 01"))

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
        self.assertTrue(self.can_reach_location("Robbable Store 01"))
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
        self.assertFalse(self.can_reach_location("Robbable Store 01"))
        self.collect_by_name([data.ROBBABLE_STORES_ITEM])
        self.assertFalse(self.can_reach_location("Robbable Store 01"))
        self.collect_by_name([data.WEAPON_EQUIP_ITEM])
        self.assertTrue(self.can_reach_location("Robbable Store 01"))

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
        self.assertEqual(len(placed), len(self.multiworld.get_locations(self.player)))

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

    def test_strand_opens_on_its_own_unlocks_alone(self) -> None:
        # The Chase is Diaz's first mission, given from the mansion on Starfish
        # Island. Strand starts are independent, so its rule is a Diaz unlock
        # plus the island; no other strand's items are needed.
        self.collect_by_name(["Progressive Diaz"])
        self.assertFalse(self.can_reach_location("The Chase"))
        self.collect_by_name(["Starfish Island Access"])
        self.assertTrue(self.can_reach_location("The Chase"))

    def test_avery_unlocks_in_vanilla_play_order(self) -> None:
        # Avery's vanilla chain is Four Iron, Demolition Man, Two Bit Hit: his
        # launchers start missions 18, 19 and 20 in that order, and Four Iron's
        # pass is what starts Demolition Man's launcher. His mission threads are
        # named SERG1, SERG3, SERG2, so pairing launchers by thread name puts
        # Two Bit Hit second.
        self.assertEqual(
            data.STORY_GIVERS["Avery"], ["Four Iron", "Demolition Man", "Two Bit Hit"])
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
        self.collect_by_name(["Progressive Diaz", "Starfish Island Access"])
        self.assertFalse(self.can_reach_location("Rub Out"))
        self.collect_by_name(["Progressive Death Row"])
        self.assertTrue(self.can_reach_location("Rub Out"))

    def test_final_mission_requires_the_protection_strand(self) -> None:
        # The finale keeps the one strand-level cross-giver edge: it sits
        # behind the protection strand. The asset items are collected up
        # front so the protection edge is the only thing under test.
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
        # area item either way, so it reads the routes from here. One entry means
        # the crossings are whole.
        routes = self.world.fill_slot_data()["mainland_routes"]
        self.assertEqual(routes, [{
            "global": scm.unlock_global("Mainland Access"),
            "label": "The mainland", "needs_global": 0, "needs_label": "",
        }])


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
        self.assertTrue(self.can_reach_location("Hidden Package - Viceport - 1"))
        self.assertTrue(self.can_reach_location(
            "Rocket Launcher Rampage - Escobar International"))

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

    def test_the_last_mission_needs_a_crossing(self) -> None:
        # Keep Your Friends Close... sits on Starfish but its launcher waits on
        # Cap the Collector, which is on the mainland, so its own rule carries
        # the crossing choice as a threshold rather than a single item.
        self.collect_by_name([
            "Progressive Vercetti Finale", "Progressive Vercetti Protection",
            "Starfish Island Access",
        ])
        self.collect_by_name(_FINALE_ASSET_ITEMS)
        self.assertFalse(self.can_reach_location(data.FINAL_MISSION))
        self.collect_by_name(["Ocean Beach Bridge"])
        self.assertTrue(self.can_reach_location(data.FINAL_MISSION))

    def test_slot_data_says_the_crossings_are_split(self) -> None:
        self.assertTrue(self.world.fill_slot_data()["split_mainland_access"])

    def test_every_route_is_shipped_with_what_it_needs(self) -> None:
        # One entry per crossing, each naming the global its item writes and the
        # name to show. Only the causeway carries a second requirement, and the
        # ASI reads it to know the difference between a route that opened and an
        # item that opened nothing yet.
        routes = self.world.fill_slot_data()["mainland_routes"]
        self.assertEqual([route["label"] for route in routes],
                         data.MAINLAND_CROSSING_ITEMS)
        for route in routes:
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
        for start_name in ["Tear Gas Rampage - Ocean Beach",
                            "Tec-9 Rampage - Washington Beach",
                            "Hidden Package - Ocean Beach - 1", "Paramedic Level 06"]:
            self.assertTrue(self.can_reach_location(start_name), start_name)
        mainland = ["Rocket Launcher Rampage - Escobar International",
                    "S.P.A.S. 12 Rampage - Escobar International",
                    "Hidden Package - Viceport - 1", "Paramedic Level 07"]
        for name in mainland:
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name(["Mainland Access"])
        for name in mainland:
            self.assertTrue(self.can_reach_location(name), name)

    def test_mainland_giver_mission_needs_mainland_access(self) -> None:
        # Phil Cassidy is a mainland giver, so his first mission needs its own
        # unlock AND Mainland Access, not the unlock alone.
        self.collect_by_name(["Progressive Phil Cassidy"])
        self.assertFalse(self.can_reach_location("Gun Runner"))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location("Gun Runner"))

    def test_mr_black_payphones_split_by_island(self) -> None:
        # Mr. Black's payphones span both islands. With his full unlock strand,
        # Road Kill (start island) is reachable but Loose Ends (mainland) still
        # waits on Mainland Access.
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

    def test_starfish_checks_need_starfish_access(self) -> None:
        # Starfish Island is its own region behind Starfish Island Access:
        # a package and a rampage on the island (both coordinate-verified)
        # wait for the item, and Mainland Access does not stand in for it,
        # because with Mainland Access alone both island gates stay shut.
        starfish = ["Hidden Package - Starfish Island - 3", data.rampage_name(14)]
        self.collect_by_name(["Mainland Access"])
        for name in starfish:
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name(["Starfish Island Access"])
        for name in starfish:
            self.assertTrue(self.can_reach_location(name), name)

    def test_starfish_access_alone_leaves_the_mainland_sealed(self) -> None:
        # The island's west gate opens only with both area items, so Starfish
        # Island Access alone never opens a walkable route onto the mainland.
        self.collect_by_name(["Starfish Island Access"])
        self.assertFalse(self.can_reach_location("Hidden Package - Viceport - 1"))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location("Hidden Package - Viceport - 1"))

    def test_mansion_giver_missions_sit_on_the_island(self) -> None:
        # Diaz and Vercetti Protection give from the mansion, so their first
        # missions need Starfish Island Access besides their own unlock.
        self.collect_by_name(["Progressive Diaz", "Progressive Vercetti Protection"])
        for name in ["The Chase", "Shakedown"]:
            self.assertFalse(self.can_reach_location(name), name)
        self.collect_by_name(["Starfish Island Access"])
        for name in ["The Chase", "Shakedown"]:
            self.assertTrue(self.can_reach_location(name), name)

    def test_finale_needs_both_area_items(self) -> None:
        # Keep Your Friends Close... starts at the mansion but only activates
        # once Cap the Collector (mainland) passes, so it needs both islands.
        # The asset items are collected up front so the area edge is the only
        # thing under test.
        self.collect_by_name([
            "Progressive Vercetti Finale", "Progressive Vercetti Protection",
        ])
        self.collect_by_name(_FINALE_ASSET_ITEMS)
        self.collect_by_name(["Starfish Island Access"])
        self.assertFalse(self.can_reach_location(data.FINAL_MISSION))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location(data.FINAL_MISSION))
        # And Cap the Collector itself is a mainland check, startable without
        # the island... except its property-sale requirements name Starfish
        # Island Access, which this test has already collected.
        self.assertTrue(self.can_reach_location("Cap the Collector"))


class TestHiddenPackagesGoalNeedsMainland(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"goal": "hidden_packages", "hidden_packages_required": 80}

    def test_high_package_goal_pulls_in_the_mainland(self) -> None:
        # The 100 Package Fragment macguffins are progression, so the fill must make
        # all of them reachable, which pulls in Mainland Access and the mainland
        # locations. A mainland package location stays gated until Mainland
        # Access; the default solvability tests prove the goal seed still beats.
        self.assertFalse(self.can_reach_location("Hidden Package - Escobar International - 1"))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location("Hidden Package - Escobar International - 1"))


class TestPropertyAccess(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_properties": True}

    def test_business_purchase_needs_the_shakedown_items(self) -> None:
        # A business goes on sale only when Shakedown passes, so its purchase
        # requires everything logic needs to pass Shakedown: its unlock item
        # and Starfish Island Access, since Shakedown gives from the mansion.
        # The price itself is grindable money and needs no item.
        self.assertFalse(self.can_reach_location("Malibu Club Purchase"))
        self.collect_by_name(["Progressive Vercetti Protection"])
        self.assertFalse(self.can_reach_location("Malibu Club Purchase"))
        self.collect_by_name(["Starfish Island Access"])
        self.assertTrue(self.can_reach_location("Malibu Club Purchase"))

    def test_mainland_purchase_needs_mainland_access_too(self) -> None:
        # A mainland business must also gate on Mainland Access so the fill
        # cannot strand Mainland Access behind it; a start-island business
        # does not.
        self.collect_by_name(["Progressive Vercetti Protection", "Starfish Island Access"])
        self.assertTrue(self.can_reach_location("Malibu Club Purchase"))
        self.assertFalse(self.can_reach_location("Kaufman Cabs Purchase"))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location("Kaufman Cabs Purchase"))

    def test_safehouse_purchase_is_free(self) -> None:
        # A safehouse is for sale from a new game, so a start-island safehouse
        # purchase is reachable with an empty inventory.
        self.assertTrue(self.can_reach_location("El Swanko Casa Purchase"))

    def test_venue_mission_needs_the_property_bought_and_owned(self) -> None:
        # No Escape? is the Malibu Club's first mission. The club must be
        # bought (it goes on sale only after Shakedown, so the mission needs
        # the Shakedown items) and owned (the building arrives as its
        # ownership item), besides its own progressive.
        self.collect_by_name(["Progressive Malibu Club", "Starfish Island Access"])
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
        for race in data.SUNSHINE_RACES:
            self.assertFalse(self.can_reach_location(race), race)
        self._collect_sunshine_base()
        for race in data.SUNSHINE_RACES:
            self.assertTrue(self.can_reach_location(race), race)

    def test_import_lists_are_a_progressive_ladder(self) -> None:
        # The four lists are the venue's strand, in the order vanilla already
        # chains them (each list's recognition thread starts the next), so list
        # n needs the first n unlocks. The races share the lot and need none.
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
        self.collect_by_name([
            "Progressive Vercetti Finale", "Progressive Vercetti Protection",
            "Mainland Access", "Starfish Island Access",
        ])

    def test_finale_needs_the_printworks_asset(self) -> None:
        # Cap the Collector keeps its vanilla prerequisite: Hit the Courier
        # passed is individually mandatory, so the Printworks items are too.
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
        self.collect_by_name([
            "Progressive Vercetti Finale", "Progressive Vercetti Protection",
            "Mainland Access",
        ])
        self.assertFalse(self.can_reach_location("Cap the Collector"))
        self.collect_by_name(["Starfish Island Access"])
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
        for start_name in ["Robbable Store 01", "Ocean Beach Chopper Checkpoint",
                            "RC Bandit Race", "Cone Crazy"]:
            self.assertTrue(self.can_reach_location(start_name), start_name)
        mainland = ["Robbable Store 03", "Hotring", "Unique Stunt Jump 01"]
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


class TestEmergencyRewardsRequireVehicles(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "shuffle_emergency_rewards": True, "enable_emergency_vehicles": False,
    }

    def test_reward_items_absent_without_the_vehicles_class(self) -> None:
        # Shuffle on but the emergency-vehicles class off: the toggle AND keeps
        # the reward items out of the pool, since there is nothing to complete.
        item_names = {item.name for item in self.multiworld.itempool}
        item_names |= {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        for reward in data.EMERGENCY_REWARD_ITEMS:
            self.assertNotIn(reward, item_names)


class TestConfigFlagsShuffleWithoutVehicles(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "shuffle_emergency_rewards": True, "enable_emergency_vehicles": False,
    }

    def test_emergency_flag_off_when_vehicles_off(self) -> None:
        # Shuffle on but vehicles off: no ability item is in the pool, so the
        # config flag must report NOT shuffled, or the SCM would suppress the
        # vanilla grants with nothing to replace them.
        config = self.world.fill_slot_data()["config_globals"]
        self.assertEqual(config[str(scm.EMERGENCY_SHUFFLED_GLOBAL)], 0)
        self.assertEqual(config[str(scm.PACKAGES_SHUFFLED_GLOBAL)], 1)


class TestConfigFlagsShuffled(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"shuffle_emergency_rewards": True}

    def test_emergency_flag_on_when_shuffled_and_vehicles_on(self) -> None:
        config = self.world.fill_slot_data()["config_globals"]
        self.assertEqual(config[str(scm.EMERGENCY_SHUFFLED_GLOBAL)], 1)


class TestClassCashFlagsAllOn(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: every check class is on.

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

    def test_a_starting_draw_never_rescues_a_narrow_seed(self) -> None:
        # The option docs promise that a config refused without the draw is
        # refused with it: the guard measures what is open with no item at all,
        # so no seed's solvability rests on a random draw. Nothing but this test
        # stops a later edit from teaching the guard about the draw.
        self._assert_rejected({
            "content_locks": ["hidden_packages"],
            "ability_locks": ["vehicles", "weapon_equip", "wallet"],
            "starting_content_unlock": True,
            "starting_ability_unlock": True,
        }, "check is reachable on a new game")

    def test_hundred_percent_rejects_with_a_class_off(self) -> None:
        # The 100 percent goal is a solvability contract: every stat
        # contributor must be a check, so generation must refuse the goal
        # unless every check class is enabled.
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

    def test_lock_combinations_that_close_the_start_island_are_refused(self) -> None:
        # These are measured, not derived. The first row is every key of both
        # families; the three after it are far smaller, so refusing does not
        # take every key. Nor does it take both families: content locks plus
        # disabled classes close the start with no ability key at all. Hidden
        # packages are the one class no ability term touches, so holding them is
        # what tips an ability-locked seed over. The neighbouring
        # content=[hidden_packages, rampages, robbable_stores] with
        # ability=[vehicles] is ACCEPTED at a free count of 6, so the boundary
        # is not simply "how many keys".
        for content, ability in (
            (_ALL_CONTENT_LOCKS, _ALL_ABILITY_LOCKS),
            (["hidden_packages"], ["vehicles", "weapon_equip", "wallet"]),
            (["hidden_packages", "properties"], ["vehicles", "weapon_equip"]),
            (["hidden_packages", "rampages", "robbable_stores", "properties"],
             ["vehicles"]),
        ):
            with self.subTest(content_locks=content, ability_locks=ability):
                self._assert_rejected(
                    {"content_locks": content, "ability_locks": ability},
                    "only 1 check is reachable",
                )

    def test_a_mainland_only_class_narrows_the_start_to_a_refusal(self) -> None:
        # The other way to a narrow start, with no lock involved: every stunt
        # jump sits on the mainland, so carrying them as the only collectible
        # class puts nothing in the start region.
        self._assert_rejected(dict(_STORY_ONLY_OPTIONS, enable_stunt_jumps=True),
                              "only 1 check is reachable")

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

    def test_packages_keep_a_locked_seed_wide(self) -> None:
        # The counterpart to the refusals above: no ability term touches a
        # hidden package, so with them on every lock key can be selected and
        # the start stays wide enough.
        self.options = {"ability_locks": _ALL_ABILITY_LOCKS}
        self.world_setup()
        self.assertGreaterEqual(self.world._free_start_location_count(),
                                MINIMUM_SPHERE_ZERO)


class TestTables(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    run_default_tests = False

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

    def test_venue_strands_are_not_story_missions(self) -> None:
        # The venue strands moved to the Properties class, so their missions
        # are no longer always-on story checks.
        for mission in ["No Escape?", "Recruitment Drive", "Cabmaggedon"]:
            self.assertNotIn(mission, STORY_MISSION_NAMES)

    def test_vehicle_rampages_are_the_unnamed_weapon_ones(self) -> None:
        # The ASI holds the weapon rampage icons by coordinate while this
        # table splits them by index, two hand-written mirrors of one
        # decompile fact. A rampage the RAMPAGE controller hands no weapon is
        # named without a weapon prefix, so the two views must agree or an
        # icon gets sunk for a check whose rule says Land Vehicles.
        unnamed = {
            index for index in range(1, data.RAMPAGE_COUNT + 1)
            if data.rampage_name(index).startswith("Rampage - ")
        }
        self.assertEqual(unnamed, set(data.VEHICLE_RAMPAGE_INDICES))
        # And each side of the split carries the ability its kill frenzy needs.
        for index in range(1, data.RAMPAGE_COUNT + 1):
            expected = (data.LAND_VEHICLES_ITEM if index in data.VEHICLE_RAMPAGE_INDICES
                        else data.WEAPON_EQUIP_ITEM)
            self.assertEqual(
                data.LOCATION_ABILITY_REQUIREMENTS[data.rampage_name(index)],
                [expected], index,
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
        for global_index in rewards | config | ownership | minimap | ability:
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
        # And under either setting, every way into the mainland is one of them.
        for split in (False, True):
            groups = data.region_access_groups(data.REGION_MAINLAND, split)
            self.assertTrue(groups, split)
            for group in groups:
                self.assertIn(group[0], alternatives, group)
        # The ASI hard-codes the packages-shuffled index too
        # (scm_game_state.cpp): it gates taking back the package cash the
        # executable pays, which no script gate can reach.
        self.assertEqual(scm.PACKAGES_SHUFFLED_GLOBAL, 9391)
        self.assertEqual(scm.ABILITY_LOCK_FLAG_BASE, 9434)
        self.assertEqual(scm.ABILITY_UNLOCK_BASE, 9442)
        self.assertEqual(scm.CONTENT_LOCK_FLAG_BASE, 9450)
        self.assertEqual(scm.CONTENT_UNLOCK_BASE, 9455)
        self.assertEqual(scm.highest_reserved_global(), 9459)
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
        self.assertEqual(scm.SIDE_EVENTS_CASH_GLOBAL, 9430)

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
        self.assertEqual(scm.PROPERTIES_CASH_GLOBAL, 9433)

    def test_the_script_gated_content_items_keep_their_offsets(self) -> None:
        # build_scm.py derives the two gates it writes into the script from
        # fixed offsets into this block (stunt jumps at +2, robbable stores at
        # +4), because those two classes have no icon for the ASI to hold.
        # Reordering CONTENT_ITEMS would point both gates at another class.
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
        # Every effect names a known type: the five consumables plus the seven
        # trap types the ASI knows how to apply.
        known_types = {
            "cash", "weapon", "health", "armor", "clear_wanted",
            "trap_wanted", "trap_explode_cars", "trap_hostile_peds",
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
        for trap_type in ("trap_wanted", "trap_explode_cars", "trap_hostile_peds",
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
                         len(self.multiworld.get_locations(self.player)))

    def test_itempool_fills_every_location(self) -> None:
        placed = [item for item in self.multiworld.itempool if item.player == self.player]
        self.assertEqual(len(placed), len(self.multiworld.get_locations(self.player)))

    def test_filler_cash_is_bounded_by_the_reward_mirror(self) -> None:
        # Total filler cash can never exceed the sum of every mirrored reward, and
        # sampling only ever removes entries, so money is bounded, not arbitrary.
        cash_total = sum(
            data.CONSUMABLE_EFFECTS[item.name][1]
            for item in self.multiworld.itempool
            if item.player == self.player and item.name.startswith("Cash $")
        )
        self.assertGreater(cash_total, 0)
        self.assertLessEqual(cash_total, sum(data.LOCATION_REWARD.values()))

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
