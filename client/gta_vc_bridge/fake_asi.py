"""A Python stand-in for the C++ ASI, speaking the mod side of the protocol.

It lets the bridge's framing, chunking, handshake, resync, and reconnect run
headless in pytest, with no game and no Archipelago server. It connects to the
bridge's listener, presents a seed hash, and exposes the messages it receives.
"""

from __future__ import annotations

import asyncio

from . import protocol


class FakeAsi:
    def __init__(self, host: str, port: int, presented_seed_hash: str = "") -> None:
        self._host = host
        self._port = port
        self._presented_seed_hash = presented_seed_hash
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._message_reader = protocol.MessageReader()
        self._message_writer = protocol.MessageWriter()
        self._pump_task: asyncio.Task | None = None
        self.inbox: asyncio.Queue[dict] = asyncio.Queue()
        self.handshake: dict | None = None

    async def connect(self) -> dict | None:
        """Connect, present the seed hash, and return the welcome or refused
        reply (None if the connection closed with no reply)."""
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
        self._pump_task = asyncio.create_task(self._pump())
        await self._send(protocol.hello_message(self._presented_seed_hash))
        self.handshake = await self.next_message()
        return self.handshake

    async def _pump(self) -> None:
        assert self._reader is not None
        try:
            while True:
                data = await self._reader.read(4096)
                if not data:
                    return
                for message in self._message_reader.feed(data):
                    self.inbox.put_nowait(message)
        except (ConnectionError, OSError, protocol.ProtocolError):
            return

    async def _send(self, message: dict) -> None:
        assert self._writer is not None
        for frame in self._message_writer.frames(message):
            self._writer.write(frame)
        await self._writer.drain()

    async def send_message(self, message: dict) -> None:
        """Send an arbitrary frame, for exercising malformed input in tests."""
        await self._send(message)

    async def send_check(self, location: int) -> None:
        await self._send(protocol.check_message(location))

    async def send_goal_reached(self) -> None:
        await self._send(protocol.goal_reached_message())

    async def next_message(self, timeout: float = 2.0) -> dict | None:
        try:
            return await asyncio.wait_for(self.inbox.get(), timeout)
        except TimeoutError:
            return None

    async def drain_messages(self, timeout: float = 0.2) -> list[dict]:
        """Collect every message currently queued, waiting briefly for more."""
        messages: list[dict] = []
        while True:
            message = await self.next_message(timeout)
            if message is None:
                return messages
            messages.append(message)

    async def close(self) -> None:
        if self._pump_task is not None:
            self._pump_task.cancel()
        if self._writer is not None:
            try:
                self._writer.close()
            except (ConnectionError, OSError):
                pass
