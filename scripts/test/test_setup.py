"""Offline setup installs the existing payload and preserves connection settings."""

import configparser
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gta_vc_setup import installer, setup
from test_installer import ASI, SCM, build_executable, install_executable


class TestOfflineSetup(unittest.TestCase):
    def test_uninstall_from_launcher_preserves_saves_and_blocks_running_game(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "gta-vc.exe").write_bytes(b"packed executable")
            (folder / "GtaVcAp.VC.asi").write_bytes(b"mod")
            save = folder / "GTAVCsf1.b"
            save.write_bytes(b"save")
            with (mock.patch.object(setup, "choose_action", return_value="uninstall"),
                  mock.patch.object(installer, "game_process_running", return_value=False) as running,
                  mock.patch.object(installer, "remove", return_value=[]) as remove):
                setup.launch(str(folder), open_directory=mock.Mock(), messagebox=mock.Mock())
                remove.assert_called_once_with(folder)
                self.assertEqual(save.read_bytes(), b"save")
                running.return_value = True
                with self.assertRaisesRegex(installer.InstallRefused, "Close Vice City"):
                    setup.uninstall(folder)
                remove.assert_called_once()

    def test_install_and_update_preserve_settings_and_stock_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            install_executable(folder)
            (folder / "data").mkdir()
            (folder / "data/main.scm").write_bytes(b"stock script")
            with (mock.patch.object(installer, "game_process_running", return_value=False),
                  mock.patch.dict(os.environ, LOCALAPPDATA=str(folder / "user")),
                  mock.patch.object(setup.subprocess, "run"),
                  mock.patch.object(installer, "materialize_payload", return_value=[ASI, SCM])):
                log = setup.install(folder)
                self.assertIn("Confirmed gta-vc.exe: classic 1.0 English.", log)
                self.assertEqual((folder / ASI[0]).read_bytes(), ASI[1])
                self.assertEqual((folder / "AP_mod_backup/main.scm").read_bytes(), b"stock script")
                settings = folder / "user/GtaVcAp/connection.ini"
                self.assertEqual(settings.read_text().strip(), setup.CONNECTION_TEMPLATE.strip())
                self.assertFalse((folder / "GtaVcAp.VC.ini").exists())
                existing = b"[archipelago]\r\nslot=My Slot\r\npassword=secret\r\n"
                settings.write_bytes(existing)
                setup.install(folder)
                self.assertEqual(settings.read_bytes(), existing)
                self.assertEqual((folder / "AP_mod_backup/main.scm").read_bytes(), b"stock script")
            with (mock.patch.object(installer, "game_process_running", return_value=True),
                  mock.patch.object(installer, "deploy") as deploy):
                with self.assertRaisesRegex(installer.InstallRefused, "Close Vice City"):
                    setup.install(folder)
                deploy.assert_not_called()

    def test_migrate_connection_once_and_preserve_legacy_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            install_executable(folder)
            legacy = folder / "GtaVcAp.VC.ini"
            original = "[archipelago]\nserver=localhost:1234\nslot=My Slot\npassword=50%secret\n"
            legacy.write_text(original, encoding="utf-8")
            with (mock.patch.object(installer, "game_process_running", return_value=False),
                  mock.patch.dict(os.environ, LOCALAPPDATA=str(folder / "user")),
                  mock.patch.object(setup.subprocess, "run"),
                  mock.patch.object(installer, "deploy", return_value=[])):
                setup.install(folder)
                settings_path = folder / "user/GtaVcAp/connection.ini"
                settings = configparser.ConfigParser(interpolation=None)
                settings.read(settings_path)
                self.assertEqual(settings.sections(), ["archipelago"])
                self.assertEqual(dict(settings["archipelago"]), {
                    "server": "localhost:1234", "slot": "My Slot", "password": "50%secret"})
                self.assertEqual(legacy.read_text(), original)
                saved = settings_path.read_bytes()
                legacy.write_text(original.replace("My Slot", "Old Slot"), encoding="utf-8")
                setup.install(folder)
                self.assertEqual(settings_path.read_bytes(), saved)

    def test_unconfirmed_executable_stops_setup_before_any_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            executable = folder / "gta-vc.exe"
            with (mock.patch.object(installer, "game_process_running", return_value=False),
                  mock.patch.object(installer, "materialize_payload") as materialize,
                  mock.patch.object(installer, "deploy") as deploy):
                before = mock.Mock()
                for content in (b"unknown executable", build_executable("1.1 English"), build_executable("Steam")):
                    for callback in (None, before):
                        with self.subTest(content_size=len(content), standalone=callback is not None):
                            executable.write_bytes(content)
                            with self.assertRaises(installer.GameBuildRefused):
                                setup.install(folder, before_install=callback)
                            self.assertEqual(list(folder.iterdir()), [executable])
                materialize.assert_not_called()
                before.assert_not_called()
                deploy.assert_not_called()

    def test_cancel_and_install_refusal(self):
        message = mock.Mock()
        directory = mock.Mock(return_value="")
        with mock.patch.object(setup, "install") as install:
            setup.launch(open_directory=directory, messagebox=message)
            install.assert_not_called()
            message.assert_not_called()
            install.side_effect = installer.InstallRefused("Unsupported game build")
            setup.launch("game folder", open_directory=directory, messagebox=message)
            message.assert_called_once_with(setup.TITLE, "Unsupported game build", error=True)

    def test_failed_process_check_blocks_installation(self):
        with (mock.patch.object(installer.sys, "platform", "win32"),
              mock.patch.object(installer.subprocess, "CREATE_NO_WINDOW", 0, create=True),
              mock.patch.object(installer.subprocess, "run") as run):
            for result, expected in [
                (subprocess.CompletedProcess([], 1, b""), True),
                (subprocess.CompletedProcess([], 0, None), True),
                (subprocess.CompletedProcess([], 0, b""), True),
                (subprocess.CompletedProcess([], 0, b"GTA-VC.EXE"), True),
                (subprocess.CompletedProcess([], 0, b"No tasks match"), False),
            ]:
                run.return_value = result
                self.assertEqual(installer.game_process_running(), expected)
            run.side_effect = subprocess.TimeoutExpired("tasklist", 3)
            self.assertTrue(installer.game_process_running())
