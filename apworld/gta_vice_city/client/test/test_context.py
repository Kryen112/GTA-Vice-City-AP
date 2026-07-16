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

from ... import GTAViceCityWorld, installer
from .. import context as context_module


@contextmanager
def _fake_settings(install_folder: str = "", auto_launch_game: bool = True,
                   isolate_saves: bool = False, auto_install_mod: bool = False):
    # World.settings is a lazy property on the AutoWorldRegister metaclass;
    # replace it with one returning a stub so no real host.yaml is loaded. Also
    # blind the context to the real save folder, so tests never move real saves.
    fake = types.SimpleNamespace(
        install_folder=install_folder, auto_launch_game=auto_launch_game,
        isolate_saves=isolate_saves, auto_install_mod=auto_install_mod)
    with mock.patch.object(
        type(GTAViceCityWorld), "settings",
        new_callable=mock.PropertyMock, return_value=fake,
    ), mock.patch.object(context_module.saves, "user_files_directory", return_value=None):
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

    def test_restore_delegates(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                with mock.patch.object(context, "restore_saves") as restore:
                    context_module.GTAViceCityCommandProcessor(context)._cmd_restore()
                    restore.assert_called_once_with()

        asyncio.run(scenario())

    def test_installmod_delegates(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                with mock.patch.object(context, "install_mod") as install_mod:
                    context_module.GTAViceCityCommandProcessor(context)._cmd_installmod()
                    install_mod.assert_called_once_with()

        asyncio.run(scenario())


class TestSaveIsolation(unittest.TestCase):
    def test_isolates_this_seed_when_enabled_and_the_game_is_not_running(self) -> None:
        async def scenario() -> None:
            with _fake_settings("", isolate_saves=True):
                context = _context()
                context.save_manager = mock.Mock()
                context.save_manager.is_isolated.return_value = False
                context.seed_name = "Seed One"
                with mock.patch.object(context, "game_running", return_value=False):
                    context._isolate_saves()
                    context.save_manager.isolate.assert_called_once_with("Seed One")

        asyncio.run(scenario())

    def test_skips_isolation_while_the_game_is_running(self) -> None:
        async def scenario() -> None:
            with _fake_settings("", isolate_saves=True):
                context = _context()
                context.save_manager = mock.Mock()
                context.save_manager.is_isolated.return_value = False
                context.seed_name = "Seed One"
                with mock.patch.object(context, "game_running", return_value=True):
                    context._isolate_saves()
                    context.save_manager.isolate.assert_not_called()

        asyncio.run(scenario())

    def test_skips_isolation_when_disabled(self) -> None:
        async def scenario() -> None:
            with _fake_settings("", isolate_saves=False):
                context = _context()
                context.save_manager = mock.Mock()
                context.seed_name = "Seed One"
                context._isolate_saves()
                context.save_manager.isolate.assert_not_called()

        asyncio.run(scenario())


class TestModInstall(unittest.TestCase):
    def test_deploys_when_the_mod_is_not_current(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(folder):
                context = _context()
                with mock.patch.object(context, "game_running", return_value=False), \
                     mock.patch.object(installer, "mod_is_current", return_value=False), \
                     mock.patch.object(installer, "deploy", return_value=["Installed main.scm."]) as deploy:
                    context.install_mod()
                    deploy.assert_called_once_with(context.install_dir)

        asyncio.run(scenario())

    def test_skips_deploy_while_the_game_is_running(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(folder):
                context = _context()
                with mock.patch.object(context, "game_running", return_value=True), \
                     mock.patch.object(installer, "deploy") as deploy:
                    context.install_mod()
                    deploy.assert_not_called()

        asyncio.run(scenario())

    def test_skips_deploy_when_already_current(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(folder):
                context = _context()
                with mock.patch.object(context, "game_running", return_value=False), \
                     mock.patch.object(installer, "mod_is_current", return_value=True), \
                     mock.patch.object(installer, "deploy") as deploy:
                    context.install_mod()
                    deploy.assert_not_called()

        asyncio.run(scenario())

    def test_auto_installs_on_connect_when_enabled(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, \
                    _fake_settings(folder, auto_launch_game=False, auto_install_mod=True):
                context = _context()
                with mock.patch.object(context, "install_mod") as install_mod:
                    await context.setup_and_launch()
                    install_mod.assert_called_once_with(announce_current=False)

        asyncio.run(scenario())

    def test_no_auto_install_on_connect_when_disabled(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, \
                    _fake_settings(folder, auto_launch_game=False, auto_install_mod=False):
                context = _context()
                with mock.patch.object(context, "install_mod") as install_mod:
                    await context.setup_and_launch()
                    install_mod.assert_not_called()

        asyncio.run(scenario())


class TestItemToast(unittest.TestCase):
    def _setup(self, context):
        context.slot = 1
        context.slot_info = {}
        context.player_names = {1: "Me", 2: "PlayerTwo"}

    def _text(self, item_player: int, receiving: int) -> str | None:
        async def scenario() -> str | None:
            with _fake_settings(""):
                from NetUtils import NetworkItem
                context = _context()
                self._setup(context)
                with mock.patch.object(context.item_names, "lookup_in_slot",
                                       return_value="Progressive Cortez"):
                    return context._item_toast_text(
                        {"type": "ItemSend", "receiving": receiving,
                         "item": NetworkItem(42, 100, item_player, 0)})

        return asyncio.run(scenario())

    def test_found_own_item(self) -> None:
        self.assertEqual(self._text(1, 1), "You found your Progressive Cortez")

    def test_sent_to_another_player(self) -> None:
        self.assertEqual(self._text(1, 2), "You sent Progressive Cortez to PlayerTwo")

    def test_another_player_found_mine(self) -> None:
        self.assertEqual(self._text(2, 1), "PlayerTwo found your Progressive Cortez")

    def test_send_toast_only_when_the_mod_is_connected(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                with mock.patch.object(type(context.bridge), "connected",
                                       new_callable=mock.PropertyMock) as connected, \
                     mock.patch.object(context.bridge, "send_toast") as send_toast:
                    connected.return_value = False
                    await context._send_toast("hi")
                    send_toast.assert_not_called()
                    connected.return_value = True
                    await context._send_toast("hi")
                    send_toast.assert_awaited_once_with("hi")

        asyncio.run(scenario())

    def test_on_print_json_toasts_my_event_and_ignores_others(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                from NetUtils import NetworkItem
                context = _context()
                self._setup(context)
                with mock.patch.object(context, "_schedule") as schedule, \
                     mock.patch.object(context, "_send_toast", mock.Mock()), \
                     mock.patch.object(context, "_item_toast_text", return_value="X"):
                    context.on_print_json(
                        {"type": "ItemSend", "receiving": 2, "data": [],
                         "item": NetworkItem(42, 100, 1, 0)})
                    schedule.assert_called_once()  # my check, sent to PlayerTwo
                    schedule.reset_mock()
                    # An event between two other players concerns nobody here.
                    context.on_print_json(
                        {"type": "ItemSend", "receiving": 2, "data": [],
                         "item": NetworkItem(42, 100, 3, 0)})
                    schedule.assert_not_called()

        asyncio.run(scenario())


def _run_goal(configure) -> tuple[int, bool]:
    # Build a context, apply the caller's goal state, run _maybe_finish_goal,
    # and report how many CLIENT_GOAL messages went out and finished_game.
    async def scenario() -> tuple[int, bool]:
        with _fake_settings(""):
            context = _context()
            context.slot = 1
            configure(context)
            with mock.patch.object(
                context, "send_msgs", new_callable=mock.AsyncMock,
            ) as send:
                context._maybe_finish_goal()
                await asyncio.gather(*list(context._background_tasks))
                return send.await_count, context.finished_game

    return asyncio.run(scenario())


def _received(item_id: int, count: int) -> list:
    from NetUtils import NetworkItem
    # A distractor item plus count copies of the goal item.
    items = [NetworkItem(999, 1, 1, 0)]
    items += [NetworkItem(item_id, 10 + n, 1, 0) for n in range(count)]
    return items


class TestHiddenPackagesHuntGoal(unittest.TestCase):
    def test_completes_when_enough_are_received(self) -> None:
        def configure(context):
            context.slot_goal = "hidden_packages"
            context.hunt_item_id = 7
            context.hunt_required = 3
            context.items_received = _received(7, 3)

        self.assertEqual(_run_goal(configure), (1, True))

    def test_does_not_complete_below_the_threshold(self) -> None:
        def configure(context):
            context.slot_goal = "hidden_packages"
            context.hunt_item_id = 7
            context.hunt_required = 3
            context.items_received = _received(7, 2)

        self.assertEqual(_run_goal(configure), (0, False))

    def test_does_not_resend_once_finished(self) -> None:
        def configure(context):
            context.slot_goal = "hidden_packages"
            context.hunt_item_id = 7
            context.hunt_required = 3
            context.items_received = _received(7, 5)
            context.finished_game = True

        self.assertEqual(_run_goal(configure), (0, True))


class TestFinalMissionGoal(unittest.TestCase):
    def test_completes_when_the_finale_is_checked(self) -> None:
        def configure(context):
            context.slot_goal = "final_mission"
            context.final_location_id = 500
            context.checked_locations = {1, 2, 500}

        self.assertEqual(_run_goal(configure), (1, True))

    def test_incomplete_until_the_finale_is_checked(self) -> None:
        def configure(context):
            context.slot_goal = "final_mission"
            context.final_location_id = 500
            context.checked_locations = {1, 2, 3}

        self.assertEqual(_run_goal(configure), (0, False))


class TestHundredPercentGoal(unittest.TestCase):
    def test_completes_when_nothing_is_missing(self) -> None:
        def configure(context):
            context.slot_goal = "hundred_percent"
            context.checked_locations = {1, 2, 3}
            context.missing_locations = set()

        self.assertEqual(_run_goal(configure), (1, True))

    def test_incomplete_while_a_location_is_missing(self) -> None:
        def configure(context):
            context.slot_goal = "hundred_percent"
            context.checked_locations = {1, 2}
            context.missing_locations = {3}

        self.assertEqual(_run_goal(configure), (0, False))

    def test_incomplete_before_location_info_arrives(self) -> None:
        # Nothing checked and nothing missing yet (the pre-Connected state) is
        # not a completed game.
        def configure(context):
            context.slot_goal = "hundred_percent"
            context.checked_locations = set()
            context.missing_locations = set()

        self.assertEqual(_run_goal(configure), (0, False))


class TestGoalDispatch(unittest.TestCase):
    def test_room_update_can_complete_the_goal(self) -> None:
        # A newly checked location reaches _maybe_finish_goal through
        # on_package's RoomUpdate dispatch, not only through a direct call.
        async def scenario() -> int:
            with _fake_settings(""):
                context = _context()
                context.slot = 1
                context.slot_goal = "final_mission"
                context.final_location_id = 500
                context.checked_locations = {500}
                with mock.patch.object(
                    context, "send_msgs", new_callable=mock.AsyncMock,
                ) as send:
                    context.on_package("RoomUpdate", {})
                    await asyncio.gather(*list(context._background_tasks))
                    return send.await_count

        self.assertEqual(asyncio.run(scenario()), 1)


if __name__ == "__main__":
    unittest.main()
