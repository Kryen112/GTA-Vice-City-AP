"""Shuffled progression, saved order, and the game's encoded order agree."""

import json
from typing import ClassVar

from Fill import distribute_items_restrictive
from Options import OptionError
from test.bases import WorldTestBase
from test.general import gen_steps, setup_multiworld
from worlds.AutoWorld import call_all

from .. import GTAViceCityWorld, data, mission_order, rules, scm


class TestMissionShuffle(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"mission_shuffle": True}

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
                    "mission_shuffle": True,
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

    def test_disabled_and_old_slots_keep_vanilla_order(self):
        generated = setup_multiworld(GTAViceCityWorld)
        world = generated.worlds[1]
        self.assertFalse(world.mission_order)
        self.assertTrue(all(value == 0 for value in scm.mission_order_globals({}).values()))
        slot = world.fill_slot_data()
        del slot["mission_shuffle"]
        del slot["mission_order"]
        self.multiworld.re_gen_passthrough = {self.game: slot}
        self.world.generate_early()
        self.assertFalse(self.world.options.mission_shuffle)
        self.assertFalse(self.world.mission_order)
