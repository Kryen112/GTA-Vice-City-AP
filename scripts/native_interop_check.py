"""Drive the real APCpp transport against an isolated, fragmented AP test server."""

import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed


async def main(executable: Path) -> None:
    connections = 0
    checks = 0
    goal = asyncio.Event()
    errors = []
    messages = []
    percentages = []
    group_requests = []

    async def server(socket):
        nonlocal connections, checks
        connections += 1
        current = connections
        try:
            # A fragmented packet larger than the fork's former 32 KB buffer.
            room = json.dumps([{"cmd": "RoomInfo", "seed_name": "native-interop",
                                "padding": "x" * 70000}])
            await socket.send([room[:10000], room[10000:50000], room[50000:]])
            async for raw in socket:
                for packet in json.loads(raw):
                    command = packet["cmd"]
                    if command == "Connect":
                        assert packet["name"] == "native-test"
                        assert packet["password"] == "test-password"
                        assert packet["items_handling"] == 7
                        item = {"item": 542100000, "player": 1, "location": 101, "flags": 1}
                        await socket.send(json.dumps([
                            {"cmd": "Connected", "slot": 1, "team": 0,
                             "players": [{"slot": 1, "team": 0, "alias": "native-test"}],
                             "slot_info": {"1": {"name": "native-test", "game": "Grand Theft Auto Vice City"}},
                             "checked_locations": [], "missing_locations": [101],
                             "slot_data": {"item_globals": {"542100000": 9005}, "config_globals": {},
                                           "completion_watch": {"9102": 101}, "goal": "final_mission",
                                           "final_location_id": 101}},
                            {"cmd": "ReceivedItems", "index": 0, "items": [item] * min(current, 2)},
                            {"cmd": "PrintJSON", "type": "Chat", "data": [{"text": "Other player: hello"}]},
                            {"cmd": "Print", "text": "Server countdown: 3"},
                        ]))
                    elif command == "Get":
                        expected = {f"_read_{kind}_name_groups_Grand Theft Auto Vice City"
                                    for kind in ("item", "location")}
                        assert set(packet["keys"]) == expected
                        group_requests.append(current)
                        await socket.send(json.dumps([{"cmd": "Retrieved", "keys": {
                            key: {"Example group": ["Example member"]} for key in expected}}]))
                    elif command == "Say":
                        messages.append(packet["text"])
                    elif command == "Set":
                        percentages.append(packet["operations"][0]["value"])
                    elif command == "LocationChecks":
                        assert packet["locations"] == [101]
                        checks += 1
                        if current == 1:
                            # Drop the acknowledgement. The next connection must replay the check.
                            await socket.close()
                            return
                        await socket.send(json.dumps([{"cmd": "RoomUpdate", "checked_locations": [101]}]))
                    elif command == "StatusUpdate":
                        assert packet["status"] == 30
                        goal.set()
        except ConnectionClosed as error:
            # APCpp destroys its socket when the harness exits after the goal.
            if not goal.is_set():
                errors.append(error)
        except Exception as error:
            errors.append(error)

    with tempfile.TemporaryDirectory(prefix="gtavc-native-") as folder:
        root = Path(folder)
        harness = root / "native_harness.exe"
        shutil.copy2(executable, harness)
        seed_hash = hashlib.sha256(b"native-interop\x1fnative-test").hexdigest()[:16]
        old_state = root / f"GtaVcAp.{seed_hash}.json"
        old_state.write_text(json.dumps({"seed_hash": seed_hash, "checks": [], "percentage": 41}))
        async with serve(server, "127.0.0.1", 0) as listener:
            port = listener.sockets[0].getsockname()[1]
            harness.with_suffix(".ini").write_text(
                f"[archipelago]\nserver=127.0.0.1:{port}\nslot=native-test\npassword=test-password\n")
            process = await asyncio.create_subprocess_exec(str(harness), stdout=asyncio.subprocess.PIPE,
                                                           stderr=asyncio.subprocess.STDOUT)
            try:
                output, _ = await asyncio.wait_for(process.communicate(), timeout=30)
            except TimeoutError:
                process.kill()
                await process.wait()
                raise
            print(output.decode(errors="replace"))
            assert process.returncode == 0, "Native harness failed"
            assert not errors, errors
            assert connections >= 2 and checks >= 2, "Reconnect did not replay the unacknowledged check"
            assert {1, 2}.issubset(group_requests), "Name groups were not refreshed on reconnect"
            assert goal.is_set(), "Goal status never reached the server"
            assert "hello from the ASI" in messages and "!hint Package" in messages
            assert "Other player: hello" in output.decode(errors="replace")
            assert "Server countdown: 3" in output.decode(errors="replace")
            assert 41 in percentages, "State from the previous beside-ASI layout was not recovered"
            assert old_state.exists() and (root / "state" / old_state.name).exists()
            assert "test-password" not in output.decode(errors="replace"), "Password leaked to the log"
    print("APCpp transport, fragmentation, reconnect, check replay and goal reporting passed")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]).resolve()))
