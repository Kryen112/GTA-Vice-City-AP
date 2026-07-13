"""The Archipelago-facing half of the bridge client.

Subclasses CommonContext to speak the real AP protocol against a hosted seed,
and hosts the AsiBridge that the GTA: Vice City mod connects to. It bridges the
two: AP received-items and checked-locations resync down to the mod, and mod
check and goal events up to AP. The protocol and framing live in bridge.py and
protocol.py, which are tested headless; this module is the live wiring, verified
against a real server and game.

Run from inside the Archipelago repo during development:
    py -3.12 -m gta_vc_bridge.context --connect localhost:38281 --name Player1
with the client package directory on PYTHONPATH.
"""

from __future__ import annotations

import asyncio
import logging
import warnings

# Silence the setuptools deprecation AP emits when it imports pkg_resources,
# before importing CommonClient so the filter is already in place.
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

from CommonClient import CommonContext, get_base_parser, gui_enabled, server_loop
from NetUtils import ClientStatus

from . import protocol
from .bridge import AsiBridge

DEFAULT_BRIDGE_PORT = 52300
logger = logging.getLogger("Client")


class GTAViceCityContext(CommonContext):
    game = "Grand Theft Auto Vice City"
    # Receive our own items, starting inventory, and items from other worlds.
    items_handling = 0b111

    def __init__(self, server_address: str | None, password: str | None, bridge_port: int) -> None:
        super().__init__(server_address, password)
        self.bridge_port = bridge_port
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
        # The mod just connected and was welcomed; give it the full state.
        await self._resync_bridge()

    async def on_bridge_check(self, location: int) -> None:
        await self.send_msgs([{"cmd": "LocationChecks", "locations": [location]}])

    async def on_bridge_goal(self) -> None:
        if not self.finished_game:
            await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            self.finished_game = True


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
        parsed = parser.parse_args(args)
        context = GTAViceCityContext(parsed.connect, parsed.password, parsed.bridge_port)
        await _run(context)

    import colorama
    colorama.just_fix_windows_console()
    asyncio.run(main())
    colorama.deinit()


if __name__ == "__main__":
    import sys
    launch(*sys.argv[1:])
