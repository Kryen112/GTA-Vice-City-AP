"""Partial check classes use the same selection in generation and game config."""

import json
from collections import Counter
from math import ceil
from typing import ClassVar

from BaseClasses import ItemClassification
from Fill import distribute_items_restrictive
from Options import OptionError
from test.bases import WorldTestBase
from test.general import gen_steps, setup_multiworld
from worlds.AutoWorld import call_all
from worlds.generic.Rules import exclusion_rules

from .. import GTAViceCityWorld, data, scm
from ..locations import LOCATION_NAME_TO_ID, STORY_MISSION_NAMES
from ..options import CHECK_CLASS_OPTIONS, LocationPercentages, MilestoneSpacing


class TestLocationPercentages(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "enable_pickups": True,
        "shuffle_shops": True,
        "location_percentages": {"pickups": 80, "stunt_jumps": 50, "shops": 50,
                                 "paramedic": 50, "taxi": 30},
        "milestone_spacing": {"taxi": 5},
    }

    def test_counts_and_game_config(self) -> None:
        world = self.world
        names = {location.name for location in self.multiworld.get_locations(1) if location.address}
        for key, (_, class_names) in data.optional_check_classes().items():
            expected = ceil(len(class_names) * self.options["location_percentages"].get(key, 100) / 100)
            if key == "emergency_vehicles":
                expected = sum(self.options["location_percentages"].get("taxi", 100) // 5 if activity == "Taxi"
                               else ceil(levels * self.options["location_percentages"].get(activity.lower(), 100) / 100)
                               for activity, levels in data.EMERGENCY_LEVELS.items())
            self.assertEqual(len(names.intersection(class_names)), expected, key)
        self.assertTrue(set(STORY_MISSION_NAMES) <= names)
        self.assertEqual(len(self.multiworld.itempool), len(names))
        slot = world.fill_slot_data()
        self.assertEqual(set(slot["completion_watch"].values()), {LOCATION_NAME_TO_ID[name] for name in names})
        self.assertTrue(set(slot["check_markers"]) <= set(slot["completion_watch"]))
        for name in world.removed_locations:
            self.assertNotIn(str(scm.completion_global(name)), slot["check_markers"])
        layout_names = [data.pickup_name(index) for index in range(data.PICKUP_COUNT)]
        layout_names += [data.shop_data.shop_item_name(data.SHOP_STAND_ITEMS[stand[6]])
                         for stand in data.SHOP_STAND_SLOTS]
        for name, row in zip(layout_names, slot["pickup_layout"], strict=True):
            self.assertEqual(row[6], scm.completion_global(name) if name in names else 0)
        for name in data.optional_check_classes()["shops"][1]:
            self.assertEqual(slot["config_globals"].get(str(scm.completion_global(name))),
                             1 if name in world.removed_locations else None)

    def test_fractional_percentages_round_up(self) -> None:
        for percentage, expected_pickups, expected_jumps in ((0, 0, 0), (1, 2, 1), (80, 93, 29), (100, 116, 36)):
            with self.subTest(percentage=percentage):
                generated = setup_multiworld(GTAViceCityWorld, options={
                    "enable_pickups": True,
                    "location_percentages": {"pickups": percentage, "stunt_jumps": percentage},
                })
                names = set(generated.worlds[1]._enabled_locations())
                classes = data.optional_check_classes()
                self.assertEqual(len(names.intersection(classes["pickups"][1])), expected_pickups)
                self.assertEqual(len(names.intersection(classes["stunt_jumps"][1])), expected_jumps)

    def test_tracker_replays_selection_on_a_different_seed(self) -> None:
        slot = json.loads(json.dumps(self.world.fill_slot_data()))
        tracker = setup_multiworld(GTAViceCityWorld, steps=(), seed=923)
        tracker.re_gen_passthrough = {self.game: GTAViceCityWorld.interpret_slot_data(slot)}
        for step in gen_steps:
            call_all(tracker, step)
        replay = tracker.worlds[1]
        self.assertEqual(replay.removed_locations, self.world.removed_locations)
        self.assertEqual(replay.options.location_percentages.value, self.options["location_percentages"])
        self.assertEqual(replay.options.milestone_spacing.value, self.options["milestone_spacing"])
        for field in ("completion_watch", "check_markers", "pickup_layout", "config_globals"):
            self.assertEqual(replay.fill_slot_data()[field], slot[field], field)

    def test_emergency_checks_keep_the_first_levels_of_each_activity(self) -> None:
        for percentage in (0, 1, 25, 50, 100):
            with self.subTest(percentage=percentage):
                generated = setup_multiworld(GTAViceCityWorld, options={
                    "location_percentages": {"emergency_vehicles": percentage},
                })
                world = generated.worlds[1]
                slot = world.fill_slot_data()
                for activity, levels in data.EMERGENCY_LEVELS.items():
                    last = percentage // 10 if activity == "Taxi" else ceil(levels * percentage / 100)
                    for level in range(1, levels + 1):
                        name = data.emergency_name(activity, level)
                        self.assertEqual(world._location_enabled(name), level <= last, name)
                        self.assertEqual(str(scm.completion_global(name)) in slot["completion_watch"],
                                         level <= last, name)

    def test_individual_emergency_percentages_override_the_fallback(self) -> None:
        percentages = {"emergency_vehicles": 50, "paramedic": 25, "vigilante": 100, "taxi": 0}
        for enabled in (False, True):
            generated = setup_multiworld(GTAViceCityWorld, options={
                "enable_emergency_vehicles": enabled, "location_percentages": percentages,
            })
            world = generated.worlds[1]
            for activity, levels in data.EMERGENCY_LEVELS.items():
                last = ceil(levels * percentages.get(activity.lower(), 50) / 100) if enabled else 0
                for level in range(1, levels + 1):
                    name = data.emergency_name(activity, level)
                    self.assertEqual(world._location_enabled(name), level <= last, name)
                    if not enabled:
                        self.assertNotIn(name, world.removed_locations)

    def test_zero_full_disabled_and_old_tracker_data(self) -> None:
        for percentage in (0, 100):
            with self.subTest(percentage=percentage):
                generated = setup_multiworld(GTAViceCityWorld, options={
                    "location_percentages": {"stunt_jumps": percentage, "pickups": 80},
                })
                world = generated.worlds[1]
                names = set(world._enabled_locations())
                self.assertEqual(len(names.intersection(data.optional_check_classes()["stunt_jumps"][1])),
                                 ceil(data.STUNT_JUMP_COUNT * percentage / 100))
                self.assertFalse(names.intersection(data.optional_check_classes()["pickups"][1]))
                self.assertFalse(world.removed_locations.intersection(data.optional_check_classes()["pickups"][1]))
        slot = self.world.fill_slot_data()
        del slot["location_percentages"]
        del slot["removed_locations"]
        del slot["milestone_spacing"]
        tracker = setup_multiworld(GTAViceCityWorld, steps=(), options=self.options)
        tracker.re_gen_passthrough = {self.game: slot}
        call_all(tracker, "generate_early")
        self.assertEqual(tracker.worlds[1].removed_locations, frozenset(data.EXTRA_TAXI_NAMES))
        self.assertEqual(tracker.worlds[1].options.location_percentages.value, {})
        self.assertEqual(tracker.worlds[1].fill_slot_data()["config_globals"]
                         [str(scm.TAXI_MILESTONE_SPACING_GLOBAL)], 10)

    def test_taxi_spacing_divides_the_reduced_fare_target_and_is_disabled_with_the_class(self) -> None:
        slot = self.world.fill_slot_data()
        self.assertEqual(slot["config_globals"][str(scm.TAXI_MILESTONE_SPACING_GLOBAL)], 5)
        self.assertEqual(sum(self.world._location_enabled(data.emergency_name("Taxi", level))
                             for level in range(1, 101)), 6)
        generated = setup_multiworld(GTAViceCityWorld, options={
            "enable_emergency_vehicles": False, "milestone_spacing": {"taxi": 5},
        })
        self.assertEqual(generated.worlds[1].fill_slot_data()["config_globals"]
                         [str(scm.TAXI_MILESTONE_SPACING_GLOBAL)], 10)

    def test_taxi_percentage_reduces_fares_before_spacing(self) -> None:
        for percentage, spacing, expected in ((10, 1, 10), (50, 5, 10), (100, 5, 20),
                                               (100, 1, 100), (10, 3, 3), (0, 1, 0)):
            with self.subTest(percentage=percentage, spacing=spacing):
                generated = setup_multiworld(GTAViceCityWorld, options={
                    "location_percentages": {"taxi": percentage}, "milestone_spacing": {"taxi": spacing},
                })
                world = generated.worlds[1]
                slot = world.fill_slot_data()
                for level in range(1, 101):
                    name = data.emergency_name("Taxi", level)
                    self.assertEqual(world._location_enabled(name), level <= expected)
                    self.assertEqual(str(scm.completion_global(name)) in slot["completion_watch"], level <= expected)
                distribute_items_restrictive(generated)
                self.assertTrue(generated.can_beat_game())
        self.assertEqual(scm.completion_global("Taxi Level 01"), 9309)
        self.assertEqual(scm.completion_global("Taxi Level 10"), 9318)
        self.assertEqual(scm.completion_global("Pizza Level 01"), 9319)
        self.assertEqual(scm.completion_global("Taxi Level 11"), 9550)
        self.assertEqual(scm.completion_global("Taxi Level 100"), 9639)

    def test_seed_determinism_and_fill_with_every_class_reduced(self) -> None:
        options = dict.fromkeys(CHECK_CLASS_OPTIONS, True)
        options["location_percentages"] = dict.fromkeys(LocationPercentages.valid_keys, 50)
        selections = []
        for seed in range(3):
            generated = setup_multiworld(GTAViceCityWorld, seed=seed, options=options)
            world = generated.worlds[1]
            selections.append(world.removed_locations)
            for key, (_, class_names) in data.optional_check_classes().items():
                default_count = len(class_names) - (90 if key == "emergency_vehicles" else 0)
                self.assertEqual(sum(world._location_enabled(name) for name in class_names), ceil(default_count / 2))
            distribute_items_restrictive(generated)
            self.assertTrue(generated.can_beat_game())
            self.assertEqual(len(generated.get_unfilled_locations()), 0)
        self.assertNotEqual(selections[0], selections[1])
        options["location_percentages"] = dict(reversed(list(options["location_percentages"].items())))
        repeated = setup_multiworld(GTAViceCityWorld, seed=0, options=options)
        self.assertEqual(selections[0], repeated.worlds[1].removed_locations)

    def test_validation_and_goal_constraints(self) -> None:
        for value in (0, -1, 101, 2.5, "5", True, None):
            with self.subTest(spacing=value), self.assertRaises(OptionError):
                MilestoneSpacing.from_any({"taxi": value})
        with self.assertRaises(OptionError):
            MilestoneSpacing.from_any({"pizza": 5})
        setup_multiworld(GTAViceCityWorld, options={
            "goal": "hundred_percent", "milestone_spacing": {"taxi": 5},
        })
        for key in ("pickups", "paramedic", "taxi"):
            for value in (-1, 101, 2.5, "50", True, None):
                with self.subTest(key=key, value=value), self.assertRaises(OptionError):
                    LocationPercentages.from_any({key: value})
        for key in ("stunt jump", "story_missions", 1):
            with self.subTest(key=key), self.assertRaises(OptionError):
                LocationPercentages.from_any({key: 50})
        with self.assertRaisesRegex(OptionError, "100 percent goal requires location_percentages"):
            setup_multiworld(GTAViceCityWorld, options={
                "goal": "hundred_percent", "location_percentages": {"stunt_jumps": 50},
            })
        setup_multiworld(GTAViceCityWorld, options={
            "goal": "hundred_percent", "enable_pickups": True, "shuffle_shops": True,
            "location_percentages": {"pickups": 0, "shops": 0},
        })
        with self.assertRaisesRegex(OptionError, "100 percent goal requires location_percentages"):
            setup_multiworld(GTAViceCityWorld, options={
                "goal": "hundred_percent", "location_percentages": {"paramedic": 50},
            })
        setup_multiworld(GTAViceCityWorld, options={
            "goal": "hundred_percent", "location_percentages": {
                "emergency_vehicles": 0, **dict.fromkeys((name.lower() for name in data.EMERGENCY_LEVELS), 100),
            },
        })
        with self.assertRaisesRegex(OptionError, "increase location_percentages"):
            setup_multiworld(GTAViceCityWorld, options={
                "location_percentages": dict.fromkeys(LocationPercentages.valid_keys, 0),
            })


class TestReducedItemPool(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "mission_shuffle": True,
        "location_percentages": {
            "firefighter": 0, "hidden_packages": 25, "paramedic": 0,
            "pickups": 25, "pizza": 0, "properties": 25, "rampages": 0,
            "robbable_stores": 0, "shops": 0, "side_events": 0,
            "stunt_jumps": 25, "taxi": 10, "vigilante": 0,
        },
        "milestone_spacing": {"taxi": 10},
        "content_locks": ["hidden_packages", "rampages", "stunt_jumps",
                          "properties", "robbable_stores", "pickups"],
        "split_content_locks": "per_district",
    }

    def test_reduced_pool_preserves_all_progression_and_fills(self) -> None:
        full = setup_multiworld(GTAViceCityWorld, options={**self.options, "location_percentages": {}})
        required = Counter(item.name for item in full.itempool if item.advancement)
        self.assertEqual(sum(required.values()), 84)
        self.assertEqual(sum(item.classification == ItemClassification.useful for item in full.itempool), 18)
        for seed in range(5):
            with self.subTest(seed=seed):
                generated = setup_multiworld(GTAViceCityWorld, options=self.options, seed=seed)
                self.assertEqual(len(generated.itempool), 89)
                self.assertEqual(Counter(item.name for item in generated.itempool if item.advancement), required)
                self.assertEqual(sum(item.classification == ItemClassification.useful
                                     for item in generated.itempool), 5)
                pool = Counter(item.name for item in generated.itempool)
                repeated = setup_multiworld(GTAViceCityWorld, options=self.options, seed=seed)
                self.assertEqual(Counter(item.name for item in repeated.itempool), pool)
                distribute_items_restrictive(generated)
                self.assertTrue(generated.can_beat_game())
                self.assertFalse(generated.get_unfilled_locations())

    def test_no_optional_items_when_progression_uses_every_check(self) -> None:
        generated = setup_multiworld(GTAViceCityWorld, options={
            **self.options,
            "location_percentages": {**self.options["location_percentages"], "hidden_packages": 20},
        })
        self.assertEqual(len(generated.itempool), 84)
        self.assertTrue(all(item.advancement for item in generated.itempool))
        distribute_items_restrictive(generated)
        self.assertTrue(generated.can_beat_game())
        self.assertFalse(generated.get_unfilled_locations())

    def test_excluded_checks_keep_filler_space(self) -> None:
        excluded = {data.FINAL_MISSION, "Rub Out"}
        generated = setup_multiworld(GTAViceCityWorld, options={**self.options, "exclude_locations": excluded})
        self.assertEqual(len(generated.itempool), 89)
        self.assertEqual(sum(item.advancement for item in generated.itempool), 84)
        self.assertEqual(sum(item.classification == ItemClassification.useful for item in generated.itempool), 3)
        exclusion_rules(generated, 1, excluded)
        distribute_items_restrictive(generated)
        for name in excluded:
            self.assertFalse(generated.get_location(name, 1).item.advancement)
            self.assertNotEqual(generated.get_location(name, 1).item.classification, ItemClassification.useful)
        self.assertTrue(generated.can_beat_game())
