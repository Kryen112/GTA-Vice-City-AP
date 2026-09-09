"""Offline setup installs the existing payload and preserves connection settings."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from worlds.LauncherComponents import Type, components

from .. import installer, launch_setup, setup
from .test_installer import ASI, SCM


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
                  mock.patch.object(installer, "remove", return_value=[]) as remove,
                  mock.patch.object(setup.Utils, "messagebox")):
                setup.launch(str(folder))
                remove.assert_called_once_with(folder)
                self.assertEqual(save.read_bytes(), b"save")
                running.return_value = True
                with self.assertRaisesRegex(installer.InstallRefused, "Close Vice City"):
                    setup.uninstall(folder)
                remove.assert_called_once()

    def test_launcher_registers_only_setup(self):
        entries = [component for component in components
                   if component.display_name.startswith("GTA Vice City")]
        self.assertEqual([component.display_name for component in entries], [setup.TITLE])
        self.assertEqual(entries[0].type, Type.TOOL)
        self.assertIs(entries[0].func, launch_setup)

    def test_install_and_update_preserve_settings_and_stock_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "gta-vc.exe").write_bytes(b"packed executable")
            (folder / "data").mkdir()
            (folder / "data/main.scm").write_bytes(b"stock script")
            with (mock.patch.object(installer, "game_process_running", return_value=False),
                  mock.patch.object(installer, "materialize_payload", return_value=[ASI, SCM])):
                setup.install(folder)
                self.assertEqual((folder / ASI[0]).read_bytes(), ASI[1])
                self.assertEqual((folder / "AP_mod_backup/main.scm").read_bytes(), b"stock script")
                settings = folder / "GtaVcAp.VC.ini"
                self.assertEqual(settings.read_text(), setup.CONNECTION_TEMPLATE)
                existing = b"[archipelago]\r\nslot=My Slot\r\npassword=secret\r\n[toasts]\r\nscale=2\r\n"
                settings.write_bytes(existing)
                setup.install(folder)
                self.assertEqual(settings.read_bytes(), existing)
                self.assertEqual((folder / "AP_mod_backup/main.scm").read_bytes(), b"stock script")
            with (mock.patch.object(installer, "game_process_running", return_value=True),
                  mock.patch.object(installer, "deploy") as deploy):
                with self.assertRaisesRegex(installer.InstallRefused, "Close Vice City"):
                    setup.install(folder)
                deploy.assert_not_called()

    def test_cancel_and_install_refusal(self):
        with (mock.patch.object(setup.Utils, "open_directory", return_value=""),
              mock.patch.object(setup, "install") as install,
              mock.patch.object(setup.Utils, "messagebox") as message):
            setup.launch()
            install.assert_not_called()
            message.assert_not_called()
            install.side_effect = installer.InstallRefused("Unsupported game build")
            setup.launch("game folder")
            message.assert_called_once_with(setup.TITLE, "Unsupported game build", error=True)

    def test_failed_process_check_blocks_installation(self):
        with (mock.patch.object(installer.sys, "platform", "win32"),
              mock.patch.object(installer.subprocess, "CREATE_NO_WINDOW", 0, create=True),
              mock.patch.object(installer.subprocess, "run") as run):
            for result, expected in [
                (subprocess.CompletedProcess([], 1, ""), True),
                (subprocess.CompletedProcess([], 0, "GTA-VC.EXE"), True),
                (subprocess.CompletedProcess([], 0, "No tasks match"), False),
            ]:
                run.return_value = result
                self.assertEqual(installer.game_process_running(), expected)
            run.side_effect = subprocess.TimeoutExpired("tasklist", 3)
            self.assertTrue(installer.game_process_running())
