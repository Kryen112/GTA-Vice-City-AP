"""The id tables and the reserved SCM globals against the snapshot that
freezes them.

Ids are derived, name by name in registry order from a base, so inserting a
location anywhere but the end renumbers every location after it and nothing in
the world notices. Once a seed exists, ids are the only names it and its tracker
have for a check: renumbering breaks a session that is already being played, and
no fix reaches the people playing it.

The reserved SCM globals are the same shape and a harder failure. scm.py numbers
each block from a list's order, and those numbers are compiled into main.scm and
the CLEO scripts and written into saves, so a global that moves points a running
save at the wrong word. That one breaks a seed in progress whether or not
anything has been released.

Two phases, decided by the snapshot's own `released` flag.

Before release the snapshot is a mirror and this asks for an exact match, so a
reorder nobody meant fails here and a reorder somebody meant is one run of
scripts/freeze_numbering.py. After release it is a floor: every id already in it must
still be exactly where it was, and a name added at the very end may take the
next id up.

"At the very end" is the whole allowance, and it is narrower than it sounds.
Each table is its category lists concatenated, so a new trap or a tenth radio
station lands in the middle of one and shifts everything after it, which this
refuses. After release, a new name that is not a tail append means a new
category at the end of the registry, or a new apworld release.

The comparison is a function over two plain mappings rather than a method, so
the phases can be driven from synthetic snapshots below. Otherwise the released
half would first run on the day it is the only thing standing between a table
edit and every seed in the world.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ..items import ID_BASE as ITEM_ID_BASE
from ..items import ITEM_NAME_TO_ID
from ..locations import ID_BASE as LOCATION_ID_BASE
from ..locations import LOCATION_NAME_TO_ID
from ..scm import reserved_global_map

SNAPSHOT_PATH = Path(__file__).resolve().parent / "frozen_numbering.json"
REGENERATE = "python scripts/freeze_numbering.py"
KINDS = ("items", "locations", "scm_globals")


def snapshot_faults(snapshot: object) -> list[str]:
    """Every way the snapshot itself is not usable as a freeze.

    Checked before it is believed, because each of these makes the freeze pass
    while enforcing nothing: a released flag that is a string is true, and an
    empty table freezes no id at all.
    """
    faults = []
    if not isinstance(snapshot, dict):
        return ["the snapshot is not an object"]
    if not isinstance(snapshot.get("released"), bool):
        faults.append("released is not true or false, so the phase is a guess")
    faults.extend(f"{field} is missing or is not a number"
                  for field in ("item_id_base", "location_id_base")
                  if not isinstance(snapshot.get(field), int))
    for kind in KINDS:
        table = snapshot.get(kind)
        if not isinstance(table, dict) or not table:
            faults.append(f"{kind} is missing or empty, so it freezes nothing")
        elif not all(isinstance(value, int) for value in table.values()):
            faults.append(f"{kind} holds an id that is not a number")
    return faults


def freeze_violations(snapshot: dict, tables: dict[str, dict[str, int]],
                      bases: dict[str, int]) -> list[str]:
    """Everything the tables do that the snapshot forbids, in the phase it is in.

    Both phases forbid a frozen id moving, a frozen name leaving, a base moving,
    and a new name landing on an id the snapshot already gave away. Only the
    unreleased phase also forbids new names, since before release the snapshot
    is meant to mirror the tables exactly.
    """
    violations = []
    for field, base in bases.items():
        if snapshot[field] != base:
            violations.append(f"{field} was {snapshot[field]}, now {base}")
    for kind in KINDS:
        frozen = snapshot[kind]
        current = tables[kind]
        holder = {identifier: name for name, identifier in frozen.items()}
        for name, identifier in frozen.items():
            if name not in current:
                violations.append(
                    f"{kind}: {name!r} left the table, taking id {identifier}")
            elif current[name] != identifier:
                violations.append(
                    f"{kind}: {name!r} moved from {identifier} to {current[name]}")
        for name, identifier in current.items():
            if name in frozen:
                continue
            if identifier in holder:
                violations.append(
                    f"{kind}: new {name!r} took id {identifier}, which the "
                    f"snapshot gave to {holder[identifier]!r}")
            elif not snapshot["released"]:
                violations.append(f"{kind}: {name!r} is not in the snapshot")
    return violations


def _current() -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    return ({"items": dict(ITEM_NAME_TO_ID),
             "locations": dict(LOCATION_NAME_TO_ID),
             "scm_globals": reserved_global_map()},
            {"item_id_base": ITEM_ID_BASE, "location_id_base": LOCATION_ID_BASE})


class TestNumberingFreeze(unittest.TestCase):
    """The tables this repository actually ships, against the real snapshot."""

    def setUp(self) -> None:
        self.assertTrue(
            SNAPSHOT_PATH.is_file(),
            f"no numbering snapshot at {SNAPSHOT_PATH.name}. It is checked in, so its "
            f"absence is a deletion, not a first run. Restore it, or write the "
            f"first one with {REGENERATE} --first-run.")
        try:
            self.snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            self.fail(f"{SNAPSHOT_PATH.name} does not read as json ({error}). "
                      f"Restore it, or rewrite it with {REGENERATE}.")

    def test_the_snapshot_is_usable_as_a_freeze(self) -> None:
        self.assertEqual(snapshot_faults(self.snapshot), [])

    def test_the_tables_agree_with_the_snapshot(self) -> None:
        tables, bases = _current()
        violations = freeze_violations(self.snapshot, tables, bases)
        if not violations:
            return
        shown = "\n  ".join(violations[:10])
        more = f"\n  and {len(violations) - 10} more" if len(violations) > 10 else ""
        after = ("These ids are RELEASED. Every seed and tracker already playing "
                 "reads them, so put the tables back and append instead."
                 if self.snapshot["released"] else
                 f"These ids are not frozen yet, so this is only asking you to "
                 f"mean it: {REGENERATE}.")
        self.fail(f"{len(violations)} against the snapshot:\n  {shown}{more}\n{after}")


class TestFreezePhases(unittest.TestCase):
    """The two phases, driven from snapshots made here.

    The released half of this cannot be exercised by the real snapshot until the
    day it is released, which is the day it has to already work.
    """

    def setUp(self) -> None:
        self.tables = {"items": {"Sprint": 10, "Jump": 11},
                       "locations": {"An Old Friend": 20, "The Party": 21},
                       "scm_globals": {"base:UNLOCK_BASE": 9010,
                                       "unlock:Rosenberg": 9010}}
        self.bases = {"item_id_base": 10, "location_id_base": 20}
        self.snapshot = {"released": False,
                         "item_id_base": 10, "location_id_base": 20,
                         "items": dict(self.tables["items"]),
                         "locations": dict(self.tables["locations"]),
                         "scm_globals": dict(self.tables["scm_globals"])}

    def _violations(self) -> list[str]:
        return freeze_violations(self.snapshot, self.tables, self.bases)

    def test_matching_tables_are_clean_in_both_phases(self) -> None:
        for released in (False, True):
            with self.subTest(released=released):
                self.snapshot["released"] = released
                self.assertEqual(self._violations(), [])

    def test_a_tail_append_passes_only_after_release(self) -> None:
        self.tables["locations"]["A New Check"] = 22
        self.snapshot["released"] = True
        self.assertEqual(self._violations(), [])
        # Before release the snapshot mirrors the tables, so the same addition
        # is drift until somebody regenerates it.
        self.snapshot["released"] = False
        self.assertEqual(len(self._violations()), 1)

    def test_an_insert_fails_after_release(self) -> None:
        # What a new name in the middle of a category does: it takes an id that
        # is already somebody's and pushes every name after it up one.
        self.tables["locations"] = {"An Old Friend": 20, "A New Check": 21,
                                    "The Party": 22}
        self.snapshot["released"] = True
        violations = self._violations()
        self.assertEqual(len(violations), 2, violations)
        self.assertTrue(any("moved from 21 to 22" in line for line in violations))
        self.assertTrue(any("took id 21" in line for line in violations))

    def test_a_removal_fails_after_release(self) -> None:
        del self.tables["items"]["Jump"]
        self.snapshot["released"] = True
        self.assertEqual(self._violations(), ["items: 'Jump' left the table, taking id 11"])

    def test_a_rename_fails_after_release(self) -> None:
        # A rename is a removal and an addition on one id, which is exactly what
        # a tracker cannot follow. Deliberately not accommodated: renaming means
        # a new apworld release.
        self.tables["locations"] = {"An Old Friend": 20, "The Gathering": 21}
        self.snapshot["released"] = True
        self.assertEqual(len(self._violations()), 2)

    def test_a_base_moving_fails_after_release(self) -> None:
        self.bases["location_id_base"] = 2000
        self.tables["locations"] = {"An Old Friend": 2000, "The Party": 2001}
        self.snapshot["released"] = True
        violations = self._violations()
        self.assertTrue(any("location_id_base was 20, now 2000" in line
                            for line in violations))

    def test_a_new_global_above_the_top_is_refused_after_release(self) -> None:
        # The globals have no tail to append to. One added above the highest
        # moves base:highest_reserved_global, which is frozen on purpose since
        # add_markers.py sizes the marker scratch from it, so main.scm is built
        # against where the block ends.
        self.snapshot["released"] = True
        self.snapshot["scm_globals"]["base:highest_reserved_global"] = 9669
        self.tables["scm_globals"]["base:highest_reserved_global"] = 9669
        self.assertEqual(self._violations(), [])
        self.tables["scm_globals"]["base:something_new"] = 9670
        self.tables["scm_globals"]["base:highest_reserved_global"] = 9670
        self.assertEqual(
            self._violations(),
            ["scm_globals: 'base:highest_reserved_global' moved from 9669 to 9670"])

    def test_two_names_on_one_global_are_not_a_collision(self) -> None:
        # Every block's base shares its number with that block's first entry,
        # and thirteen pairs do it. They are the same global under two names,
        # not two globals fighting, so the freeze must not read the pair as a
        # new name stealing a frozen id.
        self.snapshot["released"] = True
        self.assertEqual(self.snapshot["scm_globals"]["base:UNLOCK_BASE"],
                         self.snapshot["scm_globals"]["unlock:Rosenberg"])
        self.assertEqual(self._violations(), [])

    def test_an_unusable_snapshot_is_named(self) -> None:
        for field, value, said in (
            ("released", "false", "released is not"),
            ("items", {}, "items is missing or empty"),
            ("locations", None, "locations is missing or empty"),
            ("item_id_base", "10", "item_id_base is missing"),
        ):
            with self.subTest(field):
                snapshot = dict(self.snapshot)
                snapshot[field] = value
                faults = snapshot_faults(snapshot)
                self.assertTrue(any(said in fault for fault in faults), faults)

    def test_an_empty_released_snapshot_is_refused_rather_than_passing(self) -> None:
        # The vacuous pass: released, with nothing in it, forbids nothing. It has
        # to be caught by the shape check, because the comparison would be clean.
        empty = {"released": True, "item_id_base": 10, "location_id_base": 20,
                 "items": {}, "locations": {}}
        self.assertNotEqual(snapshot_faults(empty), [])
