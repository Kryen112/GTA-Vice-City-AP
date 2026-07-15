"""Bridge and fake-ASI integration tests, run headless with asyncio.run.

Covers the handshake, resync on connect, check and goal dispatch, seed and
version refusal, the not-connected-to-AP refusal, reconnect resync, and a
chunked large resync.
"""

from __future__ import annotations

import asyncio
import unittest

from .. import protocol
from ..bridge import AsiBridge
from .fake_asi import FakeAsi

HOST = "127.0.0.1"


class Recorder:
    def __init__(
        self,
        expected_hash: str | None,
        resync_items: list[tuple[int, int]] | None = None,
        resync_checked: list[int] | None = None,
        config: dict | None = None,
    ) -> None:
        self.expected_hash = expected_hash
        self.resync_items = resync_items or []
        self.resync_checked = resync_checked or []
        self.config = config
        self.checks: list[int] = []
        self.goals = 0
        self.connected = 0

    def seed_hash(self) -> str | None:
        return self.expected_hash

    async def on_check(self, location: int) -> None:
        self.checks.append(location)

    async def on_goal(self) -> None:
        self.goals += 1

    async def on_connected(self, bridge: AsiBridge) -> None:
        self.connected += 1
        if self.config is not None:
            await bridge.send_config(
                self.config["item_globals"], self.config["completion_watch"],
                self.config.get("item_effects", {}), self.config.get("config_globals", {}),
            )
        await bridge.send_items(self.resync_items)
        await bridge.send_checked(self.resync_checked)


def _make_bridge(recorder: Recorder) -> AsiBridge:
    return AsiBridge(
        HOST, 0,
        expected_seed_hash=recorder.seed_hash,
        on_check=recorder.on_check,
        on_goal_reached=recorder.on_goal,
        on_connected=recorder.on_connected,
    )


async def _wait_until(predicate, timeout: float = 2.0) -> bool:
    elapsed = 0.0
    while elapsed < timeout:
        if predicate():
            return True
        await asyncio.sleep(0.01)
        elapsed += 0.01
    return predicate()


async def _raw_handshake(port: int, hello: dict) -> dict | None:
    reader, writer = await asyncio.open_connection(HOST, port)
    message_writer = protocol.MessageWriter()
    for frame in message_writer.frames(hello):
        writer.write(frame)
    await writer.drain()
    message_reader = protocol.MessageReader()
    try:
        data = await asyncio.wait_for(reader.read(4096), 2.0)
    except TimeoutError:
        data = b""
    writer.close()
    messages = message_reader.feed(data) if data else []
    return messages[0] if messages else None


class TestBridge(unittest.TestCase):
    def test_handshake_welcomes_and_resyncs(self) -> None:
        async def scenario() -> None:
            recorder = Recorder("abcd1234", resync_items=[(0, 111), (1, 222)],
                                resync_checked=[542000000, 542000001])
            bridge = _make_bridge(recorder)
            await bridge.start()
            asi = FakeAsi(HOST, bridge.port, presented_seed_hash="")
            handshake = await asi.connect()
            self.assertEqual(handshake["type"], protocol.WELCOME)
            self.assertEqual(handshake["seed_hash"], "abcd1234")
            resync = await asi.drain_messages()
            by_type = {message["type"]: message for message in resync}
            self.assertEqual(by_type[protocol.ITEMS]["items"], [[0, 111], [1, 222]])
            self.assertEqual(by_type[protocol.CHECKED]["locations"], [542000000, 542000001])
            self.assertEqual(recorder.connected, 1)
            await asi.close()
            await bridge.stop()

        asyncio.run(scenario())

    def test_config_is_sent_before_the_resync(self) -> None:
        async def scenario() -> None:
            config = {"item_globals": {"542100000": 9010},
                      "completion_watch": {"9035": 542000000}}
            recorder = Recorder("abcd1234", resync_items=[(0, 111)], config=config)
            bridge = _make_bridge(recorder)
            await bridge.start()
            asi = FakeAsi(HOST, bridge.port, presented_seed_hash="abcd1234")
            await asi.connect()
            resync = await asi.drain_messages()
            self.assertEqual(resync[0]["type"], protocol.CONFIG)
            self.assertEqual(resync[0]["item_globals"], {"542100000": 9010})
            self.assertEqual(resync[0]["completion_watch"], {"9035": 542000000})
            await asi.close()
            await bridge.stop()

        asyncio.run(scenario())

    def test_check_and_goal_are_dispatched(self) -> None:
        async def scenario() -> None:
            recorder = Recorder("abcd1234")
            bridge = _make_bridge(recorder)
            await bridge.start()
            asi = FakeAsi(HOST, bridge.port, presented_seed_hash="abcd1234")
            await asi.connect()
            await asi.send_check(542000005)
            await asi.send_goal_reached()
            self.assertTrue(await _wait_until(lambda: recorder.checks == [542000005] and recorder.goals == 1))
            await asi.close()
            await bridge.stop()

        asyncio.run(scenario())

    def test_seed_mismatch_is_refused(self) -> None:
        async def scenario() -> None:
            recorder = Recorder("expected0")
            bridge = _make_bridge(recorder)
            await bridge.start()
            asi = FakeAsi(HOST, bridge.port, presented_seed_hash="different1")
            handshake = await asi.connect()
            self.assertEqual(handshake["type"], protocol.REFUSED)
            self.assertEqual(recorder.connected, 0)
            await asi.close()
            await bridge.stop()

        asyncio.run(scenario())

    def test_version_mismatch_is_refused(self) -> None:
        async def scenario() -> None:
            recorder = Recorder("abcd1234")
            bridge = _make_bridge(recorder)
            await bridge.start()
            reply = await _raw_handshake(bridge.port, {
                "type": protocol.HELLO, "protocol_version": protocol.PROTOCOL_VERSION + 99,
                "seed_hash": "",
            })
            self.assertEqual(reply["type"], protocol.REFUSED)
            self.assertEqual(recorder.connected, 0)
            await bridge.stop()

        asyncio.run(scenario())

    def test_refused_when_not_connected_to_ap(self) -> None:
        async def scenario() -> None:
            recorder = Recorder(None)  # AP not connected: no expected hash yet
            bridge = _make_bridge(recorder)
            await bridge.start()
            asi = FakeAsi(HOST, bridge.port, presented_seed_hash="")
            handshake = await asi.connect()
            self.assertEqual(handshake["type"], protocol.REFUSED)
            await asi.close()
            await bridge.stop()

        asyncio.run(scenario())

    def test_reconnect_resyncs_again(self) -> None:
        async def scenario() -> None:
            recorder = Recorder("abcd1234", resync_items=[(0, 111)])
            bridge = _make_bridge(recorder)
            await bridge.start()
            first = FakeAsi(HOST, bridge.port, presented_seed_hash="abcd1234")
            await first.connect()
            await first.drain_messages()
            await first.close()
            self.assertTrue(await _wait_until(lambda: not bridge.connected))
            second = FakeAsi(HOST, bridge.port, presented_seed_hash="abcd1234")
            await second.connect()
            resync = await second.drain_messages()
            self.assertIn(protocol.ITEMS, {message["type"] for message in resync})
            self.assertEqual(recorder.connected, 2)
            await second.close()
            await bridge.stop()

        asyncio.run(scenario())

    def test_refused_connection_does_not_evict_the_live_one(self) -> None:
        async def scenario() -> None:
            recorder = Recorder("goodhash0")
            bridge = _make_bridge(recorder)
            await bridge.start()
            good = FakeAsi(HOST, bridge.port, presented_seed_hash="goodhash0")
            await good.connect()
            await good.drain_messages()
            self.assertTrue(bridge.connected)
            bad = FakeAsi(HOST, bridge.port, presented_seed_hash="wronghash1")
            refusal = await bad.connect()
            self.assertEqual(refusal["type"], protocol.REFUSED)
            # The healthy connection survives the refused one and still works.
            self.assertTrue(bridge.connected)
            await good.send_check(7)
            self.assertTrue(await _wait_until(lambda: recorder.checks == [7]))
            await bad.close()
            await good.close()
            await bridge.stop()

        asyncio.run(scenario())

    def test_malformed_message_drops_connection_but_listener_survives(self) -> None:
        async def scenario() -> None:
            recorder = Recorder("abcd1234")
            bridge = _make_bridge(recorder)
            await bridge.start()
            first = FakeAsi(HOST, bridge.port, presented_seed_hash="abcd1234")
            await first.connect()
            await first.drain_messages()
            await first.send_message({"type": protocol.CHECK})  # missing "location"
            self.assertTrue(await _wait_until(lambda: not bridge.connected))
            # The listener survived; a fresh connection is welcomed as normal.
            second = FakeAsi(HOST, bridge.port, presented_seed_hash="abcd1234")
            handshake = await second.connect()
            self.assertEqual(handshake["type"], protocol.WELCOME)
            await first.close()
            await second.close()
            await bridge.stop()

        asyncio.run(scenario())

    def test_large_resync_is_chunked_and_reassembled(self) -> None:
        async def scenario() -> None:
            items = [(index, index * 3) for index in range(6000)]
            recorder = Recorder("abcd1234", resync_items=items)
            bridge = _make_bridge(recorder)
            await bridge.start()
            asi = FakeAsi(HOST, bridge.port, presented_seed_hash="abcd1234")
            await asi.connect()
            resync = await asi.drain_messages(timeout=1.0)
            items_messages = [message for message in resync if message["type"] == protocol.ITEMS]
            self.assertEqual(len(items_messages), 1)
            self.assertEqual(len(items_messages[0]["items"]), 6000)
            self.assertEqual(items_messages[0]["items"][-1], [5999, 17997])
            await asi.close()
            await bridge.stop()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
