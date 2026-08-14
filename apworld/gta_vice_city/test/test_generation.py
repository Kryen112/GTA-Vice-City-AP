"""Generation and solvability tests for GTA: Vice City.

Run through scripts/run_tests.py, which links this world into a real
Archipelago checkout and invokes pytest.
"""

from __future__ import annotations

from typing import ClassVar

from BaseClasses import CollectionState, ItemClassification
from Options import OptionError
from test.bases import WorldTestBase

from .. import data, scm
from ..items import ITEM_CLASSIFICATIONS, ITEM_NAME_TO_ID
from ..locations import LOCATION_NAME_TO_ID, PACKAGE_NAMES, STORY_MISSION_NAMES
from ..options import CHECK_CLASS_OPTIONS


class TestDefault(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: final-mission goal, hidden packages on.


class TestHiddenPackagesGoal(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"goal": "hidden_packages", "hidden_packages_required": 50}

    def test_pool_holds_one_macguffin_per_package(self) -> None:
        macguffins = [
            item for item in self.multiworld.itempool
            if item.name == data.HIDDEN_PACKAGE_ITEM and item.player == self.player
        ]
        self.assertEqual(len(macguffins), data.HIDDEN_PACKAGE_COUNT)
        # Progression, so the generator guarantees enough are reachable.
        self.assertTrue(all(item.advancement for item in macguffins))

    def test_goal_counts_received_macguffins_not_own_pickups(self) -> None:
        # The bug this guards: the goal is how many Hidden Package items are
        # received, not whether the player reaches package locations in their own
        # game. A state with no macguffins does not win; receiving enough does.
        completion = self.multiworld.completion_condition[self.player]
        state = CollectionState(self.multiworld)
        self.assertFalse(completion(state))
        for _ in range(50):
            state.collect(
                self.world.create_item(data.HIDDEN_PACKAGE_ITEM), prevent_sweep=True,
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


class TestStoryOnly(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = dict(_STORY_ONLY_OPTIONS)

    def test_solvable_with_only_story_missions(self) -> None:
        # A solo story-only seed is an all-progression pool with a one-location
        # sphere 0, so the world grants the start-island story strands at the
        # start to keep it fillable. The default reachability tests already
        # prove solvability; this asserts the world generated at all and left
        # the final mission as a real check.
        self.assertIn(
            data.FINAL_MISSION,
            {location.name for location in self.multiworld.get_locations(self.player)},
        )

    def test_opening_grant_givers_enlarge_sphere_zero(self) -> None:
        # The grant exists to enlarge sphere 0, so every granted strand must
        # be a story giver off the mainland (a mainland strand cannot open
        # before Mainland Access), with the free sphere-0 giver included.
        self.assertIn(data.SPHERE_ZERO_GIVER, data.OPENING_GRANT_GIVERS)
        for giver in data.OPENING_GRANT_GIVERS:
            self.assertIn(giver, data.STORY_GIVERS, giver)
            self.assertNotIn(giver, data.MAINLAND_GIVERS, giver)
        # And the grant really landed: the granted unlocks are precollected.
        precollected = [item.name for item in self.multiworld.precollected_items[self.player]]
        for giver in data.OPENING_GRANT_GIVERS:
            self.assertIn(data.progressive_item_name(giver), precollected, giver)


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
            slot_data["hidden_package_item_id"], ITEM_NAME_TO_ID[data.HIDDEN_PACKAGE_ITEM],
        )
        # And watches this location being checked for the final-mission goal.
        self.assertEqual(
            slot_data["final_location_id"], LOCATION_NAME_TO_ID[data.FINAL_MISSION],
        )
        self.assertFalse(slot_data["enable_properties"])
        self.assertTrue(slot_data["enable_hidden_packages"])
        self.assertIn("shuffle_emergency_rewards", slot_data)
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
        for name in CHECK_CLASS_OPTIONS:
            self.assertEqual(getattr(self.world.options, name).value, 1)


class TestStrandAccess(WorldTestBase):
    game = "Grand Theft Auto Vice City"

    def test_strand_opens_on_its_own_unlocks_alone(self) -> None:
        # The Chase is Diaz's first mission. Strand starts are independent, so
        # its rule is a Diaz unlock alone; no other strand's items are needed.
        self.assertFalse(self.can_reach_location("The Chase"))
        self.collect_by_name(["Progressive Diaz"])
        self.assertTrue(self.can_reach_location("The Chase"))

    def test_rub_out_requires_death_row(self) -> None:
        # Rub Out, Diaz's last mission, keeps the one mission-level cross-giver
        # edge: Lance must be rescued in Death Row first.
        self.collect_by_name(["Progressive Diaz"])
        self.assertFalse(self.can_reach_location("Rub Out"))
        self.collect_by_name(["Progressive Death Row"])
        self.assertTrue(self.can_reach_location("Rub Out"))

    def test_final_mission_requires_the_protection_strand(self) -> None:
        # The finale keeps the one strand-level cross-giver edge: it sits
        # behind the protection strand, and nothing else beyond its own
        # unlocks and Mainland Access.
        self.collect_by_name(["Progressive Vercetti Finale", "Mainland Access"])
        self.assertFalse(self.can_reach_location(data.FINAL_MISSION))
        self.collect_by_name(["Progressive Vercetti Protection"])
        self.assertTrue(self.can_reach_location(data.FINAL_MISSION))


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


class TestHiddenPackagesGoalNeedsMainland(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"goal": "hidden_packages", "hidden_packages_required": 80}

    def test_high_package_goal_pulls_in_the_mainland(self) -> None:
        # The 100 Hidden Package macguffins are progression, so the fill must make
        # all of them reachable, which pulls in Mainland Access and the mainland
        # locations. A mainland package location stays gated until Mainland
        # Access; the default solvability tests prove the goal seed still beats.
        self.assertFalse(self.can_reach_location("Hidden Package - Escobar International - 1"))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location("Hidden Package - Escobar International - 1"))


class TestMainlandPropertyPurchase(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"enable_properties": True}

    def test_mainland_purchase_needs_mainland_access(self) -> None:
        # A purchase carries no rule beyond its region. A mainland business must
        # gate on Mainland Access so the fill cannot strand Mainland Access behind
        # it; a start-island business does not.
        self.assertTrue(self.can_reach_location("Malibu Club Purchase"))
        self.assertFalse(self.can_reach_location("Kaufman Cabs Purchase"))
        self.collect_by_name(["Mainland Access"])
        self.assertTrue(self.can_reach_location("Kaufman Cabs Purchase"))


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
        location_names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertNotIn("No Escape?", location_names)
        self.assertNotIn("Malibu Club Purchase", location_names)


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


class TestRejections(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    auto_construct = False

    def _assert_rejected(self, options: dict) -> None:
        self.options = options
        with self.assertRaises(OptionError):
            self.world_setup()

    def test_hundred_percent_rejects_with_a_class_off(self) -> None:
        # The 100 percent goal is a solvability contract: every stat
        # contributor must be a check, so generation must refuse the goal
        # unless every check class is enabled.
        self._assert_rejected({"goal": "hundred_percent", "enable_side_events": False})

    def test_hidden_packages_goal_rejects_without_packages(self) -> None:
        self._assert_rejected({"goal": "hidden_packages", "enable_hidden_packages": False})


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
        # 15 property purchases plus the venue mission strands.
        self.assertEqual(len(classes["properties"][1]), 31)

    def test_venue_strands_are_not_story_missions(self) -> None:
        # The venue strands moved to the Properties class, so their missions
        # are no longer always-on story checks.
        for mission in ["No Escape?", "Recruitment Drive", "Cabmaggedon"]:
            self.assertNotIn(mission, STORY_MISSION_NAMES)


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
        config = {scm.PACKAGES_SHUFFLED_GLOBAL, scm.EMERGENCY_SHUFFLED_GLOBAL}
        self.assertEqual(len(rewards), len(scm.REWARD_KEYS))
        self.assertTrue(seed_hash.isdisjoint(unlocks))
        self.assertTrue(seed_hash.isdisjoint(completions))
        self.assertTrue(unlocks.isdisjoint(completions))
        # The reward and config-flag blocks must not collide with anything else,
        # and must stay within the declared reserved block the foundation sizes.
        self.assertTrue(rewards.isdisjoint(seed_hash | unlocks | completions | config))
        self.assertTrue(config.isdisjoint(seed_hash | unlocks | completions | rewards))
        for global_index in rewards | config:
            self.assertLessEqual(global_index, scm.highest_reserved_global())
        self.assertNotIn(scm.APPLIED_INDEX_GLOBAL, unlocks | completions | rewards | config)

    def test_item_globals_cover_every_progression_item(self) -> None:
        mapping = scm.item_globals()
        for strand in data.progressive_strands():
            self.assertIn(ITEM_NAME_TO_ID[data.progressive_item_name(strand)], mapping)
        for area_item in data.AREA_ITEMS:
            self.assertIn(ITEM_NAME_TO_ID[area_item], mapping)

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
            "trap_wanted", "trap_explode_cars", "trap_hostile_peds",
            "trap_weather", "trap_speed_up", "trap_slow_down",
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

    def test_effects_carry_the_six_trap_types(self) -> None:
        # The item-effect contract sent to the ASI names every trap effect type.
        types = {effect[0] for effect in scm.item_effects().values()}
        for trap_type in ("trap_wanted", "trap_explode_cars", "trap_hostile_peds",
                          "trap_weather", "trap_speed_up", "trap_slow_down"):
            self.assertIn(trap_type, types)


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
        # Rampages pay $500 for the first and $500 more for each one after it.
        self.assertEqual(data.rampage_reward(1), 500)
        self.assertEqual(data.rampage_reward(data.RAMPAGE_COUNT), 500 * data.RAMPAGE_COUNT)

    def test_every_location_has_exactly_one_reward_entry(self) -> None:
        # The mirror needs one reward per location: a missing key would KeyError
        # at generation, an extra one would drift from the location set.
        self.assertEqual(set(data.LOCATION_REWARD), set(LOCATION_NAME_TO_ID))

    def test_mission_rewards_cover_every_mission(self) -> None:
        missions = [m for missions in data.STORY_GIVERS.values() for m in missions]
        missions += [m for missions in data.VENUE_STRANDS.values() for m in missions]
        self.assertEqual(set(data.MISSION_REWARDS), set(missions))
        self.assertTrue(all(isinstance(amount, int) and amount >= 0
                            for amount in data.MISSION_REWARDS.values()))

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
