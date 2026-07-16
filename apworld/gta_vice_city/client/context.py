"""The Archipelago-facing half of the bridge client.

Subclasses CommonContext to speak the real AP protocol against a hosted seed,
and hosts the AsiBridge that the GTA: Vice City mod connects to. It bridges the
two: AP received-items and checked-locations resync down to the mod, and mod
check and goal events up to AP. The protocol and framing live in bridge.py and
protocol.py, which are tested headless; this module is the live wiring, verified
against a real server and game.

Normally launched from the Archipelago Launcher's "GTA Vice City Client"
button. During development, from inside the Archipelago repo:
    python -m worlds.gta_vice_city.client.context --connect localhost:38281 --name Player1

On connect it makes sure the install folder is known, opening a folder picker
the first time and saving the choice to host.yaml, then launches gta-vc.exe
when auto-launch is on. The /play command launches the game on demand and
/setfolder re-picks the install folder.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import warnings
from pathlib import Path

# Silence the setuptools deprecation AP emits when it imports pkg_resources,
# before importing CommonClient so the filter is already in place.
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import Utils
from CommonClient import (
    ClientCommandProcessor,
    CommonContext,
    get_base_parser,
    gui_enabled,
    handle_url_arg,
    server_loop,
)
from NetUtils import ClientStatus

from . import protocol, saves
from .bridge import AsiBridge
from .saves import SaveManager

DEFAULT_BRIDGE_PORT = 52300
logger = logging.getLogger("Client")


def looks_like_install(path: Path) -> bool:
    """A folder counts as a GTA Vice City install only if it holds gta-vc.exe.
    An unset UserFolderPath resolves to the Archipelago root, so a non-empty
    value is not enough on its own."""
    return (path / "gta-vc.exe").is_file()


def game_process_running() -> bool:
    """Whether any gta-vc.exe runs, including one the client did not launch."""
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq gta-vc.exe", "/NH"],
            capture_output=True, text=True, timeout=3, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        # Callers guard destructive save moves, so an unanswerable check fails
        # closed: assume the game is running.
        return True
    return "gta-vc.exe" in result.stdout


class GTAViceCityCommandProcessor(ClientCommandProcessor):
    def _cmd_play(self) -> None:
        """Launch GTA Vice City, or relaunch it after quitting."""
        self.ctx.launch_game()

    def _cmd_setfolder(self, path: str = "") -> None:
        """Choose the GTA Vice City install folder (the one holding gta-vc.exe)
        and save it to host.yaml. With no argument, opens a folder picker."""
        chosen = path if path and Path(path).is_dir() else Utils.open_directory(
            "Select the GTA Vice City install folder (holds gta-vc.exe)",
            suggest=str(self.ctx.install_dir or ""))
        if not chosen:
            self.output("No folder selected.")
            return
        if not looks_like_install(Path(chosen)):
            self.output("That folder has no gta-vc.exe. Pick the GTA Vice City "
                        "install folder.")
            return
        self.ctx.set_install_dir(chosen)
        self.output(f"Install folder set to {self.ctx.install_dir} (saved to host.yaml).")

    def _cmd_restore(self) -> None:
        """Restore your normal saves, undoing Archipelago save isolation. Close
        the game first."""
        self.ctx.restore_saves()

    def _cmd_installmod(self) -> None:
        """Install or update the bundled GTA Vice City mod in the install
        folder. Close the game first."""
        self.ctx.install_mod()


class GTAViceCityContext(CommonContext):
    game = "Grand Theft Auto Vice City"
    # Receive our own items, starting inventory, and items from other worlds.
    items_handling = 0b111
    command_processor = GTAViceCityCommandProcessor

    def __init__(self, server_address: str | None, password: str | None,
                 bridge_port: int, slot_name: str | None = None) -> None:
        super().__init__(server_address, password)
        if slot_name:
            self.auth = slot_name
        self.bridge_port = bridge_port
        self.game_launched = False
        self.game_process: subprocess.Popen | None = None
        # Set by /restore, so a reconnect does not swap the normal saves back
        # out after the player asked for them.
        self.isolation_suspended = False
        # The install folder, from host.yaml if it already holds gta-vc.exe.
        # A blank setting resolves to the Archipelago root, so it is validated,
        # not just checked for being non-empty.
        self.install_dir: Path | None = None
        folder = self._configured_folder()
        if folder and looks_like_install(Path(folder)):
            self.install_dir = Path(folder)
        # Save isolation works on the GTA Vice City User Files folder, which
        # lives under Documents, apart from the install folder.
        user_files = saves.user_files_directory()
        self.save_manager: SaveManager | None = SaveManager(user_files) if user_files else None
        # The ASI configuration from slot_data: item id -> unlock global, and
        # completion global -> location id. Captured on Connected.
        self.asi_config: dict = {}
        # The hidden-packages hunt goal is detected on the client by counting
        # received copies of the macguffin. None unless that is the goal.
        self.hunt_item_id: int | None = None
        self.hunt_required = 0
        # Hold references to fire-and-forget tasks so they are not
        # garbage-collected mid-flight.
        self._background_tasks: set[asyncio.Task] = set()
        self.bridge = AsiBridge(
            "127.0.0.1", bridge_port,
            expected_seed_hash=self.expected_seed_hash,
            on_check=self.on_bridge_check,
            on_goal_reached=self.on_bridge_goal,
            on_connected=self.on_bridge_connected,
            logger=logger,
        )

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        if not self.auth:
            await self.get_username()
        await self.send_connect()

    def expected_seed_hash(self) -> str | None:
        # The identity the mod stamps into its save and presents on connect.
        # Available once AP has sent RoomInfo (seed_name) and Connected (slot).
        if not self.seed_name or self.slot is None:
            return None
        slot_name = self.player_names.get(self.slot, str(self.slot))
        return protocol.seed_hash(self.seed_name, slot_name)

    def on_package(self, cmd: str, args: dict) -> None:
        # Capture the seed name from RoomInfo. CommonContext does not populate
        # it, and the seed hash the mod handshake needs is derived from it.
        if cmd == "RoomInfo":
            self.seed_name = args.get("seed_name")
        # Capture the ASI configuration from slot_data on connect, then make
        # sure the install folder is known and auto-launch the game.
        if cmd == "Connected":
            slot_data = args.get("slot_data") or {}
            self.asi_config = {
                "item_globals": slot_data.get("item_globals", {}),
                "item_effects": slot_data.get("item_effects", {}),
                "config_globals": slot_data.get("config_globals", {}),
                "completion_watch": slot_data.get("completion_watch", {}),
                "package_coords": slot_data.get("package_coords", {}),
            }
            if slot_data.get("goal") == "hidden_packages":
                self.hunt_item_id = slot_data.get("hidden_package_item_id")
                self.hunt_required = slot_data.get("hidden_packages_required", 0)
            self._schedule(self.setup_and_launch())
        # A new Connected or a ReceivedItems update means the mod's view is
        # stale, so push a fresh resync. The bridge no-ops if the mod is not
        # connected; it also resyncs itself on every mod (re)connect. A received
        # item can also complete the hidden-packages hunt.
        if cmd in ("Connected", "ReceivedItems"):
            self._schedule(self._resync_bridge())
            self._maybe_finish_hunt()

    def _schedule(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def on_print_json(self, args: dict) -> None:
        super().on_print_json(args)
        # Turn each item movement that concerns this player into an in-game
        # toast, so completing a check shows what it sent or found.
        if args.get("type") != "ItemSend" or self.is_uninteresting_item_send(args):
            return
        text = self._item_toast_text(args)
        if text:
            self._schedule(self._send_toast(text))

    def _item_toast_text(self, args: dict) -> str | None:
        item = args["item"]
        receiving = args["receiving"]
        item_name = self.item_names.lookup_in_slot(item.item, receiving)
        found_it = self.slot_concerns_self(item.player)
        got_it = self.slot_concerns_self(receiving)
        if found_it and got_it:
            return f"You found your {item_name}"
        if found_it:
            return f"You sent {item_name} to {self.player_names.get(receiving, str(receiving))}"
        if got_it:
            return f"{self.player_names.get(item.player, str(item.player))} found your {item_name}"
        return None

    async def _send_toast(self, text: str) -> None:
        if self.bridge.connected:
            await self.bridge.send_toast(text)

    def _received_item_pairs(self) -> list[tuple[int, int]]:
        return [(index, item.item) for index, item in enumerate(self.items_received)]

    async def _resync_bridge(self) -> None:
        if not self.bridge.connected:
            return
        await self.bridge.send_items(self._received_item_pairs())
        await self.bridge.send_checked(sorted(self.checked_locations))

    async def on_bridge_connected(self, _bridge: AsiBridge) -> None:
        # The mod just connected and was welcomed; give it its configuration
        # then the full state.
        if self.asi_config:
            await self.bridge.send_config(
                self.asi_config.get("item_globals", {}),
                self.asi_config.get("completion_watch", {}),
                self.asi_config.get("item_effects", {}),
                self.asi_config.get("config_globals", {}),
                self.asi_config.get("package_coords", {}),
            )
        await self._resync_bridge()

    async def on_bridge_check(self, location: int) -> None:
        await self.send_msgs([{"cmd": "LocationChecks", "locations": [location]}])

    async def on_bridge_goal(self) -> None:
        await self._finish_goal()

    async def _finish_goal(self) -> None:
        if self.finished_game:
            return
        # Mark finished before awaiting the send: a burst of ReceivedItems can
        # schedule this more than once, and the flag set with no await before it
        # keeps the check-and-set atomic so the goal is reported exactly once.
        self.finished_game = True
        await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

    def _maybe_finish_hunt(self) -> None:
        # The hidden-packages goal is met when enough Hidden Package items have
        # been received, wherever in the multiworld they were found.
        if self.finished_game or self.hunt_item_id is None:
            return
        received = sum(1 for item in self.items_received if item.item == self.hunt_item_id)
        if received >= self.hunt_required:
            self._schedule(self._finish_goal())

    def _configured_folder(self) -> str:
        from .. import GTAViceCityWorld
        return str(GTAViceCityWorld.settings.install_folder)

    def _auto_launch_enabled(self) -> bool:
        from .. import GTAViceCityWorld
        return bool(getattr(GTAViceCityWorld.settings, "auto_launch_game", False))

    def _isolate_saves_enabled(self) -> bool:
        from .. import GTAViceCityWorld
        return bool(getattr(GTAViceCityWorld.settings, "isolate_saves", False))

    def _auto_install_mod_enabled(self) -> bool:
        from .. import GTAViceCityWorld
        return bool(getattr(GTAViceCityWorld.settings, "auto_install_mod", False))

    async def setup_and_launch(self) -> None:
        """On connect: isolate this seed's saves, make sure an install folder is
        known (picker on first run), install the mod, then auto-launch the game
        if that setting is on."""
        # Isolation moves save files, so it runs on the loop (serialized with
        # other connects) rather than racing in a thread; its one blocking step,
        # the tasklist check, is bounded to a few seconds.
        self._isolate_saves()
        if not self.install_dir:
            if gui_enabled:
                await self.pick_install_dir()
            else:
                logger.warning("No install folder set. Use /setfolder, or set "
                               "gta_vice_city_options -> install_folder in host.yaml.")
        if not self.install_dir:
            return
        if self._auto_install_mod_enabled():
            self.install_mod(announce_current=False)
        if not self.game_launched and self._auto_launch_enabled():
            self.launch_game()

    def install_mod(self, announce_current: bool = True) -> None:
        from .. import installer
        if not self.install_dir:
            logger.warning("No install folder set. Use /setfolder first.")
            return
        try:
            # Check first, so a current mod (or an apworld with no payload) is a
            # silent no-op and never warns about a running game needlessly.
            if installer.mod_is_current(self.install_dir):
                if announce_current:
                    logger.info("The mod is already up to date.")
                return
            if self.game_running():
                logger.warning("Close the game before installing the mod.")
                return
            for line in installer.deploy(self.install_dir):
                logger.info(line)
        except Exception as error:
            logger.error(f"Could not install the mod ({error}).")

    def game_running(self) -> bool:
        # The client-launched process is authoritative, but a game the player
        # started themselves counts too: swapping saves under a live game
        # corrupts state.
        if self.game_process is not None and self.game_process.poll() is None:
            return True
        return game_process_running()

    def _isolate_saves(self) -> None:
        """Swap in this seed's own save set, unless disabled. Skipped while the
        game runs, so saves are never swapped under a live game."""
        if not (self.save_manager and self._isolate_saves_enabled()):
            return
        if self.isolation_suspended:
            return
        if not self.seed_name:
            return
        already_on_seed = (
            self.save_manager.is_isolated()
            and self.save_manager.active_seed() == saves.seed_folder_name(self.seed_name))
        if self.game_running() and not already_on_seed:
            logger.warning("The game is running, so save isolation was skipped. Close it "
                           "and reconnect to isolate this seed's saves.")
            return
        try:
            logger.info(self.save_manager.isolate(self.seed_name))
        except Exception as error:
            logger.error(f"Save isolation failed ({error}); using the current saves as-is.")

    def restore_saves(self) -> None:
        if not self.save_manager:
            logger.warning("No GTA Vice City User Files folder found to restore saves in.")
            return
        if self.game_running():
            logger.warning("Close the game before restoring your normal saves.")
            return
        try:
            logger.info(self.save_manager.restore())
            # Do not re-isolate on the next reconnect this session, or the
            # restore would silently swap the normal saves back out.
            self.isolation_suspended = True
        except Exception as error:
            logger.error(f"Could not restore saves ({error}); resolve by hand.")

    async def pick_install_dir(self) -> None:
        """Open a folder picker off the event loop and save the choice."""
        loop = asyncio.get_event_loop()
        chosen = await loop.run_in_executor(
            None, Utils.open_directory,
            "Select the GTA Vice City install folder (holds gta-vc.exe)")
        if not chosen:
            logger.warning("No install folder chosen. Use /setfolder to try again, or "
                           "set gta_vice_city_options -> install_folder in host.yaml.")
            return
        if not looks_like_install(Path(chosen)):
            logger.warning(f"'{chosen}' has no gta-vc.exe, so it is not a GTA Vice City "
                           "install folder. Not saved; use /setfolder to try again.")
            return
        self.set_install_dir(chosen)
        logger.info(f"Install folder set to {self.install_dir} (saved to host.yaml).")

    def set_install_dir(self, path: str) -> None:
        self.install_dir = Path(path)
        self._save_install_folder(str(self.install_dir))

    def _save_install_folder(self, path: str) -> None:
        """Persist the install folder to host.yaml, so the player picks it once."""
        from .. import GTAViceCityWorld
        try:
            import settings as ap_settings
            current = GTAViceCityWorld.settings.install_folder
            GTAViceCityWorld.settings.install_folder = type(current)(path)
            ap_settings.get_settings().save()
        except Exception as error:
            logger.warning(f"Could not save the install folder to host.yaml ({error}); "
                           "set it there yourself to avoid picking it again.")

    def launch_game(self) -> None:
        if not self.install_dir:
            logger.warning("No install folder set. Use /setfolder first.")
            return
        executable = self.install_dir / "gta-vc.exe"
        if not executable.is_file():
            logger.error(f"gta-vc.exe not found at {executable}.")
            return
        try:
            self.game_process = subprocess.Popen([str(executable)], cwd=str(executable.parent))
            self.game_launched = True
            logger.info("Launched GTA Vice City.")
        except OSError as error:
            logger.error("Could not launch GTA Vice City: %s", error)


async def _run(context: GTAViceCityContext) -> None:
    await context.bridge.start()
    logger.info("GTA Vice City bridge listening on 127.0.0.1:%d", context.bridge.port)
    context.server_task = asyncio.create_task(server_loop(context), name="server loop")
    if gui_enabled:
        context.run_gui()
    context.run_cli()
    await context.exit_event.wait()
    await context.bridge.stop()
    await context.shutdown()


def launch(*args: str) -> None:
    async def main() -> None:
        parser = get_base_parser(description="GTA: Vice City Archipelago bridge client.")
        parser.add_argument("--bridge_port", type=int, default=DEFAULT_BRIDGE_PORT,
                            help="Localhost port the GTA Vice City mod connects to.")
        parser.add_argument("--name", default=None, help="Slot name to connect as.")
        parser.add_argument("url", nargs="?", help="Archipelago connection url.")
        parsed = parser.parse_args(args)
        # A WebHost archipelago:// link arrives as the url positional; fold it
        # into connect, name, and password.
        parsed = handle_url_arg(parsed, parser=parser)
        context = GTAViceCityContext(parsed.connect, parsed.password, parsed.bridge_port, parsed.name)
        await _run(context)

    import colorama
    colorama.just_fix_windows_console()
    asyncio.run(main())
    colorama.deinit()


if __name__ == "__main__":
    import sys
    launch(*sys.argv[1:])
