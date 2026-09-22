"""Shuffled progression, saved order, and the game's encoded order agree."""

import json
from random import Random
from typing import ClassVar
from unittest import TestCase
from unittest.mock import patch

from Fill import distribute_items_restrictive
from Options import OptionError
from test.bases import WorldTestBase
from test.general import gen_steps, setup_multiworld
from worlds.AutoWorld import call_all

from .. import GTAViceCityWorld, data, mission_order, mission_progression, rules, scm


class TestGlobalMissionAssignment(TestCase):
    def test_global_assignment_preserves_slots_and_mission_identity(self):
        strands = {giver: missions for giver, (_, missions) in data.progressive_strands().items()
                   if giver != "Sunshine Autos"}
        assignment = mission_order.shuffle_slots(strands, Random(17))
        inverse = mission_order.assigned_slots(strands, assignment)
        self.assertEqual(assignment, mission_order.shuffle_slots(strands, Random(17)))
        self.assertEqual(set(inverse), {mission for missions in strands.values() for mission in missions})
        self.assertTrue(any(giver != source for source, missions in strands.items()
                            for mission in missions for giver, _ in [inverse[mission]]))
        for giver, assigned in assignment.items():
            self.assertEqual(len(assigned), len(strands[giver]))
            for ordinal, mission in enumerate(assigned):
                self.assertEqual(inverse[mission], (giver, ordinal))
        # This layer enforces no endpoint restrictions.
        identity = {giver: list(missions) for giver, missions in strands.items()}
        identity["Rosenberg"][0], identity["Vercetti Finale"][-1] = (
            identity["Vercetti Finale"][-1], identity["Rosenberg"][0])
        swapped = mission_order.assigned_slots(strands, identity)
        self.assertEqual(swapped[data.FINAL_MISSION], ("Rosenberg", 0))
        self.assertEqual(swapped["An Old Friend"], ("Vercetti Finale", 1))

    def test_assignment_rejects_lost_duplicate_unknown_and_malformed_missions(self):
        strands = {"A": ["first", "second"], "B": ["third"]}
        invalid = [None, {}, {"A": ["first", "second"]},
                   {"A": ["first"], "B": ["second", "third"]},
                   {"A": ["first", "first"], "B": ["third"]},
                   {"A": ["first", "unknown"], "B": ["third"]},
                   {"A": ["first", []], "B": ["third"]},
                   {"A": ["first", "second"], "B": "third"}]
        for assignment in invalid:
            with self.subTest(assignment=assignment), self.assertRaises(ValueError):
                mission_order.assigned_slots(strands, assignment)

    def test_disabled_strands_do_not_enter_the_pool(self):
        strands = {giver: list(missions) for giver, missions in data.STORY_GIVERS.items()}
        original = {giver: list(missions) for giver, missions in strands.items()}
        assignment = mission_order.shuffle_slots(strands, Random(7))
        self.assertEqual(strands, original)
        self.assertEqual(set(assignment), set(data.STORY_GIVERS))
        self.assertEqual(mission_order.shuffle_slots({}, Random(7)), {})


class TestMissionShuffle(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"mission_shuffle": "within_giver"}

    def test_order_stays_with_its_giver_and_matches_script_encoding(self):
        world = self.world
        self.assertEqual(scm.MISSION_RANK_GLOBAL, mission_order.RANK_GLOBAL)
        self.assertEqual(scm.MISSION_DIGIT_GLOBAL, mission_order.DIGIT_GLOBAL)
        self.assertEqual(scm.MISSION_COMPLETED_GLOBAL, mission_order.COMPLETED_GLOBAL)
        flags = world.fill_slot_data()["config_globals"]
        for giver, (_, vanilla) in data.progressive_strands().items():
            ordered = world.mission_order.get(giver, vanilla)
            self.assertCountEqual(ordered, vanilla)
            if vanilla[-1] in data.MISSION_SHUFFLE_LAST:
                self.assertEqual(ordered[-1], vanilla[-1])
            offset = int(giver == data.SPHERE_ZERO_GIVER)
            if offset:
                self.assertEqual(ordered[0], "An Old Friend")
            global_index = mission_order.order_global(scm.unlock_global(giver))
            self.assertEqual(global_index, scm.unlock_global(f"Mission Order: {giver}"))
            encoded = flags[str(global_index)]
            for index, mission in enumerate(vanilla[offset:]):
                rank = encoded // (10 ** index) % 10 if encoded else index + 1
                self.assertEqual(rank, ordered.index(mission) + 1 - offset)
        self.assertNotIn("Sunshine Autos", world.mission_order)

    def test_one_cortez_item_opens_the_shuffled_first_mission(self):
        self.collect_by_name([*data.AREA_ITEMS])
        self.collect(self.world.create_item("Progressive Cortez"))
        ordered = self.world.mission_order["Cortez"]
        self.assertTrue(self.can_reach_location(ordered[0]))
        for mission in ordered[1:]:
            self.assertFalse(self.can_reach_location(mission))

    def test_cross_giver_edges_follow_the_named_mission(self):
        order = dict(self.world.mission_order)
        order["Cortez"] = ["Sir, Yes Sir!", "Mall Shootout", "Guardian Angels",
                           "Treacherous Swine", "All Hands On Deck!"]
        entries = rules.build_location_requirements(mission_order=order)
        self.assertEqual(dict(entries["Death Row"].requirements)["Progressive Cortez"], 1)
        inherited = rules._inherited_missions("Death Row", "Death Row", mission_order=order)
        self.assertIn("Sir, Yes Sir!", inherited)
        self.assertNotIn("All Hands On Deck!", inherited)
        order["Vercetti Protection"] = ["Bar Brawl", "Cop Land", "Shakedown"]
        entries = rules.build_location_requirements(mission_order=order)
        self.assertEqual(dict(entries["Malibu Club Purchase"].requirements)["Progressive Vercetti Protection"], 3)

    def test_tracker_replays_the_exact_order(self):
        slot = json.loads(json.dumps(self.world.fill_slot_data()))
        tracker = setup_multiworld(GTAViceCityWorld, steps=(), seed=902)
        tracker.re_gen_passthrough = {self.game: slot}
        for step in gen_steps:
            call_all(tracker, step)
        self.assertEqual(tracker.worlds[1].mission_order, self.world.mission_order)
        self.assertEqual(tracker.worlds[1].fill_slot_data()["config_globals"], slot["config_globals"])
        slot["mission_order"]["Cortez"] = ["Rub Out"]
        with self.assertRaises(OptionError):
            tracker.worlds[1].generate_early()

    def test_shuffled_seeds_fill_with_locks_and_reduced_locations(self):
        for seed in range(5):
            with self.subTest(seed=seed):
                generated = setup_multiworld(GTAViceCityWorld, seed=seed, options={
                    "mission_shuffle": "within_giver",
                    "ability_locks": list(data.ABILITY_LOCK_ITEMS),
                    "split_mainland_access": True,
                    "content_locks": ["properties", "stunt_jumps"],
                    "location_percentages": {"stunt_jumps": 50, "properties": 50},
                })
                distribute_items_restrictive(generated)
                self.assertTrue(generated.can_beat_game())
                self.assertFalse(generated.get_unfilled_locations())
        repeated = setup_multiworld(GTAViceCityWorld, seed=34, options=self.options)
        other = setup_multiworld(GTAViceCityWorld, seed=34, options=self.options)
        self.assertEqual(repeated.worlds[1].mission_order, other.worlds[1].mission_order)

    def test_disabled_slots_keep_vanilla_order(self):
        generated = setup_multiworld(GTAViceCityWorld)
        world = generated.worlds[1]
        self.assertFalse(world.mission_order)
        self.assertTrue(all(value == 0 for value in scm.mission_order_globals({}).values()))
        slot = world.fill_slot_data()
        self.multiworld.re_gen_passthrough = {self.game: slot}
        self.world.generate_early()
        self.assertFalse(self.world.options.mission_shuffle)
        self.assertFalse(self.world.mission_order)


class TestFullMissionShuffle(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"mission_shuffle": "full"}

    def test_slots_preserve_region_ids_and_bootstrap(self):
        from ..locations import LOCATION_NAME_TO_ID, LOCATION_REGIONS
        strands = mission_progression.full_strands(True)
        assignment = self.world.mission_order
        self.assertEqual(assignment["Rosenberg"][0], "An Old Friend")
        self.assertNotIn("Cherry Popper", assignment)
        self.assertNotIn("Boatyard", assignment)
        self.assertNotIn("Sunshine Autos", assignment)
        self.assertTrue(any(set(assignment[giver]) != set(missions) for giver, missions in strands.items()))
        for giver, missions in assignment.items():
            for ordinal, mission in enumerate(missions):
                location = self.multiworld.get_location(mission, 1)
                self.assertEqual(location.address, LOCATION_NAME_TO_ID[mission])
                self.assertEqual(location.parent_region.name, LOCATION_REGIONS[strands[giver][ordinal]])
        slot = self.world.fill_slot_data()
        self.assertEqual(slot["mission_shuffle"], "full")
        self.assertEqual(slot["final_location_id"], LOCATION_NAME_TO_ID[assignment["Vercetti Finale"][-1]])
        hints = {}
        self.world.extend_hint_information(hints)
        for giver, missions in assignment.items():
            for ordinal, mission in enumerate(missions):
                self.assertEqual(hints[1][LOCATION_NAME_TO_ID[mission]], f"{giver} slot {ordinal + 1}")

    def test_progressive_ranks_do_not_complete_slots_or_assets(self):
        from BaseClasses import CollectionState
        state = CollectionState(self.multiworld)
        for giver, (_, missions) in data.progressive_strands().items():
            for _ in missions:
                state.collect(self.world.create_item(data.progressive_item_name(giver)), prevent_sweep=True)
        self.assertFalse(state.has(mission_progression.asset_completed("Printworks"), 1))
        self.assertFalse(self.multiworld.get_location(self.world._goal_mission(), 1).access_rule(state))

    def test_finale_requires_seven_assets_of_any_kind(self):
        from BaseClasses import CollectionState, Item, ItemClassification
        state = CollectionState(self.multiworld)
        entries, _, _ = self.world._full_mission_graph()
        for name in self.world.item_name_to_id:
            for _ in range(5):
                state.collect(self.world.create_item(name), prevent_sweep=True)
        for name, count in entries[self.world._goal_mission()].requirements:
            for _ in range(count):
                state.collect(Item(name, ItemClassification.progression, None, 1), prevent_sweep=True)
        for index, asset in enumerate([*data.FINALE_OPTIONAL_ASSETS, "Printworks", "Vercetti Estate"]):
            state.collect(Item(mission_progression.asset_completed(asset), ItemClassification.progression, None, 1),
                          prevent_sweep=True)
            self.assertEqual(self.world._completion_condition()(state),
                             index + 1 >= self.world.options.finale_assets_required.value)

    def test_structural_cycle_rejects_saved_assignment_and_redraws_fresh_assignment(self):
        for restored in (True, False):
            with self.subTest(restored=restored):
                generated = setup_multiworld(GTAViceCityWorld, steps=("generate_early",), options={
                    "mission_shuffle": "full", "world_event_timing": "mission_completion"})
                world = generated.worlds[1]
                identity = mission_progression.full_strands(True)
                world.mission_order = {giver: list(missions) for giver, missions in identity.items()}
                world.mission_order["Vercetti Protection"][0], world.mission_order["Malibu Club"][0] = (
                    world.mission_order["Malibu Club"][0], world.mission_order["Vercetti Protection"][0])
                if restored:
                    generated.re_gen_passthrough = {self.game: {}}
                    with self.assertRaisesRegex(OptionError, "structurally blocked"):
                        world.create_regions()
                else:
                    with patch.object(mission_progression, "shuffle_full", return_value=identity) as redraw:
                        world.create_regions()
                    redraw.assert_called_once()
                    self.assertEqual(world.mission_order, identity)

    def test_moved_mainland_payload_needs_gameplay_abilities_but_no_island_item(self):
        from BaseClasses import CollectionState
        generated = setup_multiworld(GTAViceCityWorld, steps=("generate_early",), options={
            "mission_shuffle": "full", "ability_locks": ["vehicles"]})
        world = generated.worlds[1]
        world.mission_order = mission_progression.full_strands(True)
        world.mission_order["Rosenberg"][1], world.mission_order["Kaufman Cabs"][0] = (
            world.mission_order["Kaufman Cabs"][0], world.mission_order["Rosenberg"][1])
        world.create_regions()
        state = CollectionState(generated)
        state.collect(world.create_item("Progressive Rosenberg"))
        self.assertFalse(state.can_reach_location("V.I.P.", 1))
        state.collect(world.create_item(data.LAND_VEHICLES_ITEM))
        self.assertTrue(state.can_reach_location("V.I.P.", 1))
        self.assertFalse(state.has("Mainland Access", 1))
        self.assertFalse(state.can_reach_region(data.REGION_MAINLAND, 1))

    def test_world_effects_do_not_replace_payload_rewards(self):
        entries, _, _ = self.world._full_mission_graph()
        self.assertEqual(entries[data.mission_event_name("All Hands On Deck!")].requirements,
                         [(mission_progression.mission_completed("All Hands On Deck!"), 1)])
        self.assertEqual(entries[data.mission_event_name("Rub Out")].requirements,
                         [(mission_progression.mission_completed("Rub Out"), 1)])
        self.assertIn((mission_progression.MANSION_TAKEN_OVER, 1), entries[data.pickup_name(61)].requirements)
        self.assertIn((mission_progression.CORTEZ_DEPARTED, 1), entries[data.stunt_jump_name(25)].requirements)
        for asset in ("Printworks", "Vercetti Estate"):
            term = (mission_progression.asset_completed(asset), 1)
            self.assertNotIn(term, entries["Cap the Collector"].requirements)
            self.assertIn([term], entries["Cap the Collector"].thresholds[-1][0])

    def test_full_seeds_fill_and_tracker_replays_both_event_policies(self):
        for timing in ("quest_giver_progress", "mission_completion"):
            for seed in range(3):
                with self.subTest(timing=timing, seed=seed):
                    options = {"mission_shuffle": "full", "world_event_timing": timing,
                               "ability_locks": list(data.ABILITY_LOCK_ITEMS),
                               "content_locks": ["properties"], "split_mainland_access": bool(seed % 2),
                               "enable_properties": seed != 2}
                    generated = setup_multiworld(GTAViceCityWorld, seed=seed, options=options)
                    distribute_items_restrictive(generated)
                    self.assertTrue(generated.can_beat_game())
                    self.assertFalse(generated.get_unfilled_locations())
                    slot = json.loads(json.dumps(generated.worlds[1].fill_slot_data()))
                    tracker = setup_multiworld(GTAViceCityWorld, steps=(), seed=900)
                    tracker.re_gen_passthrough = {self.game: slot}
                    for step in gen_steps:
                        call_all(tracker, step)
                    self.assertEqual(tracker.worlds[1].mission_order, generated.worlds[1].mission_order)
                    self.assertEqual(tracker.worlds[1].fill_slot_data()["config_globals"], slot["config_globals"])

class TestKeepYourFriendsCloseGoal(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    auto_construct = False

    def test_early_final_mission_can_win_without_completing_finale_slot(self):
        from BaseClasses import CollectionState

        from ..locations import LOCATION_NAME_TO_ID
        from ..options import Goal

        for goal in ("final_mission", "keep_your_friends_close"):
            with self.subTest(goal=goal):
                self.multiworld = setup_multiworld(GTAViceCityWorld, steps=("generate_early",), options={
                    "mission_shuffle": "full", "goal": goal})
                self.world = self.multiworld.worlds[1]
                order = mission_progression.full_strands(True)
                self.world.mission_order = {giver: list(missions) for giver, missions in order.items()}
                self.world.mission_order["Rosenberg"][1], self.world.mission_order["Vercetti Finale"][1] = (
                    self.world.mission_order["Vercetti Finale"][1], self.world.mission_order["Rosenberg"][1])
                for step in ("create_regions", "create_items", "set_rules"):
                    call_all(self.multiworld, step)
                state = CollectionState(self.multiworld)
                for item in self.multiworld.itempool:
                    if item.name not in ("Mainland Access", "Starfish Island Access", "Progressive Vercetti Finale"):
                        state.collect(item, prevent_sweep=True)
                state.sweep_for_advancements()
                self.assertTrue(state.can_reach_location(data.FINAL_MISSION, 1))
                self.assertFalse(state.can_reach_location("The Party", 1))
                alternate = self.world.options.goal == Goal.option_keep_your_friends_close
                self.assertEqual(self.multiworld.completion_condition[1](state), alternate)
                slot = self.world.fill_slot_data()
                target = data.FINAL_MISSION if alternate else "The Party"
                self.assertEqual(slot["final_location_id"], LOCATION_NAME_TO_ID[target])
                self.assertEqual(slot["goal_trigger"]["kind"], "mission" if alternate else "mission_slot")
                if alternate:
                    self.assertNotIn("giver", slot["goal_trigger"])


class TestConfigurableFinaleAssets(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    auto_construct = False

    def test_all_counts_and_tracker_transport(self):
        from BaseClasses import CollectionState, Item, ItemClassification

        from ..mission_layout import FINALE_ASSETS_REQUIRED_GLOBAL
        assets = ["Vercetti Estate", "Printworks", *data.FINALE_OPTIONAL_ASSETS]
        for required in range(10):
            with self.subTest(required=required):
                generated = setup_multiworld(GTAViceCityWorld, steps=("generate_early",), options={
                    "mission_shuffle": "full", "finale_assets_required": required})
                world = generated.worlds[1]
                world.mission_order = mission_progression.full_strands(True)
                world.create_regions()
                world.create_items()
                world.set_rules()
                entries, _, _ = world._full_mission_graph()
                state = CollectionState(generated)
                for name, count in entries[data.FINAL_MISSION].requirements:
                    for _ in range(count):
                        state.collect(Item(name, ItemClassification.progression, None, 1), prevent_sweep=True)
                rule = rules.compile_requirements(entries[data.FINAL_MISSION])
                for count in range(10):
                    self.assertEqual(rule(state, 1), count >= required)
                    if count < 9:
                        state.collect(Item(mission_progression.asset_completed(assets[count]),
                                           ItemClassification.progression, None, 1), prevent_sweep=True)
                slot = world.fill_slot_data()
                self.assertEqual(slot["finale_assets_required"], required)
                self.assertEqual(slot["config_globals"][str(FINALE_ASSETS_REQUIRED_GLOBAL)], required)
                world.options.finale_assets_required.value = 7
                world._restore_options(slot)
                self.assertEqual(world.options.finale_assets_required.value, required)

    def test_zero_assets_does_not_require_business_or_protection_items(self):
        for shuffle in ("off", "within_giver"):
            generated = setup_multiworld(GTAViceCityWorld, options={
                "mission_shuffle": shuffle, "finale_assets_required": 0})
            from BaseClasses import CollectionState
            state = CollectionState(generated)
            for item in generated.itempool:
                if "Ownership" not in item.name and item.name != "Progressive Vercetti Protection":
                    state.collect(item, prevent_sweep=True)
            state.sweep_for_advancements()
            self.assertTrue(state.can_reach_location(data.FINAL_MISSION, 1))


    def test_disabled_property_checks_keep_asset_ability_requirements(self):
        from BaseClasses import CollectionState
        for required in (1, 9):
            generated = setup_multiworld(GTAViceCityWorld, options={
                "enable_properties": False, "finale_assets_required": required,
                "ability_locks": ["wallet", "vehicles"]})
            state = CollectionState(generated)
            for item in generated.itempool:
                if item.name not in (data.AIR_VEHICLES_ITEM, data.WALLET_ITEM):
                    state.collect(item, prevent_sweep=True)
            state.sweep_for_advancements()
            self.assertEqual(state.can_reach_location(data.FINAL_MISSION, 1), required == 1)
            state.collect(generated.worlds[1].create_item(data.WALLET_ITEM))
            self.assertEqual(state.can_reach_location(data.FINAL_MISSION, 1), required == 1)
            state.collect(generated.worlds[1].create_item(data.AIR_VEHICLES_ITEM))
            self.assertTrue(state.can_reach_location(data.FINAL_MISSION, 1))


    def test_mandatory_assets_fit_within_the_count_and_roundtrip(self):
        from BaseClasses import CollectionState, Item, ItemClassification

        from ..mission_layout import FINALE_MANDATORY_ASSETS_GLOBAL
        for required in range(10):
            generated = setup_multiworld(GTAViceCityWorld, steps=("generate_early",), options={
                "mission_shuffle": "full", "finale_assets_required": required,
                "require_printworks_and_estate": True})
            world = generated.worlds[1]
            world.mission_order = mission_progression.full_strands(True)
            world.create_regions()
            world.create_items()
            world.set_rules()
            entries, _, _ = world._full_mission_graph()
            state = CollectionState(generated)
            for name, count in entries[data.FINAL_MISSION].requirements:
                if name.startswith("Income asset completed:"):
                    continue
                for _ in range(count):
                    state.collect(Item(name, ItemClassification.progression, None, 1), prevent_sweep=True)
            rule = rules.compile_requirements(entries[data.FINAL_MISSION])
            for asset in data.FINALE_OPTIONAL_ASSETS:
                state.collect(Item(mission_progression.asset_completed(asset), ItemClassification.progression,
                                   None, 1), prevent_sweep=True)
            self.assertEqual(rule(state, 1), required == 0)
            state.collect(Item(mission_progression.asset_completed("Printworks"), ItemClassification.progression,
                               None, 1), prevent_sweep=True)
            self.assertEqual(rule(state, 1), required <= 1)
            state.collect(Item(mission_progression.asset_completed("Vercetti Estate"), ItemClassification.progression,
                               None, 1), prevent_sweep=True)
            self.assertTrue(rule(state, 1))
            slot = world.fill_slot_data()
            self.assertTrue(slot["require_printworks_and_estate"])
            self.assertEqual(slot["config_globals"][str(FINALE_MANDATORY_ASSETS_GLOBAL)], 1)
            world.options.require_printworks_and_estate.value = 0
            world._restore_options(slot)
            self.assertTrue(world.options.require_printworks_and_estate)

    def test_mandatory_assets_in_nonfull_modes(self):
        from BaseClasses import CollectionState
        for shuffle in ("off", "within_giver"):
            for required in (0, 1, 2):
                generated = setup_multiworld(GTAViceCityWorld, options={
                    "mission_shuffle": shuffle, "finale_assets_required": required,
                    "require_printworks_and_estate": True})
                world = generated.worlds[1]
                state = CollectionState(generated)
                for item in generated.itempool:
                    if item.name not in ("Printworks Ownership", "Progressive Printworks",
                                         "Progressive Vercetti Protection"):
                        state.collect(item, prevent_sweep=True)
                sale_rank = world.mission_order.get("Vercetti Protection",
                                                    data.STORY_GIVERS["Vercetti Protection"]).index("Shakedown") + 1
                for _ in range(sale_rank):
                    state.collect(world.create_item("Progressive Vercetti Protection"), prevent_sweep=True)
                state.sweep_for_advancements()
                self.assertEqual(state.can_reach_location(data.FINAL_MISSION, 1), required == 0)
                for item in generated.itempool:
                    if item.name in ("Printworks Ownership", "Progressive Printworks"):
                        state.collect(item, prevent_sweep=True)
                state.sweep_for_advancements()
                estate_rank = world.mission_order.get("Vercetti Protection",
                                                      data.STORY_GIVERS["Vercetti Protection"]).index("Cop Land") + 1
                self.assertEqual(state.can_reach_location(data.FINAL_MISSION, 1),
                                 required <= 1 or sale_rank >= estate_rank)
                for _ in range(3 - sale_rank):
                    state.collect(world.create_item("Progressive Vercetti Protection"), prevent_sweep=True)
                state.sweep_for_advancements()
                self.assertTrue(state.can_reach_location(data.FINAL_MISSION, 1))
