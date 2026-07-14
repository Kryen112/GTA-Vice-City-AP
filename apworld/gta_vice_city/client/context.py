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

from . import protocol
from .bridge import AsiBridge

DEFAULT_BRIDGE_PORT = 52300
logger = logging.getLogger("Client")


def looks_like_install(path: Path) -> bool:
    """A folder counts as a GTA Vice City install only if it holds gta-vc.exe.
    An unset UserFolderPath resolves to the Archipelago root, so a non-empty
    value is not enough on its own."""
    return (path / "gta-vc.exe").is_file()


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
        # The install folder, from host.yaml if it already holds gta-vc.exe.
        # A blank setting resolves to the Archipelago root, so it is validated,
        # not just checked for being non-empty.
        self.install_dir: Path | None = None
        folder = self._configured_folder()
        if folder and looks_like_install(Path(folder)):
            self.install_dir = Path(folder)
        # The ASI configuration from slot_data: item id -> unlock global, and
        # completion global -> location id. Captured on Connected.
        self.asi_config: dict = {}
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
                "completion_watch": slot_data.get("completion_watch", {}),
            }
            self._schedule(self.setup_and_launch())
        # A new Connected or a ReceivedItems update means the mod's view is
        # stale, so push a fresh resync. The bridge no-ops if the mod is not
        # connected; it also resyncs itself on every mod (re)connect.
        if cmd in ("Connected", "ReceivedItems"):
            self._schedule(self._resync_bridge())

    def _schedule(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

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
            )
        await self._resync_bridge()

    async def on_bridge_check(self, location: int) -> None:
        await self.send_msgs([{"cmd": "LocationChecks", "locations": [location]}])

    async def on_bridge_goal(self) -> None:
        if not self.finished_game:
            await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            self.finished_game = True

    def _configured_folder(self) -> str:
        from .. import GTAViceCityWorld
        return str(GTAViceCityWorld.settings.install_folder)

    def _auto_launch_enabled(self) -> bool:
        from .. import GTAViceCityWorld
        return bool(getattr(GTAViceCityWorld.settings, "auto_launch_game", False))

    async def setup_and_launch(self) -> None:
        """On connect: make sure an install folder is known (picker on first
        run), then auto-launch the game if that setting is on."""
        if not self.install_dir:
            if gui_enabled:
                await self.pick_install_dir()
            else:
                logger.warning("No install folder set. Use /setfolder, or set "
                               "gta_vice_city_options -> install_folder in host.yaml.")
        if not self.install_dir:
            return
        if not self.game_launched and self._auto_launch_enabled():
            self.launch_game()

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
            subprocess.Popen([str(executable)], cwd=str(executable.parent))
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
