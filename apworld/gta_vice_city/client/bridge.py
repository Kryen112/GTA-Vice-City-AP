"""The ASI-facing side of the bridge client: a localhost TCP listener.

Hosts one ASI connection at a time, performs the version and seed handshake,
and dispatches check and goal messages to injected callbacks. It has no
Archipelago dependency; the context module wires the callbacks and the expected
seed hash to the real AP connection. Assume the ASI disconnects and reconnects
at any time: on every successful handshake the caller pushes a full resync.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from . import protocol

# A connection that sends no hello within this many seconds is dropped, so a
# stalled half-open peer cannot accumulate.
HANDSHAKE_TIMEOUT_SECONDS = 30.0

SeedHashGetter = Callable[[], "str | None"]
CheckCallback = Callable[[int], Awaitable[None]]
GoalCallback = Callable[[], Awaitable[None]]
ConnectedCallback = Callable[["AsiBridge"], Awaitable[None]]
AppliedCallback = Callable[[int], Awaitable[None]]


async def _noop_applied(_index: int) -> None:
    return None


class AsiBridge:
    """A localhost listener the ASI connects to. One connection at a time; a
    new connection replaces any previous one."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        expected_seed_hash: SeedHashGetter,
        on_check: CheckCallback,
        on_goal_reached: GoalCallback,
        on_connected: ConnectedCallback,
        on_applied: AppliedCallback = _noop_applied,
        logger: logging.Logger | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._expected_seed_hash = expected_seed_hash
        self._on_check = on_check
        self._on_goal_reached = on_goal_reached
        self._on_connected = on_connected
        self._on_applied = on_applied
        self._logger = logger or logging.getLogger("Client")
        self._server: asyncio.AbstractServer | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._message_writer = protocol.MessageWriter()

    @property
    def port(self) -> int:
        # The bound port, resolved after start (useful when constructed with 0).
        if self._server is None:
            return self._port
        return self._server.sockets[0].getsockname()[1]

    @property
    def connected(self) -> bool:
        return self._writer is not None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_connection, self._host, self._port)

    async def stop(self) -> None:
        self._drop_connection()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def send(self, message: dict) -> None:
        writer = self._writer
        if writer is None:
            return
        try:
            for frame in self._message_writer.frames(message):
                writer.write(frame)
            await writer.drain()
        except (ConnectionError, OSError):
            # Only drop if this is still the current connection; a newer one may
            # have superseded it while we awaited the drain.
            if self._writer is writer:
                self._drop_connection()

    async def send_config(
        self, item_globals: dict, completion_watch: dict, item_effects: dict, config_globals: dict,
        package_coords: dict, pickup_layout: list, mainland_routes: list,
        content_district_globals: dict, content_districts: list,
    ) -> None:
        await self.send(
            protocol.config_message(
                item_globals, completion_watch, item_effects, config_globals, package_coords,
                pickup_layout, mainland_routes, content_district_globals, content_districts,
            )
        )

    async def send_items(self, items: list[tuple[int, int]]) -> None:
        await self.send(protocol.items_message(items))

    async def send_checked(self, locations: list[int]) -> None:
        await self.send(protocol.checked_message(locations))

    async def send_toast(self, text: str) -> None:
        await self.send(protocol.toast_message(text))

    def _drop_connection(self) -> None:
        writer = self._writer
        self._writer = None
        if writer is not None:
            try:
                writer.close()
            except (ConnectionError, OSError):
                pass

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        message_reader = protocol.MessageReader()
        try:
            accepted = await self._handshake(reader, writer, message_reader)
            if not accepted:
                return
            # Only now supersede any previous connection: a refused or stalled
            # connect must never evict a healthy live one.
            self._drop_connection()
            self._writer = writer
            await self._on_connected(self)
            await self._read_loop(reader, message_reader)
        except protocol.ProtocolError as error:
            self._logger.warning("GTA Vice City bridge: dropping the mod connection: %s", error)
        except (ConnectionError, OSError):
            pass
        finally:
            if self._writer is writer:
                self._writer = None
            try:
                writer.close()
            except (ConnectionError, OSError):
                pass

    async def _handshake(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        message_reader: protocol.MessageReader,
    ) -> bool:
        try:
            hello = await asyncio.wait_for(
                self._read_one(reader, message_reader), HANDSHAKE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return False
        if hello is None:
            return False
        if hello.get("type") != protocol.HELLO:
            await self._refuse(writer, "expected a hello frame first")
            return False
        if hello.get("protocol_version") != protocol.PROTOCOL_VERSION:
            await self._refuse(
                writer,
                f"protocol version mismatch: the mod speaks "
                f"{hello.get('protocol_version')}, the client speaks {protocol.PROTOCOL_VERSION}",
            )
            return False
        expected = self._expected_seed_hash()
        if expected is None:
            await self._refuse(writer, "connect the client to the Archipelago server first")
            return False
        presented = hello.get("seed_hash") or ""
        if presented and presented != expected:
            await self._refuse(
                writer,
                "this save belongs to a different multiworld; start a new game for this seed",
            )
            return False
        await self._write(writer, protocol.welcome_message(expected))
        return True

    async def _refuse(self, writer: asyncio.StreamWriter, reason: str) -> None:
        self._logger.info("GTA Vice City bridge refused the mod: %s", reason)
        await self._write(writer, protocol.refused_message(reason))

    async def _write(self, writer: asyncio.StreamWriter, message: dict) -> None:
        for frame in self._message_writer.frames(message):
            writer.write(frame)
        await writer.drain()

    async def _read_one(
        self, reader: asyncio.StreamReader, message_reader: protocol.MessageReader,
    ) -> dict | None:
        while True:
            data = await reader.read(4096)
            if not data:
                return None
            messages = message_reader.feed(data)
            if messages:
                return messages[0]

    async def _read_loop(
        self, reader: asyncio.StreamReader, message_reader: protocol.MessageReader,
    ) -> None:
        while True:
            data = await reader.read(4096)
            if not data:
                return
            for message in message_reader.feed(data):
                await self._dispatch(message)

    async def _dispatch(self, message: dict) -> None:
        message_type = message.get("type")
        try:
            if message_type == protocol.CHECK:
                await self._on_check(int(message["location"]))
            elif message_type == protocol.GOAL_REACHED:
                await self._on_goal_reached()
            elif message_type == protocol.APPLIED:
                await self._on_applied(int(message["index"]))
            else:
                self._logger.debug("GTA Vice City bridge ignoring message: %r", message_type)
        except (KeyError, TypeError, ValueError) as error:
            raise protocol.ProtocolError(f"malformed {message_type} message: {error}") from error
