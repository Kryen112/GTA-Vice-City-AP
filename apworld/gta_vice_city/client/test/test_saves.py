"""Tests for per-seed save isolation, on temporary folders with fake saves.

These never touch a real GTA Vice City User Files folder; each test builds its
own directory and fake .b save files.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from .. import saves
from ..saves import SaveManager


def _touch(path: Path) -> None:
    path.write_text("save", encoding="utf-8")


class TestSeedFolderName(unittest.TestCase):
    def test_sanitizes_to_a_safe_name(self) -> None:
        self.assertEqual(saves.seed_folder_name("A B/c:d"), "A_B_c_d")
        self.assertEqual(saves.seed_folder_name(""), "unnamed")


class TestSaveManager(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.user_files = Path(self._tmp.name)
        self.manager = SaveManager(self.user_files)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _live_saves(self) -> list[str]:
        return sorted(path.name for path in self.user_files.glob("*.b"))

    def test_first_isolation_stashes_normal_saves_and_starts_fresh(self) -> None:
        _touch(self.user_files / "GTAVC1.b")
        _touch(self.user_files / "GTAVC2.b")
        (self.user_files / "gta_vc.set").write_text("settings", encoding="utf-8")
        result = self.manager.isolate("Seed One")
        self.assertIn("fresh", result.lower())
        self.assertEqual(self._live_saves(), [])  # a new seed starts with no saves
        self.assertEqual(
            sorted(path.name for path in self.manager.career.glob("*.b")),
            ["GTAVC1.b", "GTAVC2.b"])
        self.assertTrue((self.user_files / "gta_vc.set").is_file())  # settings untouched
        self.assertTrue(self.manager.is_isolated())
        self.assertEqual(self.manager.active_seed(), "Seed_One")

    def test_resume_brings_back_the_seed_saves(self) -> None:
        _touch(self.user_files / "GTAVC1.b")  # a normal save
        self.manager.isolate("seed_a")        # stash normal, start a fresh
        _touch(self.user_files / "GTAVC3.b")  # a save made while playing seed a
        self.manager.isolate("seed_b")        # persist a, start b fresh
        self.assertEqual(self._live_saves(), [])
        result = self.manager.isolate("seed_a")  # switch back to a
        self.assertIn("resumed", result.lower())
        self.assertEqual(self._live_saves(), ["GTAVC3.b"])

    def test_restore_returns_the_normal_saves(self) -> None:
        _touch(self.user_files / "GTAVC1.b")
        self.manager.isolate("seed_a")
        _touch(self.user_files / "GTAVC3.b")  # a seed save
        result = self.manager.restore()
        self.assertIn("restored", result.lower())
        self.assertEqual(self._live_saves(), ["GTAVC1.b"])  # normal saves are back
        self.assertFalse(self.manager.is_isolated())
        self.assertEqual(  # the seed save was persisted, not lost
            sorted(path.name for path in self.manager._seed_dir("seed_a").glob("*.b")),
            ["GTAVC3.b"])

    def test_already_on_seed_is_idempotent(self) -> None:
        _touch(self.user_files / "GTAVC1.b")
        self.manager.isolate("seed_a")
        result = self.manager.isolate("seed_a")
        self.assertIn("already", result.lower())

    def test_refuses_to_overwrite_a_populated_career(self) -> None:
        _touch(self.user_files / "GTAVC1.b")
        self.manager.career.mkdir()
        _touch(self.manager.career / "GTAVC9.b")  # a stray stash with no state
        with self.assertRaises(RuntimeError):
            self.manager.isolate("seed_a")

    def test_restore_with_nothing_stashed_is_a_noop(self) -> None:
        result = self.manager.restore()
        self.assertIn("already in place", result.lower())

    def test_switch_refuses_to_overwrite_a_populated_seed_folder(self) -> None:
        _touch(self.user_files / "GTAVC1.b")
        self.manager.isolate("seed_a")        # active seed_a, live empty
        _touch(self.user_files / "GTAVC3.b")  # a live save under seed_a
        stray = self.manager._seed_dir("seed_a")
        stray.mkdir(parents=True)
        _touch(stray / "GTAVC5.b")            # a stale seed_a stash
        with self.assertRaises(RuntimeError):
            self.manager.isolate("seed_b")    # cannot persist seed_a over the stash

    def test_restore_refuses_when_no_active_seed_is_recorded(self) -> None:
        _touch(self.user_files / "GTAVC1.b")
        self.manager._write_state(True, None)  # stashed, but no active seed
        with self.assertRaises(RuntimeError):
            self.manager.restore()

    def test_discard_refuses_while_the_career_is_stashed(self) -> None:
        _touch(self.user_files / "GTAVC1.b")
        self.manager.isolate("seed_a")
        note = self.manager.discard_isolation_state()
        self.assertIn("stashed", note.lower())
        self.assertTrue(self.manager.state_path.is_file())
        self.assertTrue(self.manager.is_isolated())

    def test_discard_removes_the_bookkeeping_and_empty_folders(self) -> None:
        _touch(self.user_files / "GTAVC1.b")
        self.manager.isolate("seed_a")
        self.manager.restore()
        note = self.manager.discard_isolation_state()
        self.assertIsNone(note)
        self.assertFalse(self.manager.career.exists())
        self.assertFalse(self.manager.state_path.exists())
        self.assertEqual(self._live_saves(), ["GTAVC1.b"])  # normal saves untouched

    def test_discard_keeps_seed_saves_with_a_note(self) -> None:
        _touch(self.user_files / "GTAVC1.b")
        self.manager.isolate("seed_a")
        _touch(self.user_files / "GTAVC3.b")  # a save made while playing the seed
        self.manager.restore()                # persists it under AP_Seeds/seed_a
        note = self.manager.discard_isolation_state()
        self.assertIn("seed saves are kept", note.lower())
        self.assertTrue((self.manager._seed_dir("seed_a") / "GTAVC3.b").is_file())
        self.assertFalse(self.manager.state_path.exists())

    def test_discard_drops_seed_folders_emptied_by_a_resume(self) -> None:
        _touch(self.user_files / "GTAVC1.b")
        self.manager.isolate("seed_a")
        self.manager.restore()
        (self.manager.seeds_root / "seed_a").mkdir(parents=True)  # left by a resume
        note = self.manager.discard_isolation_state()
        self.assertIsNone(note)
        self.assertFalse(self.manager.seeds_root.exists())

    def test_discard_with_no_bookkeeping_is_a_noop(self) -> None:
        self.assertIsNone(self.manager.discard_isolation_state())


if __name__ == "__main__":
    unittest.main()
