"""Tests for the client's install-folder handling, auto-launch, and commands.

These import the context (and so CommonClient), and run in the world test
environment where Archipelago is on the path. The context creates asyncio tasks
in its constructor and reads the world settings, so it is built inside a running
loop with the settings stubbed.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from ... import GTAViceCityWorld
from .. import context as context_module


@contextmanager
def _fake_settings(install_folder: str = "", auto_launch_game: bool = True):
    # World.settings is a lazy property on the AutoWorldRegister metaclass;
    # replace it with one returning a stub so no real host.yaml is loaded.
    fake = types.SimpleNamespace(install_folder=install_folder, auto_launch_game=auto_launch_game)
    with mock.patch.object(
        type(GTAViceCityWorld), "settings",
        new_callable=mock.PropertyMock, return_value=fake,
    ):
        yield fake


@contextmanager
def _install_folder_with_exe():
    with tempfile.TemporaryDirectory() as folder:
        with open(os.path.join(folder, "gta-vc.exe"), "w"):
            pass
        yield folder


def _context() -> context_module.GTAViceCityContext:
    return context_module.GTAViceCityContext(None, None, 52300, "Player1")


class TestLooksLikeInstall(unittest.TestCase):
    def test_true_only_when_the_exe_is_present(self) -> None:
        with _install_folder_with_exe() as folder:
            self.assertTrue(context_module.looks_like_install(Path(folder)))
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(context_module.looks_like_install(Path(folder)))


class TestLaunchGame(unittest.TestCase):
    def test_launches_from_the_install_folder(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(folder):
                context = _context()
                self.assertEqual(context.install_dir, Path(folder))
                with mock.patch.object(context_module.subprocess, "Popen") as popen:
                    context.launch_game()
                    popen.assert_called_once()
                    self.assertTrue(context.game_launched)

        asyncio.run(scenario())

    def test_no_install_folder_does_not_launch(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                self.assertIsNone(context.install_dir)
                with mock.patch.object(context_module.subprocess, "Popen") as popen:
                    context.launch_game()
                    popen.assert_not_called()

        asyncio.run(scenario())

    def test_missing_exe_does_not_launch(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""), tempfile.TemporaryDirectory() as empty:
                context = _context()
                context.install_dir = Path(empty)  # a folder with no gta-vc.exe
                with mock.patch.object(context_module.subprocess, "Popen") as popen:
                    context.launch_game()
                    popen.assert_not_called()

        asyncio.run(scenario())


class TestSetupAndLaunch(unittest.TestCase):
    def test_auto_launches_once_when_the_folder_is_known(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(folder, auto_launch_game=True):
                context = _context()
                with mock.patch.object(context_module.subprocess, "Popen") as popen:
                    await context.setup_and_launch()
                    await context.setup_and_launch()  # guarded by game_launched
                    self.assertEqual(popen.call_count, 1)

        asyncio.run(scenario())

    def test_does_not_launch_when_auto_launch_is_off(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(folder, auto_launch_game=False):
                context = _context()
                with mock.patch.object(context_module.subprocess, "Popen") as popen:
                    await context.setup_and_launch()
                    popen.assert_not_called()

        asyncio.run(scenario())

    def test_gui_without_a_folder_prompts(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                with mock.patch.object(context_module, "gui_enabled", True), \
                     mock.patch.object(context, "pick_install_dir") as pick, \
                     mock.patch.object(context_module.subprocess, "Popen"):
                    await context.setup_and_launch()
                    pick.assert_awaited_once()

        asyncio.run(scenario())

    def test_headless_without_a_folder_warns_and_does_not_prompt(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                with mock.patch.object(context_module, "gui_enabled", False), \
                     mock.patch.object(context, "pick_install_dir") as pick, \
                     mock.patch.object(context_module.subprocess, "Popen") as popen:
                    await context.setup_and_launch()
                    pick.assert_not_called()
                    popen.assert_not_called()
                    self.assertIsNone(context.install_dir)

        asyncio.run(scenario())


class TestPickInstallDir(unittest.TestCase):
    def test_valid_choice_is_set_and_saved(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(""):
                context = _context()
                with mock.patch.object(context_module.Utils, "open_directory", return_value=folder), \
                     mock.patch.object(context, "_save_install_folder") as save:
                    await context.pick_install_dir()
                    self.assertEqual(context.install_dir, Path(folder))
                    save.assert_called_once_with(folder)

        asyncio.run(scenario())

    def test_cancelled_choice_leaves_the_folder_unset(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                with mock.patch.object(context_module.Utils, "open_directory", return_value=None), \
                     mock.patch.object(context, "_save_install_folder") as save:
                    await context.pick_install_dir()
                    self.assertIsNone(context.install_dir)
                    save.assert_not_called()

        asyncio.run(scenario())

    def test_folder_without_the_exe_is_rejected(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""), tempfile.TemporaryDirectory() as empty:
                context = _context()
                with mock.patch.object(context_module.Utils, "open_directory", return_value=empty), \
                     mock.patch.object(context, "_save_install_folder") as save:
                    await context.pick_install_dir()
                    self.assertIsNone(context.install_dir)
                    save.assert_not_called()

        asyncio.run(scenario())


class TestSaveInstallFolder(unittest.TestCase):
    def test_writes_the_value_and_saves_host_yaml(self) -> None:
        async def scenario() -> None:
            with _fake_settings("") as fake:
                context = _context()
                with mock.patch("settings.get_settings") as get_settings:
                    context._save_install_folder("C:/Games/GTA Vice City")
                    self.assertEqual(fake.install_folder, "C:/Games/GTA Vice City")
                    get_settings.return_value.save.assert_called_once()

        asyncio.run(scenario())


class TestCommands(unittest.TestCase):
    def test_play_launches(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                with mock.patch.object(context, "launch_game") as launch_game:
                    context_module.GTAViceCityCommandProcessor(context)._cmd_play()
                    launch_game.assert_called_once_with()

        asyncio.run(scenario())

    def test_setfolder_accepts_a_valid_path(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(""):
                context = _context()
                with mock.patch.object(context, "set_install_dir") as set_dir:
                    context_module.GTAViceCityCommandProcessor(context)._cmd_setfolder(folder)
                    set_dir.assert_called_once_with(folder)

        asyncio.run(scenario())

    def test_setfolder_rejects_a_folder_without_the_exe(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""), tempfile.TemporaryDirectory() as empty:
                context = _context()
                with mock.patch.object(context, "set_install_dir") as set_dir:
                    context_module.GTAViceCityCommandProcessor(context)._cmd_setfolder(empty)
                    set_dir.assert_not_called()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
