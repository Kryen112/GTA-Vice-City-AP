"""Tests for the client's game auto-launch and the /play command.

These import the context (and so CommonClient), and run in the world test
environment where Archipelago is on the path.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import types
import unittest
from unittest import mock

from ... import GTAViceCityWorld
from .. import context as context_module


class TestSettingsReaders(unittest.TestCase):
    # Exercise the readers that turn host.yaml settings into a launch decision,
    # against a stubbed world settings object. These readers only touch the
    # world settings, not the context instance, so they run unbound (with a
    # None self) and need no event loop.

    def _with_settings(self, install_folder: str, auto_launch_game: bool):
        # World.settings is a lazy property on the AutoWorldRegister metaclass;
        # replace it with one returning a stub so no real host.yaml is loaded.
        fake = types.SimpleNamespace(
            install_folder=install_folder, auto_launch_game=auto_launch_game,
        )
        return mock.patch.object(
            type(GTAViceCityWorld), "settings",
            new_callable=mock.PropertyMock, return_value=fake,
        )

    def test_executable_found_when_folder_holds_the_exe(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            executable = os.path.join(folder, "gta-vc.exe")
            with open(executable, "w"):
                pass
            with self._with_settings(folder, True):
                self.assertEqual(context_module.GTAViceCityContext._game_executable(None), executable)
                self.assertTrue(context_module.GTAViceCityContext._auto_launch_enabled(None))

    def test_no_executable_when_folder_blank_or_missing_exe(self) -> None:
        with self._with_settings("", True):
            self.assertIsNone(context_module.GTAViceCityContext._game_executable(None))
        with tempfile.TemporaryDirectory() as folder:  # folder exists, exe does not
            with self._with_settings(folder, False):
                self.assertIsNone(context_module.GTAViceCityContext._game_executable(None))
                self.assertFalse(context_module.GTAViceCityContext._auto_launch_enabled(None))


class TestGameLaunch(unittest.TestCase):
    # The context creates asyncio tasks in its constructor, so it must be built
    # inside a running loop.

    def test_launch_fires_once_then_forced_relaunches(self) -> None:
        async def scenario() -> None:
            context = context_module.GTAViceCityContext(None, None, 52300, "Player1")
            with mock.patch.object(context, "_game_executable", return_value="C:/game/gta-vc.exe"), \
                 mock.patch.object(context_module.subprocess, "Popen") as popen:
                context.launch_game()
                context.launch_game()
                self.assertEqual(popen.call_count, 1)  # once-per-session guard
                context.launch_game(forced=True)
                self.assertEqual(popen.call_count, 2)  # forced bypasses the guard

        asyncio.run(scenario())

    def test_no_executable_does_not_launch(self) -> None:
        async def scenario() -> None:
            context = context_module.GTAViceCityContext(None, None, 52300, "Player1")
            with mock.patch.object(context, "_game_executable", return_value=None), \
                 mock.patch.object(context_module.subprocess, "Popen") as popen:
                context.launch_game()
                popen.assert_not_called()

        asyncio.run(scenario())

    def test_play_command_forces_launch(self) -> None:
        async def scenario() -> None:
            context = context_module.GTAViceCityContext(None, None, 52300, "Player1")
            with mock.patch.object(context, "launch_game") as launch_game:
                processor = context_module.GTAViceCityCommandProcessor(context)
                processor._cmd_play()
                launch_game.assert_called_once_with(forced=True)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
