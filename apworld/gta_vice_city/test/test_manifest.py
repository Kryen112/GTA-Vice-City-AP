"""The apworld manifest, against what the format asks of it.

Archipelago's Build APWorlds component carries these fields into the packaged
apworld untouched and adds only the container versions, so a field wrong here is
a field wrong in every apworld this repository ships.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from Utils import tuplize_version, version_tuple

from .. import GTAViceCityWorld

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "archipelago.json"


class TestManifest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_the_game_matches_the_world(self) -> None:
        # The component is handed the manifest's game name and packages
        # whatever the registry holds under it, so a rename on one side leaves
        # it with nothing to build. This is where that is caught, at test time;
        # the build itself sees only an archive that was never written.
        self.assertEqual(self.manifest["game"], GTAViceCityWorld.game)

    def test_the_world_version_is_three_numbers(self) -> None:
        # The format is exact about the shape. A core that cannot read it treats
        # the world as unversioned, which sorts it below every versioned copy of
        # itself, so a player with two installed gets the other one.
        parts = self.manifest["world_version"].split(".")
        self.assertEqual(len(parts), 3, "world_version is major.minor.build")
        for part in parts:
            self.assertTrue(part.isdigit(), f"{part} in world_version is not a number")

    def test_the_core_floor_is_one_this_world_runs_on(self) -> None:
        # A floor above the checkout the tests run against refuses to load in the
        # very core that just proved the world works.
        self.assertLessEqual(
            tuplize_version(self.manifest["minimum_ap_version"]), version_tuple)

    def test_the_container_versions_are_left_to_the_packager(self) -> None:
        # The format forbids both in a world's own manifest, and the component
        # writes them itself. A copy here freezes the container format at
        # whatever it was the day someone typed it.
        self.assertNotIn("version", self.manifest)
        self.assertNotIn("compatible_version", self.manifest)
