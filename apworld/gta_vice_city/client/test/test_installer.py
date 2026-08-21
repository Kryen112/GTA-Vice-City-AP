"""Tests for the mod installer, on a temporary install with a fake payload.

Each test passes an explicit payload, so the real bundled payload (staged by
the build once the mod compiles) never matters here. Covers deploy, backup,
idempotency, the no-payload path, the removal manifest, remove, and the text
table patch that carries the pause menu's Archipelago label.

The text tables here are built by build_text_table, not copied from a game: the
structure is the game's (a TABL of table offsets, then per-table TKEY records
sorted by key and TDAT text in UTF-16) and that is what the patch has to keep
true.
"""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from ... import installer

ASI = ("GtaVcAp.VC.asi", b"asi-bytes")
SCM = ("main.scm", b"scm-bytes")
CLEO = ("cleo/gtavc_ap.cs", b"cleo-bytes")
PAYLOAD = [ASI, CLEO, SCM]


def build_text_table(tables: dict[str, dict[str, str]]) -> bytes:
    """A Vice City text table file carrying the given tables. MAIN comes first
    and opens with its TKEY chunk; every other table is preceded by its name,
    the way the game's own files are laid out."""
    names = ["MAIN", *sorted(name for name in tables if name != "MAIN")]
    bodies: list[bytes] = []
    for name in names:
        entries = sorted(tables[name].items())
        text_body = b""
        keys = b""
        for key, value in entries:
            keys += struct.pack("<I", len(text_body)) + key.encode().ljust(8, b"\x00")
            text_body += value.encode("utf-16-le") + b"\x00\x00"
        body = b"" if name == "MAIN" else name.encode().ljust(8, b"\x00")
        body += b"TKEY" + struct.pack("<I", len(keys)) + keys
        body += b"TDAT" + struct.pack("<I", len(text_body)) + text_body
        bodies.append(body)
    header = b"TABL" + struct.pack("<I", 12 * len(names))
    offset = len(header) + 12 * len(names)
    records = b""
    for name, body in zip(names, bodies, strict=True):
        records += name.encode().ljust(8, b"\x00") + struct.pack("<I", offset)
        offset += len(body)
    return header + records + b"".join(bodies)


VANILLA_TABLE = build_text_table({
    "MAIN": {"AMMU": "Ammu-Nation", "APR": "April", "FEP_QUI": "Quit Game",
             "ZEBRA": "Zebra"},
    "ASSIN1": {"ASM1_A": "Kill them all."},
})


class TestDestination(unittest.TestCase):
    def test_maps_each_file_to_its_place(self) -> None:
        root = Path("C:/game")
        self.assertEqual(installer._destination(root, "GtaVcAp.VC.asi"), root / "GtaVcAp.VC.asi")
        self.assertEqual(installer._destination(root, "cleo/gtavc_ap.cs"), root / "CLEO" / "gtavc_ap.cs")
        self.assertEqual(installer._destination(root, "main.scm"), root / "data" / "main.scm")


class TestDeploy(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.install = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_deploys_every_file_to_its_place(self) -> None:
        log = installer.deploy(self.install, payload=PAYLOAD)
        self.assertEqual((self.install / "GtaVcAp.VC.asi").read_bytes(), b"asi-bytes")
        self.assertEqual((self.install / "CLEO" / "gtavc_ap.cs").read_bytes(), b"cleo-bytes")
        self.assertEqual((self.install / "data" / "main.scm").read_bytes(), b"scm-bytes")
        self.assertEqual(len(log), 3)

    def test_clears_a_copy_an_earlier_build_left_in_scripts(self) -> None:
        # The ASI loader scans the install root and scripts alike, so a copy an
        # earlier build left in scripts runs as a second instance beside the
        # current one. Deploy takes it out, and says so.
        stale = self.install / "scripts" / "GtaVcAp.VC.asi"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"an-older-build")
        log = installer.deploy(self.install, payload=PAYLOAD)
        self.assertFalse(stale.exists())
        self.assertEqual((self.install / "GtaVcAp.VC.asi").read_bytes(), b"asi-bytes")
        self.assertTrue(any("scripts/GtaVcAp.VC.asi" in line for line in log))

    def test_leaves_other_files_in_scripts_alone(self) -> None:
        # Only the paths this mod itself used to occupy are cleared; the folder
        # belongs to the player and may hold anything else.
        other = self.install / "scripts" / "SomeOtherMod.asi"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"not-ours")
        installer.deploy(self.install, payload=PAYLOAD)
        self.assertEqual(other.read_bytes(), b"not-ours")

    def test_a_stale_copy_makes_the_install_not_current(self) -> None:
        # The client skips deploy while the mod reads as current, so a stale copy
        # has to make it read stale or the duplicate would never be cleaned.
        installer.deploy(self.install, payload=PAYLOAD)
        self.assertTrue(installer.mod_is_current(self.install, payload=PAYLOAD))
        stale = self.install / "scripts" / "GtaVcAp.VC.asi"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"an-older-build")
        self.assertFalse(installer.mod_is_current(self.install, payload=PAYLOAD))

    def test_backs_up_a_replaced_stock_file(self) -> None:
        stock = self.install / "data" / "main.scm"
        stock.parent.mkdir(parents=True)
        stock.write_bytes(b"stock-scm")
        installer.deploy(self.install, payload=[SCM])
        self.assertEqual(stock.read_bytes(), b"scm-bytes")  # replaced
        self.assertEqual(
            (self.install / "AP_mod_backup" / "main.scm").read_bytes(), b"stock-scm")

    def test_is_idempotent(self) -> None:
        installer.deploy(self.install, payload=PAYLOAD)
        log = installer.deploy(self.install, payload=PAYLOAD)
        self.assertEqual(log, ["The mod is already up to date."])

    def test_mod_is_current_tracks_the_payload(self) -> None:
        self.assertFalse(installer.mod_is_current(self.install, payload=PAYLOAD))
        installer.deploy(self.install, payload=PAYLOAD)
        self.assertTrue(installer.mod_is_current(self.install, payload=PAYLOAD))

    def test_no_payload_is_a_noop(self) -> None:
        self.assertTrue(installer.mod_is_current(self.install, payload=[]))
        with self.assertRaises(FileNotFoundError):
            installer.deploy(self.install, payload=[])


class TestUnlistedPayloadPaths(unittest.TestCase):
    def test_accepts_every_shipped_name_and_main_scm(self) -> None:
        staged = [*installer.SHIPPED_PAYLOAD_PATHS, "main.scm"]
        self.assertEqual(installer.unlisted_payload_paths(staged), [])

    def test_flags_a_file_missing_from_the_manifest(self) -> None:
        staged = ["GtaVcAp.VC.asi", "cleo/new_script.cs", "main.scm"]
        self.assertEqual(installer.unlisted_payload_paths(staged), ["cleo/new_script.cs"])


class TestRemove(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.install = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_removes_deployed_files_and_restores_the_stock_scm(self) -> None:
        stock = self.install / "data" / "main.scm"
        stock.parent.mkdir(parents=True)
        stock.write_bytes(b"stock-scm")
        installer.deploy(self.install, payload=PAYLOAD)
        log = installer.remove(self.install, payload=PAYLOAD)
        self.assertFalse((self.install / "GtaVcAp.VC.asi").exists())
        self.assertFalse((self.install / "CLEO" / "gtavc_ap.cs").exists())
        self.assertEqual(stock.read_bytes(), b"stock-scm")
        self.assertFalse((self.install / "AP_mod_backup").exists())
        self.assertTrue(log)

    def test_is_idempotent(self) -> None:
        stock = self.install / "data" / "main.scm"
        stock.parent.mkdir(parents=True)
        stock.write_bytes(b"stock-scm")
        installer.deploy(self.install, payload=PAYLOAD)
        installer.remove(self.install, payload=PAYLOAD)
        self.assertEqual(installer.remove(self.install, payload=PAYLOAD), [])

    def test_stock_install_returns_no_log(self) -> None:
        self.assertEqual(installer.remove(self.install, payload=PAYLOAD), [])

    def test_removes_shipped_names_without_a_payload(self) -> None:
        # An apworld packaged without a mod still cleans up a modded install,
        # by the fixed list of every file a payload has ever deployed.
        for relative_path in installer.SHIPPED_PAYLOAD_PATHS:
            destination = installer._destination(self.install, relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"mod-bytes")
        log = installer.remove(self.install, payload=[])
        for relative_path in installer.SHIPPED_PAYLOAD_PATHS:
            self.assertFalse(installer._destination(self.install, relative_path).exists())
        self.assertTrue(log)

    def test_leaves_a_player_authored_scm_and_keeps_the_backup(self) -> None:
        stock = self.install / "data" / "main.scm"
        stock.parent.mkdir(parents=True)
        stock.write_bytes(b"stock-scm")
        installer.deploy(self.install, payload=[SCM])
        stock.write_bytes(b"player-scm")  # the player replaced it after deploy
        log = installer.remove(self.install, payload=[SCM])
        self.assertEqual(stock.read_bytes(), b"player-scm")
        self.assertEqual(
            (self.install / "AP_mod_backup" / "main.scm").read_bytes(), b"stock-scm")
        self.assertTrue(any("left alone" in line for line in log))

    def test_keeps_stray_files_in_the_backup_folder(self) -> None:
        stock = self.install / "data" / "main.scm"
        stock.parent.mkdir(parents=True)
        stock.write_bytes(b"stock-scm")
        installer.deploy(self.install, payload=[SCM])
        stray = self.install / "AP_mod_backup" / "players_own_note.txt"
        stray.write_bytes(b"stray-bytes")
        installer.remove(self.install, payload=[SCM])
        self.assertEqual(stock.read_bytes(), b"stock-scm")
        self.assertFalse((self.install / "AP_mod_backup" / "main.scm").exists())
        self.assertEqual(stray.read_bytes(), b"stray-bytes")  # never swept along

    def test_already_stock_scm_only_cleans_the_backup(self) -> None:
        backup = self.install / "AP_mod_backup" / "main.scm"
        backup.parent.mkdir(parents=True)
        backup.write_bytes(b"stock-scm")
        stock = self.install / "data" / "main.scm"
        stock.parent.mkdir(parents=True)
        stock.write_bytes(b"stock-scm")  # already restored by hand
        log = installer.remove(self.install, payload=[SCM])
        self.assertEqual(stock.read_bytes(), b"stock-scm")
        self.assertFalse((self.install / "AP_mod_backup").exists())
        self.assertFalse(any("Restored" in line for line in log))

    def test_warns_when_the_modded_scm_has_no_backup(self) -> None:
        # No stock main.scm existed at deploy time, so there is no backup to
        # restore; the modded file is recognized and left in place with a note.
        installer.deploy(self.install, payload=[SCM])
        log = installer.remove(self.install, payload=[SCM])
        self.assertEqual((self.install / "data" / "main.scm").read_bytes(), b"scm-bytes")
        self.assertTrue(any("backup" in line.lower() for line in log))

    def test_keeps_a_cleo_folder_holding_other_files(self) -> None:
        installer.deploy(self.install, payload=[CLEO])
        player_script = self.install / "CLEO" / "players_own.cs"
        player_script.write_bytes(b"player-bytes")
        installer.remove(self.install, payload=[CLEO])
        self.assertFalse((self.install / "CLEO" / "gtavc_ap.cs").exists())
        self.assertTrue(player_script.is_file())

    def test_removes_a_copy_an_earlier_build_left_in_scripts(self) -> None:
        # Left behind, it would keep running the mod against the restored stock
        # main.scm and the deleted CLEO scripts, which is worse than a leftover.
        installer.deploy(self.install, payload=PAYLOAD)
        stale = self.install / "scripts" / "GtaVcAp.VC.asi"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_bytes(b"an-older-build")
        log = installer.remove(self.install, payload=PAYLOAD)
        self.assertFalse(stale.exists())
        self.assertTrue(any("scripts/GtaVcAp.VC.asi" in line for line in log))

    def test_removes_the_cleo_folder_it_created_once_empty(self) -> None:
        installer.deploy(self.install, payload=[CLEO])
        installer.remove(self.install, payload=[CLEO])
        self.assertFalse((self.install / "CLEO").exists())


class TestTextTablePatch(unittest.TestCase):
    def test_adds_the_key_and_leaves_everything_else_alone(self) -> None:
        patched = installer.add_gxt_key(VANILLA_TABLE, "APSTAT", "ARCHIPELAGO")
        self.assertEqual(installer.gxt_value(patched, "APSTAT"), "ARCHIPELAGO")
        for key in ("AMMU", "APR", "FEP_QUI", "ZEBRA"):
            self.assertEqual(installer.gxt_value(patched, key),
                             installer.gxt_value(VANILLA_TABLE, key))

    def test_keeps_the_keys_sorted_so_the_game_can_find_them(self) -> None:
        # The game binary-searches the key records, so an insertion out of order
        # would hide the new key and every key past it.
        patched = installer.add_gxt_key(VANILLA_TABLE, "APSTAT", "ARCHIPELAGO")
        keys = installer.gxt_keys(patched)
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(keys, ["AMMU", "APR", "APSTAT", "FEP_QUI", "ZEBRA"])

    def test_moves_the_tables_after_main_down_by_what_main_grew(self) -> None:
        patched = installer.add_gxt_key(VANILLA_TABLE, "APSTAT", "ARCHIPELAGO")
        # Reading a later table's own key proves its TABL offset followed the
        # text that was inserted above it.
        record, key_body, key_size, data_body, data_size = \
            installer._gxt_main_table(patched)
        self.assertGreater(data_size,
                           installer._gxt_main_table(VANILLA_TABLE)[4])
        table_size = struct.unpack_from("<I", patched, 4)[0]
        offsets = [struct.unpack_from("<I", patched, 8 + index * 12 + 8)[0]
                   for index in range(table_size // 12)]
        for offset in offsets[1:]:
            name = patched[offset:offset + 8].rstrip(b"\x00").decode()
            self.assertEqual(patched[offset + 8:offset + 12], b"TKEY", name)

    def test_is_idempotent(self) -> None:
        once = installer.add_gxt_key(VANILLA_TABLE, "APSTAT", "ARCHIPELAGO")
        self.assertEqual(installer.add_gxt_key(once, "APSTAT", "ARCHIPELAGO"), once)

    def test_repoints_a_key_that_reads_something_else(self) -> None:
        # A table an earlier build patched with another label must heal, or the
        # install is never current again and deploy runs on every launch.
        stale = installer.add_gxt_key(VANILLA_TABLE, "APSTAT", "OLD LABEL")
        healed = installer.add_gxt_key(stale, "APSTAT", "ARCHIPELAGO")
        self.assertEqual(installer.gxt_value(healed, "APSTAT"), "ARCHIPELAGO")
        keys = installer.gxt_keys(healed)
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(keys.count("APSTAT"), 1)
        for key in ("AMMU", "APR", "FEP_QUI", "ZEBRA"):
            self.assertEqual(installer.gxt_value(healed, key),
                             installer.gxt_value(VANILLA_TABLE, key))

    def test_refuses_a_key_longer_than_the_format_allows(self) -> None:
        with self.assertRaises(ValueError):
            installer.add_gxt_key(VANILLA_TABLE, "TOOLONGKEY", "x")

    def test_refuses_a_file_that_is_not_a_text_table(self) -> None:
        with self.assertRaises(ValueError):
            installer.add_gxt_key(b"not a gxt at all", "APSTAT", "x")


class TestTextTableDeploy(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.install = Path(self._tmp.name)
        text_dir = self.install / "TEXT"
        text_dir.mkdir()
        (text_dir / "american.gxt").write_bytes(VANILLA_TABLE)
        (text_dir / "french.gxt").write_bytes(VANILLA_TABLE)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_deploy_patches_every_table_and_backs_each_one_up(self) -> None:
        installer.deploy(self.install, payload=PAYLOAD)
        for name in ("american.gxt", "french.gxt"):
            patched = (self.install / "TEXT" / name).read_bytes()
            self.assertEqual(installer.gxt_value(patched, installer.PANEL_TEXT_KEY),
                             installer.PANEL_TEXT)
            backup = self.install / installer.BACKUP_DIR_NAME / name
            self.assertEqual(backup.read_bytes(), VANILLA_TABLE)

    def test_an_unpatched_table_makes_the_install_not_current(self) -> None:
        installer.deploy(self.install, payload=PAYLOAD)
        self.assertTrue(installer.mod_is_current(self.install, payload=PAYLOAD))
        (self.install / "TEXT" / "american.gxt").write_bytes(VANILLA_TABLE)
        self.assertFalse(installer.mod_is_current(self.install, payload=PAYLOAD))

    def test_an_install_without_text_tables_is_not_held_up(self) -> None:
        for path in (self.install / "TEXT").iterdir():
            path.unlink()
        (self.install / "TEXT").rmdir()
        log = installer.deploy(self.install, payload=PAYLOAD)
        self.assertTrue(installer.mod_is_current(self.install, payload=PAYLOAD))
        self.assertFalse([line for line in log if "menu text" in line])

    def test_a_truncated_table_is_reported_rather_than_raised(self) -> None:
        # A half-written file raises struct.error out of the readers, which the
        # guards have to name: deploy and remove both promise not to raise, and
        # remove runs this after the payload files are already gone.
        # Twelve bytes cuts an unpack_from short, which raises struct.error;
        # twenty bytes reaches the chunk check, which raises ValueError. Both have
        # to be caught, and only the first exercises the struct.error the guard
        # names.
        # Pinned rather than assumed, since which error a truncation raises
        # depends on where it cuts: a length guard added to the reader later would
        # otherwise turn both of these into ValueError with this test still green.
        with self.assertRaises(struct.error):
            installer.gxt_value(VANILLA_TABLE[:12], installer.PANEL_TEXT_KEY)
        with self.assertRaises(ValueError):
            installer.gxt_value(VANILLA_TABLE[:20], installer.PANEL_TEXT_KEY)
        (self.install / "TEXT" / "american.gxt").write_bytes(VANILLA_TABLE[:12])
        (self.install / "TEXT" / "french.gxt").write_bytes(VANILLA_TABLE[:20])
        log = installer.deploy(self.install, payload=PAYLOAD)
        reported = [line for line in log if "Could not add the menu text" in line]
        self.assertEqual(len(reported), 2, log)
        # A table this installer cannot read never holds an install up, and with
        # both of them unreadable there is nothing left to hold one up.
        self.assertTrue(installer.text_tables_are_patched(self.install))
        installer.remove(self.install, payload=PAYLOAD)

    def test_never_backs_up_a_table_it_already_patched(self) -> None:
        # A label change must not save the patched file as the stock one: remove
        # would then "restore stock" over a table that still carries the key.
        stale = installer.add_gxt_key(VANILLA_TABLE, installer.PANEL_TEXT_KEY,
                                      "OLD LABEL")
        (self.install / "TEXT" / "american.gxt").write_bytes(stale)
        installer.deploy(self.install, payload=PAYLOAD)
        backup = self.install / installer.BACKUP_DIR_NAME / "american.gxt"
        self.assertFalse(backup.exists())
        self.assertEqual(
            installer.gxt_value((self.install / "TEXT" / "american.gxt").read_bytes(),
                                installer.PANEL_TEXT_KEY),
            installer.PANEL_TEXT)

    def test_a_file_that_is_not_a_text_table_is_reported_and_left(self) -> None:
        (self.install / "TEXT" / "american.gxt").write_bytes(b"garbage")
        log = installer.deploy(self.install, payload=PAYLOAD)
        self.assertEqual((self.install / "TEXT" / "american.gxt").read_bytes(),
                         b"garbage")
        self.assertTrue([line for line in log if "Could not add the menu text" in line])

    def test_remove_brings_the_stock_tables_back(self) -> None:
        installer.deploy(self.install, payload=PAYLOAD)
        log = installer.remove(self.install, payload=PAYLOAD)
        for name in ("american.gxt", "french.gxt"):
            self.assertEqual((self.install / "TEXT" / name).read_bytes(), VANILLA_TABLE)
            self.assertFalse((self.install / installer.BACKUP_DIR_NAME / name).exists())
        self.assertTrue([line for line in log if "Restored the stock TEXT" in line])

    def test_remove_leaves_a_player_replaced_table_alone(self) -> None:
        installer.deploy(self.install, payload=PAYLOAD)
        other = build_text_table({"MAIN": {"AMMU": "Ammu-Nation"}})
        (self.install / "TEXT" / "american.gxt").write_bytes(other)
        installer.remove(self.install, payload=PAYLOAD)
        self.assertEqual((self.install / "TEXT" / "american.gxt").read_bytes(), other)

    def test_remove_says_so_when_a_patched_table_has_no_backup(self) -> None:
        installer.deploy(self.install, payload=PAYLOAD)
        (self.install / installer.BACKUP_DIR_NAME / "american.gxt").unlink()
        log = installer.remove(self.install, payload=PAYLOAD)
        self.assertTrue([line for line in log if "No backup for TEXT/american.gxt" in line])


if __name__ == "__main__":
    unittest.main()
