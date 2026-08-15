"""Tests for the mod installer, on a temporary install with a fake payload.

Each test passes an explicit payload, so the real bundled payload (staged by
the build once the mod compiles) never matters here. Covers deploy, backup,
idempotency, the no-payload path, the removal manifest, and remove.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ... import installer

ASI = ("GtaVcAp.VC.asi", b"asi-bytes")
SCM = ("main.scm", b"scm-bytes")
CLEO = ("cleo/gtavc_ap.cs", b"cleo-bytes")
PAYLOAD = [ASI, CLEO, SCM]


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

    def test_removes_the_cleo_folder_it_created_once_empty(self) -> None:
        installer.deploy(self.install, payload=[CLEO])
        installer.remove(self.install, payload=[CLEO])
        self.assertFalse((self.install / "CLEO").exists())


if __name__ == "__main__":
    unittest.main()
