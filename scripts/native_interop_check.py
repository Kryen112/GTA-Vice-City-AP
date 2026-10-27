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


async def main(executable: Path, *, legacy: bool = False, large_room: bool = False) -> None:
    connections = 0
    authenticated_connections = 0
    checks = 0
    goal = asyncio.Event()
    errors = []
    messages = []
    percentages = []
    group_requests = []
    package_requests = []
    foreign_games = {f"Foreign Game {game}": {
        "item_name_to_id": {f"Item {index} " + "x" * 256: index for index in range(12000)},
        "location_name_to_id": {f"Location {index} " + "x" * 256: index for index in range(12000)},
    } for game in range(3)} if large_room else {}
    for index, package in enumerate(foreign_games.values()):
        package["item_name_to_id"][f"Foreign item {index}"] = 1000000 + index
    if large_room:
        assert len(json.dumps(foreign_games).encode()) > 16 * 1024 * 1024

    async def server(socket):
        nonlocal connections, authenticated_connections, checks
        connections += 1
        # A reachable WebSocket endpoint can repeatedly close before AP login.
        if connections in (1, 2, 3, 5, 6, 7):
            await socket.close()
            return
        authenticated_connections += 1
        current = authenticated_connections
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
                             "slot_info": {"1": {"name": "native-test", "game": "Grand Theft Auto Vice City"},
                                           **{str(index + 2): {"name": f"Player{index + 2}",
                                                              "game": f"Foreign Game {index % 3}"}
                                              for index in range(159 if large_room else 0)}},
                             "checked_locations": [], "missing_locations": [101],
                             "slot_data": {"item_globals": {"542100000": 9005}, "config_globals": {},
                                           "completion_watch": {"9102": 101}, "goal": "final_mission",
                                           "final_location_id": 101}},
                            {"cmd": "ReceivedItems", "index": 0, "items": [item] * min(current, 2)},
                            {"cmd": "PrintJSON", "type": "Chat", "data": [{"text": "Other player: hello"}]},
                            {"cmd": "Print", "text": "Server countdown: 3"},
                        ]))
                    elif command == "GetDataPackage":
                        assert len(packet["games"]) == 1, "Request one game per response, not the entire room"
                        game = packet["games"][0]
                        assert game in foreign_games, f"Unexpected name database: {game}"
                        assert (current, game) not in package_requests, "Duplicate game request"
                        package_requests.append((current, game))
                        reply = [{"cmd": "DataPackage", "data": {"games": {game: foreign_games[game]}}}]
                        if current >= 2 and game == "Foreign Game 2":
                            reply.append({"cmd": "PrintJSON", "data": [
                                {"type": "item_id", "text": "1000002", "player": 4}]})
                        await socket.send(json.dumps(reply))
                    elif command == "Get":
                        expected = {f"_read_{kind}_name_groups_Grand Theft Auto Vice City"
                                    for kind in ("item", "location")}
                        trap_key = f"gta_vice_city_consumed_traps_0_1_{seed_hash}"
                        emergency_keys = {f"gta_vice_city_emergency_0_1_{seed_hash}_{activity}"
                                          for activity in ("taxi", "paramedic", "firefighter", "vigilante", "pizza")}
                        assert set(packet["keys"]) == expected | {trap_key} | emergency_keys, (
                            f"Unexpected Get keys: {packet['keys']}")
                        group_requests.append(current)
                        await socket.send(json.dumps([{"cmd": "Retrieved", "keys": {
                            **{key: {"Example group": ["Example member"]} for key in expected},
                            **dict.fromkeys(emergency_keys),
                            trap_key: None}}]))
                    elif command == "Say":
                        messages.append(packet["text"])
                    elif command == "Set":
                        percentages.append(packet["operations"][0]["value"])
                    elif command == "LocationChecks":
                        assert packet["locations"] == [101], f"Unexpected checks: {packet['locations']}"
                        checks += 1
                        if current == 1:
                            # Drop the acknowledgement. The next connection must replay the check.
                            await socket.close()
                            return
                        await socket.send(json.dumps([{"cmd": "RoomUpdate", "checked_locations": [101]}]))
                    elif command == "StatusUpdate":
                        assert packet["status"] in (10, 30), f"Unexpected status: {packet['status']}"
                        if packet["status"] == 30:
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
            settings_text = f"[archipelago]\nserver=127.0.0.1:{port}\nslot=native-test\npassword=test-password\n"
            settings = root / "state/connection.ini"
            if legacy:
                harness.with_suffix(".ini").write_text(settings_text)
            else:
                settings.parent.mkdir()
                settings.write_text(settings_text)
                harness.with_suffix(".ini").write_text(
                    "[archipelago]\nserver=127.0.0.1:1\nslot=stale-slot\npassword=stale-password\n")
            arguments = ["--large-room"] if large_room else []
            process = await asyncio.create_subprocess_exec(str(harness), *arguments, stdout=asyncio.subprocess.PIPE,
                                                           stderr=asyncio.subprocess.STDOUT)
            try:
                output, _ = await asyncio.wait_for(process.communicate(), timeout=30)
            except TimeoutError:
                process.kill()
                await process.wait()
                raise
            print(output.decode(errors="replace"))
            assert not errors, errors
            assert process.returncode == 0, "Native harness failed"
            assert connections >= 8 and checks >= 2, "Reconnect did not replay the unacknowledged check"
            assert {1, 2}.issubset(group_requests), "Name groups were not refreshed on reconnect"
            if large_room:
                assert {(2, game) for game in foreign_games}.issubset(package_requests)
                assert "Foreign item 2" in output.decode(errors="replace"), "Foreign names did not resolve"
                assert "Server message limit exceeded" not in output.decode(errors="replace")
            assert goal.is_set(), "Goal status never reached the server"
            assert output.decode(errors="replace").count("Connection unavailable;") == 2, (
                "Repeated transport failures must log once per outage, rearmed only after AP login")
            assert "hello from the ASI" in messages and "!hint Package" in messages
            assert "Other player: hello" in output.decode(errors="replace")
            assert "Server countdown: 3" in output.decode(errors="replace")
            assert 41 in percentages, "State from the previous beside-ASI layout was not recovered"
            assert old_state.exists() and (root / "state" / old_state.name).exists()
            assert settings.read_text().strip() == settings_text.strip(), "Connection settings were not preserved"
            assert "test-password" not in output.decode(errors="replace"), "Password leaked to the log"
            assert "AP: Connected | Server:" in output.decode(errors="replace")
            assert "AP: Disconnected | Server:" in output.decode(errors="replace")
            assert "Port must be 1..65535." in output.decode(errors="replace")
            assert "server updated. Use /connect." in output.decode(errors="replace")
            assert "AP client stopped." in output.decode(errors="replace")
    print("APCpp transport, reconnect, check replay, goal reporting and console settings commands passed")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]).resolve()))
    asyncio.run(main(Path(sys.argv[1]).resolve(), legacy=True))
    asyncio.run(main(Path(sys.argv[1]).resolve(), large_room=True))
