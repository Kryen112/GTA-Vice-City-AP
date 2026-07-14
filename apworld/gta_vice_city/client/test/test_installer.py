"""Tests for the mod installer, on a temporary install with a fake payload.

The real apworld carries no payload yet, so these pass an explicit payload to
exercise the deploy, backup, idempotency, and no-payload paths.
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


if __name__ == "__main__":
    unittest.main()
