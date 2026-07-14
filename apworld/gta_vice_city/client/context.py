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

On connect it launches gta-vc.exe from the install folder set in host.yaml (if
auto-launch is on), and the /play command launches it on demand.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import warnings

# Silence the setuptools deprecation AP emits when it imports pkg_resources,
# before importing CommonClient so the filter is already in place.
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

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


class GTAViceCityCommandProcessor(ClientCommandProcessor):
    def _cmd_play(self) -> bool:
        """Launch GTA Vice City."""
        self.ctx.launch_game(forced=True)
        return True


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
        self._game_launched = False
        # The ASI configuration from slot_data: item id -> unlock global, and
        # completion global -> location id. Captured on Connected.
        self.asi_config: dict = {}
        # Hold references to fire-and-forget resync tasks so they are not
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
        # Capture the ASI configuration from slot_data on connect, and launch
        # the game if configured to.
        if cmd == "Connected":
            slot_data = args.get("slot_data") or {}
            self.asi_config = {
                "item_globals": slot_data.get("item_globals", {}),
                "completion_watch": slot_data.get("completion_watch", {}),
            }
            if self._auto_launch_enabled():
                self.launch_game()
        # A new Connected or a ReceivedItems update means the mod's view is
        # stale, so push a fresh resync. The bridge no-ops if the mod is not
        # connected; it also resyncs itself on every mod (re)connect.
        if cmd in ("Connected", "ReceivedItems"):
            task = asyncio.create_task(self._resync_bridge())
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

    def _game_executable(self) -> str | None:
        from .. import GTAViceCityWorld
        folder = str(getattr(GTAViceCityWorld.settings, "install_folder", "")).strip()
        if not folder:
            return None
        executable = os.path.join(folder, "gta-vc.exe")
        return executable if os.path.isfile(executable) else None

    def _auto_launch_enabled(self) -> bool:
        from .. import GTAViceCityWorld
        return bool(getattr(GTAViceCityWorld.settings, "auto_launch_game", False))

    def launch_game(self, forced: bool = False) -> None:
        if self._game_launched and not forced:
            return
        executable = self._game_executable()
        if executable is None:
            logger.info("Set the GTA Vice City install folder in host.yaml to launch the game, "
                        "or start gta-vc.exe yourself.")
            return
        try:
            subprocess.Popen([executable], cwd=os.path.dirname(executable))
            self._game_launched = True
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
