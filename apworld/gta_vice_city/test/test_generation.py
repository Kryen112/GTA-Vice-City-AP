"""Generation and solvability tests for GTA: Vice City.

Run through scripts/run_tests.py, which links this world into a real
Archipelago checkout and invokes pytest.
"""

from __future__ import annotations

from typing import ClassVar

from Options import OptionError
from test.bases import WorldTestBase

from .. import data
from ..items import ITEM_NAME_TO_ID
from ..locations import LOCATION_NAME_TO_ID, PACKAGE_NAMES, STORY_MISSION_NAMES


class TestDefault(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    # Default options: final-mission goal, hidden packages on.


class TestHiddenPackagesGoal(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {"goal": "hidden_packages", "hidden_packages_required": 50}


class TestHundredPercentAllClasses(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    options: ClassVar[dict] = {
        "goal": "hundred_percent",
        "enable_hidden_packages": True,
        "enable_rampages_stunts": True,
        "enable_emergency_vehicles": True,
        "enable_properties": True,
        "enable_robbable_stores": True,
        "enable_side_events": True,
    }


_STORY_ONLY_OPTIONS: dict = {
    "enable_hidden_packages": False,
    "enable_rampages_stunts": False,
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
        # sphere 0, so the world grants the east-island spine strands at the
        # start to keep it fillable. The default reachability tests already
        # prove solvability; this asserts the world generated at all and left
        # the final mission as a real check.
        self.assertIn(
            data.FINAL_MISSION,
            {location.name for location in self.multiworld.get_locations(self.player)},
        )


class TestSpine(WorldTestBase):
    game = "Grand Theft Auto Vice City"

    def test_diaz_gated_behind_cortez(self) -> None:
        # The Chase is Diaz's first mission. Its rule needs the Cortez strand
        # complete (the spine edge) plus a Diaz unlock, so it is unreachable
        # with an empty inventory and reachable once those unlocks are held.
        self.assertFalse(self.can_reach_location("The Chase"))
        self.collect_by_name(["Progressive Cortez", "Progressive Diaz"])
        self.assertTrue(self.can_reach_location("The Chase"))

    def test_final_mission_requires_the_whole_spine(self) -> None:
        # Owning only the finale's own unlocks and mainland access is not
        # enough; the finale sits behind the entire main-story chain.
        self.collect_by_name(["Progressive Vercetti Finale", "Mainland Access"])
        self.assertFalse(self.can_reach_location(data.FINAL_MISSION))
        self.collect_by_name([
            "Progressive Rosenberg", "Progressive Cortez", "Progressive Diaz",
            "Progressive Death Row", "Progressive Vercetti Protection",
        ])
        self.assertTrue(self.can_reach_location(data.FINAL_MISSION))


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
        self.assertEqual(len(classes["rampages_stunts"][1]), 71)
        self.assertEqual(len(classes["emergency_vehicles"][1]), 56)
        self.assertEqual(len(classes["side_events"][1]), 14)


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
