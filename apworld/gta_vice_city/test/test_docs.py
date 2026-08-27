"""The pages a WebHost serves for this world, against what it asks of them.

Archipelago's own test/webhost/test_docs.py checks these for worlds inside its
repository. A world that ships as an apworld is never in that run, so the same
guarantees are made here: a tutorial whose file exists, a game info page named
for the game, and both of them actually inside the package.

The fourth test is this world's own. The info page names each check class with
its size, and a number written by hand in prose is a number that goes wrong the
first time a class changes, so the table is parsed and compared against the
location tables.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from Options import PerGameCommonOptions
from Utils import local_path, read_apignore
from werkzeug.utils import secure_filename

from .. import GTAViceCityWorld
from ..locations import LOCATION_CLASS
from ..options import CHECK_CLASS_OPTIONS, GTAViceCityOptions

WORLD_PACKAGE = Path(__file__).resolve().parent.parent
DOCS = WORLD_PACKAGE / "docs"
INFO_PAGE = DOCS / f"en_{GTAViceCityWorld.game}.md"

# The label each row of the info page's table carries, and the check class it
# reports on. Written out rather than derived from the class keys: the page is
# for players, so it says "Unique stunt jumps" where the world says
# "stunt_jumps", and the mapping is the only place those two spellings meet.
TABLE_ROW_CLASSES: dict[str, str] = {
    "Story missions": "story_missions",
    "Hidden packages": "hidden_packages",
    "Rampages": "rampages",
    "Unique stunt jumps": "stunt_jumps",
    "Emergency vehicle milestones": "emergency_vehicles",
    "Properties and venue missions": "properties",
    "Robbable stores": "robbable_stores",
    "Side events": "side_events",
    "Ambient pickups": "pickups",
    "Shop items": "shops",
}

TABLE_ROW = re.compile(r"^\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<count>\d+)\s*\|$")


def _class_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for class_key in LOCATION_CLASS.values():
        counts[class_key] = counts.get(class_key, 0) + 1
    return counts


def _page_counts() -> dict[str, int]:
    """The check counts the info page publishes, by check class key."""
    counts: dict[str, int] = {}
    for line in INFO_PAGE.read_text(encoding="utf-8").splitlines():
        match = TABLE_ROW.match(line)
        if match is None:
            continue
        label = match.group("label")
        if label in TABLE_ROW_CLASSES:
            counts[TABLE_ROW_CLASSES[label]] = int(match.group("count"))
    return counts


class TestDocs(unittest.TestCase):
    def test_every_tutorial_names_a_file_that_exists(self) -> None:
        # The WebHost copies each tutorial file out of the apworld by name and
        # links to it whether or not it arrived, so a typo here is a dead page
        # rather than an error anybody sees.
        tutorials = GTAViceCityWorld.web.tutorials
        self.assertTrue(tutorials, "the world offers no setup tutorial")
        for tutorial in tutorials:
            with self.subTest(tutorial.file_name):
                self.assertTrue((DOCS / tutorial.file_name).is_file())

    def test_the_game_info_page_is_named_for_the_game(self) -> None:
        # The WebHost sanitizes the file name on the way in and then looks for
        # the sanitized game name, so those two have to agree. They do not when
        # the page is named by hand with underscores, or when the game is
        # renamed and the page is not.
        for language in GTAViceCityWorld.web.game_info_languages:
            with self.subTest(language):
                page = DOCS / f"{language}_{GTAViceCityWorld.game}.md"
                self.assertTrue(page.is_file(), f"no {page.name}")
                self.assertEqual(
                    secure_filename(page.name),
                    f"{language}_{secure_filename(GTAViceCityWorld.game)}.md")

    def test_the_docs_are_inside_the_packaged_apworld(self) -> None:
        # Asked of the real packaging rules rather than of the file system: the
        # build component lists what it packages through the global apignore
        # plus this world's own, so a pattern added to either that swallows the
        # docs would leave a released world with no pages and nothing else would
        # notice.
        ignores = read_apignore(local_path("data", "GLOBAL.apignore"))
        self.assertIsNotNone(ignores, "no global apignore to read")
        local_ignores = read_apignore(WORLD_PACKAGE / ".apignore")
        if local_ignores:
            ignores = ignores + local_ignores
        packaged = {Path(name).as_posix()
                    for name in ignores.match_tree_files(WORLD_PACKAGE, negate=True)}
        for page in sorted(DOCS.iterdir()):
            with self.subTest(page.name):
                self.assertIn(f"docs/{page.name}", packaged)

    def test_the_info_page_counts_match_the_location_tables(self) -> None:
        # The page tells a player how big each class is, which is a promise the
        # tables have to keep. Every class needs a row, so a class added later
        # fails here rather than going unmentioned on the page that lists them.
        self.assertEqual(_page_counts(), _class_counts())

    def test_the_info_page_total_matches_its_own_rows(self) -> None:
        # The total is written out in prose under the table, so it is the one
        # number on the page the row check cannot reach.
        total = sum(_class_counts().values())
        self.assertIn(f"that is {total} checks",
                      INFO_PAGE.read_text(encoding="utf-8"))

    def test_every_option_is_in_exactly_one_group(self) -> None:
        # An option added to the dataclass and to no group lands in Archipelago's
        # default bucket, silently, on the page where a player decides what to
        # turn on. The world's own options are the ones this world places; the
        # common ones Archipelago groups itself.
        common = set(PerGameCommonOptions.type_hints)
        placed: list[type] = [option
                              for group in GTAViceCityWorld.web.option_groups
                              for option in group.options]
        self.assertEqual(len(placed), len(set(placed)), "an option is in two groups")
        ours = {option for name, option in GTAViceCityOptions.type_hints.items()
                if name not in common}
        self.assertEqual(ours - set(placed), set(), "these options are in no group")

    def test_the_check_class_group_is_the_check_classes(self) -> None:
        # The group a player reads as "what can be a check" has to be the list
        # the world actually treats as check classes, or the page teaches the
        # wrong shape of the seed.
        grouped = next(group for group in GTAViceCityWorld.web.option_groups
                       if group.name == "Check Classes")
        expected = {GTAViceCityOptions.type_hints[name]
                    for name in CHECK_CLASS_OPTIONS}
        self.assertEqual(set(grouped.options), expected)
