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
from .. import protocol


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


class TestOutboundChecksSurviveAFailedSend(unittest.TestCase):
    """A check the server never receives has to be recoverable.

    The mod cannot find a location twice: it records the location the moment it
    detects it, and once the player saves, the completion global folds into the
    next baseline. So the only place a lost check can come back from is
    CommonContext's replay of locations_checked on Connected.
    """

    def test_the_location_is_recorded_even_when_the_send_raises(self) -> None:
        checked = set()

        async def scenario() -> None:
            context = _context()

            async def failing_send(messages) -> None:
                raise ConnectionResetError("server went away mid-frame")

            context.send_msgs = failing_send
            with self.assertRaises(ConnectionResetError):
                await context.on_bridge_check(4242)
            checked.update(context.locations_checked)

        asyncio.run(scenario())
        # Recorded before the send, so the framework replays it on reconnect.
        self.assertIn(4242, checked)

    def test_the_location_is_recorded_on_a_send_that_works(self) -> None:
        sent = []
        checked = set()

        async def scenario() -> None:
            context = _context()

            async def capture(messages) -> None:
                sent.extend(messages)

            context.send_msgs = capture
            await context.on_bridge_check(77)
            await context.on_bridge_check(77)
            checked.update(context.locations_checked)

        asyncio.run(scenario())
        self.assertIn(77, checked)
        self.assertEqual(
            sent, [{"cmd": "LocationChecks", "locations": [77]}] * 2)


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

    def test_uninstall_delegates(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                with mock.patch.object(context, "uninstall_mod") as uninstall_mod:
                    context_module.GTAViceCityCommandProcessor(context)._cmd_uninstall()
                    uninstall_mod.assert_called_once_with()

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


class TestModUninstall(unittest.TestCase):
    def test_restores_saves_removes_the_mod_and_discards_state(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(folder):
                context = _context()
                context.save_manager = mock.Mock()
                context.save_manager.is_isolated.return_value = True
                context.save_manager.restore.return_value = "Restored your normal saves."
                context.save_manager.discard_isolation_state.return_value = None
                with mock.patch.object(context, "game_running", return_value=False), \
                     mock.patch.object(installer, "remove",
                                       return_value=["Removed GtaVcAp.VC.asi."]) as remove:
                    context.uninstall_mod()
                    context.save_manager.restore.assert_called_once_with()
                    remove.assert_called_once_with(context.install_dir)
                    context.save_manager.discard_isolation_state.assert_called_once_with()
                    # Unlike /restore, uninstall leaves isolation unsuspended:
                    # a later connect is the full opt-in again, reinstalling
                    # the mod and re-isolating seed saves together.
                    self.assertFalse(context.isolation_suspended)

        asyncio.run(scenario())

    def test_a_failed_restore_stops_before_touching_the_mod(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(folder):
                context = _context()
                context.save_manager = mock.Mock()
                context.save_manager.is_isolated.return_value = True
                context.save_manager.restore.side_effect = RuntimeError("collision")
                with mock.patch.object(context, "game_running", return_value=False), \
                     mock.patch.object(installer, "remove") as remove:
                    context.uninstall_mod()
                    remove.assert_not_called()
                    context.save_manager.discard_isolation_state.assert_not_called()

        asyncio.run(scenario())

    def test_blocked_while_the_game_is_running(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(folder):
                context = _context()
                context.save_manager = mock.Mock()
                with mock.patch.object(context, "game_running", return_value=True), \
                     mock.patch.object(installer, "remove") as remove:
                    context.uninstall_mod()
                    remove.assert_not_called()
                    context.save_manager.restore.assert_not_called()

        asyncio.run(scenario())

    def test_no_install_folder_warns_and_does_nothing(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                with mock.patch.object(installer, "remove") as remove:
                    context.uninstall_mod()
                    remove.assert_not_called()

        asyncio.run(scenario())

    def test_a_failed_discard_still_finishes(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(folder):
                context = _context()
                context.save_manager = mock.Mock()
                context.save_manager.is_isolated.return_value = False
                context.save_manager.discard_isolation_state.side_effect = OSError("locked")
                with mock.patch.object(context, "game_running", return_value=False), \
                     mock.patch.object(installer, "remove", return_value=[]) as remove:
                    context.uninstall_mod()  # the note is logged, nothing raises
                    remove.assert_called_once_with(context.install_dir)

        asyncio.run(scenario())

    def test_saves_never_isolated_still_removes_the_mod(self) -> None:
        async def scenario() -> None:
            with _install_folder_with_exe() as folder, _fake_settings(folder):
                context = _context()
                context.save_manager = mock.Mock()
                context.save_manager.is_isolated.return_value = False
                context.save_manager.discard_isolation_state.return_value = None
                with mock.patch.object(context, "game_running", return_value=False), \
                     mock.patch.object(installer, "remove", return_value=[]) as remove:
                    context.uninstall_mod()
                    context.save_manager.restore.assert_not_called()
                    remove.assert_called_once_with(context.install_dir)

        asyncio.run(scenario())


class TestItemToast(unittest.TestCase):
    def _setup(self, context):
        context.slot = 1
        context.slot_info = {}
        context.player_names = {1: "Me", 2: "PlayerTwo"}

    def _segments(self, item_player: int, receiving: int, flags: int = 1,
                  location: int = 100, location_name: str = "Cortez Mission") -> list | None:
        async def scenario() -> list | None:
            with _fake_settings(""):
                from NetUtils import NetworkItem
                context = _context()
                self._setup(context)
                with mock.patch.object(context.item_names, "lookup_in_slot",
                                       return_value="Progressive Cortez"), \
                     mock.patch.object(context.location_names, "lookup_in_slot",
                                       return_value=location_name):
                    return context._item_toast_segments(
                        {"type": "ItemSend", "receiving": receiving,
                         "item": NetworkItem(42, location, item_player, flags)})

        return asyncio.run(scenario())

    def _text(self, *args, **kwargs) -> str | None:
        # The sentence a row reads as, which is what the phrasing assertions are
        # about; the colours are asserted separately so a wording change and a
        # palette change cannot be mistaken for each other.
        segments = self._segments(*args, **kwargs)
        if segments is None:
            return None
        return "".join(text for text, color in segments
                       if color != protocol.TOAST_NEWLINE)

    def test_found_own_item(self) -> None:
        self.assertEqual(self._text(1, 1),
                         "You found your Progressive Cortez(Cortez Mission)")

    def test_sent_to_another_player(self) -> None:
        self.assertEqual(self._text(1, 2),
                         "You sent Progressive Cortez to PlayerTwo(Cortez Mission)")

    def test_received_from_another_player(self) -> None:
        self.assertEqual(self._text(2, 1),
                         "You received Progressive Cortez from PlayerTwo(Cortez Mission)")

    def test_between_two_other_players_is_not_a_row(self) -> None:
        self.assertIsNone(self._segments(2, 3))

    def test_our_own_slot_keeps_the_own_slot_role(self) -> None:
        # The word standing in for our slot carries the colour Archipelago gives
        # the player's own name, which is the whole reason the wording can be
        # second person without losing the role.
        for item_player, receiving in ((1, 1), (1, 2), (2, 1)):
            segments = self._segments(item_player, receiving)
            self.assertEqual(segments[0], ("You", protocol.TOAST_OWN_SLOT))

    def test_the_location_is_its_own_line_and_its_own_colour(self) -> None:
        segments = self._segments(1, 1)
        self.assertIn(protocol.toast_newline(), segments)
        # Everything after the break is the parenthesised location.
        tail = segments[segments.index(protocol.toast_newline()) + 1:]
        self.assertEqual(tail, [("(", protocol.TOAST_CONNECTIVE),
                                ("Cortez Mission", protocol.TOAST_LOCATION),
                                (")", protocol.TOAST_CONNECTIVE)])

    def test_a_row_with_no_location_has_no_second_line(self) -> None:
        # A cheat-sent item has no location, and then there is nothing to name.
        segments = self._segments(1, 1, location=0)
        self.assertNotIn(protocol.toast_newline(), segments)
        self.assertEqual(self._text(1, 1, location=0),
                         "You found your Progressive Cortez")

    def test_every_colour_is_one_the_mod_knows(self) -> None:
        for item_player, receiving in ((1, 1), (1, 2), (2, 1)):
            for _text, color in self._segments(item_player, receiving):
                self.assertIn(color, protocol.TOAST_COLORS)

    def test_the_item_colour_follows_archipelagos_own_priority(self) -> None:
        # progression, then useful, then trap, then filler, which is what
        # NetUtils.py's own parser does. Deliberately not trap-first: a colour
        # disagreeing with the client window is worse than a wrong emphasis.
        cases = {
            0b001: protocol.TOAST_PROGRESSION,
            0b010: protocol.TOAST_USEFUL,
            0b100: protocol.TOAST_TRAP,
            0b011: protocol.TOAST_PROGRESSION,
            0b110: protocol.TOAST_USEFUL,
            0b101: protocol.TOAST_PROGRESSION,
        }
        for flags, expected in cases.items():
            segments = self._segments(1, 2, flags=flags)
            item = next(color for text, color in segments
                        if text == "Progressive Cortez")
            self.assertEqual(item, expected, f"flags {flags:#05b}")

    def test_an_unclassified_item_of_ours_recovers_its_class(self) -> None:
        # /send and !getitem build a NetworkItem whose flags default to 0, so
        # every one of our own items would otherwise read as filler. An item we
        # only route onward cannot be recovered, since the table is ours alone.
        from ... import items
        name = next(iter(items.ITEM_CLASSIFICATIONS))
        recovered = int(items.ITEM_CLASSIFICATIONS[name])

        async def scenario() -> tuple[str, str]:
            with _fake_settings(""):
                from NetUtils import NetworkItem
                context = _context()
                self._setup(context)
                with mock.patch.object(context.item_names, "lookup_in_slot",
                                       return_value=name), \
                     mock.patch.object(context.location_names, "lookup_in_slot",
                                       return_value="Somewhere"):
                    mine = context._item_toast_segments(
                        {"type": "ItemSend", "receiving": 1,
                         "item": NetworkItem(42, 100, 2, 0)})
                    theirs = context._item_toast_segments(
                        {"type": "ItemSend", "receiving": 2,
                         "item": NetworkItem(42, 100, 1, 0)})
            mine_color = next(c for t, c in mine if t == name)
            theirs_color = next(c for t, c in theirs if t == name)
            return mine_color, theirs_color

        mine_color, theirs_color = asyncio.run(scenario())
        expected = {0b001: protocol.TOAST_PROGRESSION,
                    0b010: protocol.TOAST_USEFUL,
                    0b100: protocol.TOAST_TRAP}
        wanted = protocol.TOAST_FILLER
        for bit, color in expected.items():
            if recovered & bit:
                wanted = color
                break
        self.assertEqual(mine_color, wanted)
        self.assertEqual(theirs_color, protocol.TOAST_FILLER)

    def test_send_toast_only_when_the_mod_is_connected(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                row = [("hi", protocol.TOAST_CONNECTIVE)]
                with mock.patch.object(type(context.bridge), "connected",
                                       new_callable=mock.PropertyMock) as connected, \
                     mock.patch.object(context.bridge, "send_toast") as send_toast:
                    connected.return_value = False
                    await context._send_toast(row)
                    send_toast.assert_not_called()
                    connected.return_value = True
                    await context._send_toast(row)
                    send_toast.assert_awaited_once_with(row)

        asyncio.run(scenario())

    def test_on_print_json_toasts_my_event_and_ignores_others(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                from NetUtils import NetworkItem
                context = _context()
                self._setup(context)
                with mock.patch.object(context, "_schedule") as schedule, \
                     mock.patch.object(context, "_send_toast", mock.Mock()), \
                     mock.patch.object(context, "_item_toast_segments",
                                       return_value=[("X", protocol.TOAST_CONNECTIVE)]):
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


class TestStatusCounts(unittest.TestCase):
    def test_sends_the_counts_the_mod_cannot_work_out(self) -> None:
        # The seed's location total is the client's to know: the mod is told
        # every completion global it watches, not which of them this seed made
        # into locations.
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                context.slot = 1
                context.checked_locations = {542000000, 542000001}
                context.missing_locations = {542000002}
                context.items_received = [object(), object(), object()]
                with mock.patch.object(type(context.bridge), "connected",
                                       new_callable=mock.PropertyMock) as connected, \
                     mock.patch.object(context.bridge, "send_status") as send_status, \
                     mock.patch.object(context, "_goal_rows", return_value=[]), \
                     mock.patch.object(context, "_strand_rows", return_value=[]), \
                     mock.patch.object(context, "_goal_reached", return_value=False):
                    connected.return_value = False
                    await context._send_status()
                    send_status.assert_not_called()
                    connected.return_value = True
                    await context._send_status()
                    send_status.assert_awaited_once_with(2, 3, 3, False, [], [],
                                                        False)
                    # A room the server already has finished counts as finished
                    # even with nothing left for the goal check to evaluate.
                    context.finished_game = True
                    send_status.reset_mock()
                    await context._send_status()
                    send_status.assert_awaited_once_with(2, 3, 3, True, [], [],
                                                        False)

        asyncio.run(scenario())

    def test_nothing_is_sent_before_ap_connects(self) -> None:
        # Zeroes would reach the page as counts and read as a seed with nothing in
        # it, which is worse than the page saying it has heard nothing.
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                context.slot = None
                with mock.patch.object(type(context.bridge), "connected",
                                       new_callable=mock.PropertyMock) as connected, \
                     mock.patch.object(context.bridge, "send_status") as send_status:
                    connected.return_value = True
                    await context._send_status()
                    send_status.assert_not_called()

        asyncio.run(scenario())

    def test_received_name_counts_counts_by_name(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                from NetUtils import NetworkItem
                context = _context()
                context.slot = 1
                context.items_received = [NetworkItem(1, 1, 1, 0),
                                          NetworkItem(1, 1, 1, 0),
                                          NetworkItem(2, 1, 1, 0)]
                with mock.patch.object(context.item_names, "lookup_in_slot",
                                       side_effect=lambda item, slot:
                                       {1: "Progressive Cortez",
                                        2: "Progressive Diaz"}[item]):
                    self.assertEqual(context._received_name_counts(),
                                     {"Progressive Cortez": 2, "Progressive Diaz": 1})

        asyncio.run(scenario())

    def test_goal_rows_name_the_goal_and_count_what_it_counts(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                from NetUtils import NetworkItem
                context = _context()
                context.slot_goal = "hidden_packages"
                context.hunt_item_id = 900
                context.hunt_required = 20
                context.items_received = [NetworkItem(900, 1, 1, 0)] * 7
                rows = context._goal_rows()
                self.assertEqual(rows[0][:2], ["Goal", "Package Fragments"])
                self.assertEqual(rows[1], ["Fragments", "7 of 20", False])
                # The hundred percent goal counts what is left instead.
                context.slot_goal = "hundred_percent"
                context.checked_locations = {1, 2}
                context.missing_locations = {3}
                self.assertEqual(context._goal_rows()[1], ["Checks left", "1", False])
                # And it counts only what the goal waits for: a location outside
                # the goal is not a check left, so the page cannot report a
                # number the goal is not holding on.
                context.goal_uncounted_locations = {3}
                self.assertEqual(context._goal_rows()[1], ["Checks left", "0", True])

        asyncio.run(scenario())

    def test_strand_rows_count_the_progressive_items_received(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                from ... import data
                context = _context()
                context.asi_config = {}
                with mock.patch.object(context, "_received_name_counts",
                                       return_value={"Progressive Cortez": 3}):
                    rows = {row[0]: row[1] for row in context._strand_rows()}
                self.assertEqual(rows["Cortez"],
                                 f"3 of {data.progressive_item_count('Cortez')}")
                # Every story giver is listed whether or not anything arrived yet.
                self.assertEqual(len(rows), len(data.STORY_GIVERS))
                self.assertTrue(rows["Diaz"].startswith("0 of "))
                # The venue strands only exist as items when properties are on.
                context.asi_config = {"enable_properties": True}
                with mock.patch.object(context, "_received_name_counts",
                                       return_value={}):
                    with_venues = context._strand_rows()
                self.assertEqual(len(with_venues),
                                 len(data.STORY_GIVERS) + len(data.VENUE_STRANDS))

        asyncio.run(scenario())

    def test_a_room_update_pushes_a_fresh_count(self) -> None:
        # A location checked by someone else moves the count with no item
        # arriving, which the item resync alone would not catch.
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                with mock.patch.object(context, "_schedule") as schedule, \
                     mock.patch.object(context, "_send_status",
                                       mock.Mock(return_value="status")), \
                     mock.patch.object(context, "_maybe_finish_goal"):
                    context.on_package("RoomUpdate", {})
                    schedule.assert_any_call("status")

        asyncio.run(scenario())


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


def _run_warp(configure) -> tuple[bool, bool]:
    # Build a context the way _run_goal does, apply the caller's goal state, and
    # report whether the goal is reached and whether the mod is asked for the
    # ending. The pair is what pins the distinction: two goals reach their goal
    # without ever asking.
    async def scenario() -> tuple[bool, bool]:
        with _fake_settings(""):
            context = _context()
            context.slot = 1
            configure(context)
            return context._goal_reached(), context._finale_warp()

    return asyncio.run(scenario())


class TestFinaleWarp(unittest.TestCase):
    """The hunt goal's ending: the last Package Fragment plays the finale.

    The ask rides the status frame, so it is repeated for as long as it holds
    rather than announced once, and the mod is the one that decides when the
    mission may start.
    """

    def test_the_hunt_asks_for_the_ending_once_it_is_met(self) -> None:
        def configure(context):
            context.slot_goal = "hidden_packages"
            context.hunt_item_id = 7
            context.hunt_required = 3
            context.items_received = _received(7, 3)

        self.assertEqual(_run_warp(configure), (True, True))

    def test_the_hunt_does_not_ask_below_the_threshold(self) -> None:
        def configure(context):
            context.slot_goal = "hidden_packages"
            context.hunt_item_id = 7
            context.hunt_required = 3
            context.items_received = _received(7, 2)

        self.assertEqual(_run_warp(configure), (False, False))

    def test_a_hunt_with_no_threshold_is_not_a_met_goal(self) -> None:
        # slot_data always carries the threshold (the option's floor is one), so
        # this pins the malformed case the fallback would otherwise clear: zero
        # required reads as met by any count, and the goal now plays the ending
        # rather than only reporting itself.
        def configure(context):
            context.slot_goal = "hidden_packages"
            context.hunt_item_id = 7
            context.hunt_required = 0
            context.items_received = _received(7, 1)

        self.assertEqual(_run_warp(configure), (False, False))

    def test_the_finale_goal_never_asks(self) -> None:
        # It is met by checking the finale itself, so the mission has been played
        # by the time it completes; asking would offer to play its ending again.
        def configure(context):
            context.slot_goal = "final_mission"
            context.final_location_id = 500
            context.checked_locations = {500}

        self.assertEqual(_run_warp(configure), (True, False))

    def test_the_hundred_percent_goal_ignores_locations_outside_it(self) -> None:
        # The world stopped counting the uncounted classes toward this goal, so
        # the client has to agree or it waits for checks the seed does not need.
        # With the ambient pickups on that is 110 of them, and one that cannot be
        # collected would hold the goal forever.
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                context.slot_goal = "hundred_percent"
                context.checked_locations = {1, 2}
                context.missing_locations = {50, 51}
                self.assertFalse(context._goal_reached())
                # Both outstanding locations are outside the goal: it is met.
                context.goal_uncounted_locations = {50, 51}
                self.assertTrue(context._goal_reached())
                # One counted location still missing holds it, so this is not
                # passing by ignoring everything.
                context.missing_locations = {50, 51, 9}
                self.assertFalse(context._goal_reached())

        asyncio.run(scenario())

    def test_the_hundred_percent_goal_never_asks(self) -> None:
        # Same reason: every location checked includes the finale's.
        def configure(context):
            context.slot_goal = "hundred_percent"
            context.checked_locations = {1, 2}
            context.missing_locations = set()

        self.assertEqual(_run_warp(configure), (True, False))

    def test_the_status_frame_carries_the_ask(self) -> None:
        async def scenario() -> None:
            with _fake_settings(""):
                context = _context()
                context.slot = 1
                context.slot_goal = "hidden_packages"
                context.hunt_item_id = 7
                context.hunt_required = 2
                context.items_received = _received(7, 2)
                context.checked_locations = {1}
                context.missing_locations = set()
                with mock.patch.object(type(context.bridge), "connected",
                                       new_callable=mock.PropertyMock) as connected, \
                     mock.patch.object(context.bridge, "send_status") as send_status, \
                     mock.patch.object(context, "_goal_rows", return_value=[]), \
                     mock.patch.object(context, "_strand_rows", return_value=[]):
                    connected.return_value = True
                    await context._send_status()
                    self.assertIs(send_status.await_args.args[-1], True)

        asyncio.run(scenario())


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


class TestProgressPercentage(unittest.TestCase):
    def test_publishes_the_percentage_to_the_data_store(self) -> None:
        async def scenario() -> dict:
            with _fake_settings(""):
                context = _context()
                context.team = 0
                context.slot = 3
                with mock.patch.object(
                    context, "send_msgs", new_callable=mock.AsyncMock,
                ) as send:
                    await context.on_bridge_progress(93)
                    return send.await_args.args[0][0]

        message = asyncio.run(scenario())
        self.assertEqual(message["cmd"], "Set")
        self.assertEqual(message["key"], "gta_vice_city_percentage_0_3")
        self.assertEqual(message["operations"],
                         [{"operation": "replace", "value": 93}])

    def test_remembers_a_report_the_server_never_saw(self) -> None:
        # The mod reports each number once. A report arriving while AP is away
        # goes nowhere, so the value has to survive in the context or the data
        # store keeps the one before it until the game's percentage moves again.
        async def scenario() -> tuple[int | None, dict]:
            with _fake_settings(""):
                context = _context()
                with mock.patch.object(
                    context, "send_msgs", new_callable=mock.AsyncMock,
                ) as send:
                    # No team or slot yet: this is the outage.
                    await context.on_bridge_progress(100)
                    self.assertEqual(send.await_count, 0)
                    context.team = 0
                    context.slot = 3
                    await context._publish_percentage()
                    return context.last_percentage, send.await_args.args[0][0]

        remembered, message = asyncio.run(scenario())
        self.assertEqual(remembered, 100)
        self.assertEqual(message["key"], "gta_vice_city_percentage_0_3")
        self.assertEqual(message["operations"],
                         [{"operation": "replace", "value": 100}])

    def test_connected_republishes_the_last_percentage(self) -> None:
        async def scenario() -> list[dict]:
            with _fake_settings(""):
                context = _context()
                context.team = 0
                context.slot = 3
                context.last_percentage = 93
                with mock.patch.object(
                    context, "setup_and_launch", new_callable=mock.AsyncMock,
                ), mock.patch.object(
                    context, "send_msgs", new_callable=mock.AsyncMock,
                ) as send:
                    context.on_package("Connected", {"slot_data": {}})
                    await asyncio.gather(*list(context._background_tasks))
                    return [call.args[0][0] for call in send.await_args_list]

        messages = asyncio.run(scenario())
        sets = [message for message in messages if message.get("cmd") == "Set"]
        self.assertEqual(len(sets), 1)
        self.assertEqual(sets[0]["key"], "gta_vice_city_percentage_0_3")
        self.assertEqual(sets[0]["operations"],
                         [{"operation": "replace", "value": 93}])

    def test_connected_says_nothing_with_no_report_yet(self) -> None:
        async def scenario() -> list[dict]:
            with _fake_settings(""):
                context = _context()
                context.team = 0
                context.slot = 3
                with mock.patch.object(
                    context, "setup_and_launch", new_callable=mock.AsyncMock,
                ), mock.patch.object(
                    context, "send_msgs", new_callable=mock.AsyncMock,
                ) as send:
                    context.on_package("Connected", {"slot_data": {}})
                    await asyncio.gather(*list(context._background_tasks))
                    return [call.args[0][0] for call in send.await_args_list]

        self.assertEqual(
            [message for message in asyncio.run(scenario())
             if message.get("cmd") == "Set"], [])

    def test_says_nothing_before_the_slot_is_known(self) -> None:
        # The mod can report a percentage while AP has not answered yet; there is
        # no key to write it under, so the report is dropped rather than landing
        # somewhere another slot would read.
        async def scenario() -> int:
            with _fake_settings(""):
                context = _context()
                self.assertIsNone(context.percentage_key())
                with mock.patch.object(
                    context, "send_msgs", new_callable=mock.AsyncMock,
                ) as send:
                    await context.on_bridge_progress(50)
                    return send.await_count

        self.assertEqual(asyncio.run(scenario()), 0)


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
