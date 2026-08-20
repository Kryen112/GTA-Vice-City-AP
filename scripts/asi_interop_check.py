"""Headless C++ ASI to Python client interop check.

Starts the real Python AsiBridge, runs the compiled C++ harness against it as a
subprocess, and asserts the round trip: the harness receives the welcome, the
resync items and checked locations, and its emitted check reaches the bridge.
Windows and MSVC only (needs the built harness), so this is a dev-machine check,
not part of the ubuntu CI. Usage:
    python scripts/asi_interop_check.py <path-to-harness.exe>
"""

from __future__ import annotations

import asyncio
import json
import sys

from ap_env import archipelago_root, link_world

_root = archipelago_root()
if _root is not None:
    sys.path.insert(0, str(_root))
    link_world(_root)

from worlds.gta_vice_city.client import protocol  # noqa: E402
from worlds.gta_vice_city.client.bridge import AsiBridge  # noqa: E402

EXPECTED_HASH = "interophash01"
RESYNC_ITEMS = [(0, 111), (1, 222), (2, 333)]
RESYNC_CHECKED = [542000000, 542000001]
EMITTED_CHECK = 542000042
CONFIG = {
    "item_globals": {"542100000": 9010, "542100001": 9011},
    "completion_watch": {"9035": 542000000, "9036": 542000042},
    "item_effects": {
        "542100050": ["cash", 5000], "542100051": ["weapon"],
        # Traps ride the same channel: one with a duration param, one without,
        # so the round trip proves the param list is preserved either way.
        "542100052": ["trap_speed_up", 30], "542100053": ["trap_weather"],
    },
    "config_globals": {"9377": 1, "9378": 0},
    # Two ambient pickup rows, one weapon with ammo and one consumable, so the
    # round trip proves the layout decode end to end.
    "pickup_layout": [[393.9, -60.2, 11.5, 15, 274, 34], [-37.7, -938.3, 10.5, 15, 375, 0]],
    # Two mainland routes, one plain and one carrying the second item its route
    # needs, so the round trip proves both shapes decode.
    "mainland_routes": [
        {"global": 9032, "label": "Prawn Island Bridge",
         "needs_global": 0, "needs_label": ""},
        {"global": 9035, "label": "Starfish Island Causeway",
         "needs_global": 9031, "needs_label": "Starfish Island Access"},
    ],
    # One content item releasing several district globals and one releasing a
    # single global: the two shapes the fan-out has to decode.
    "content_district_globals": {
        "542100200": [9460, 9461, 9462],
        "542100201": [9471],
    },
    # Two placed pickups of different classes, close enough together that only
    # the class tells them apart.
    "content_districts": [
        {"x": 479.6, "y": -1718.5, "class": 0, "district": 0},
        {"x": 480.1, "y": -1718.5, "class": 3, "district": 9},
    ],
}

# Pickup district rows the ASI must drop rather than keep: a class and a district
# outside their blocks would index past the lock array. Sent with the good rows;
# the harness does not echo them, so the assertion is that the config frame
# decodes at all rather than that these are filtered, which the console
# self-test covers directly.
DROPPED_PICKUP_DISTRICTS = [
    {"x": 1.0, "y": 2.0, "class": 99, "district": 0},
    {"x": 3.0, "y": 4.0, "class": 0, "district": 99},
]

# Rows the ASI must drop rather than keep: one with no global to read, one with
# no name to show, and one claiming a second requirement it cannot name, which
# would otherwise render as "... needs ." Sent with the good rows, absent from
# what comes back.
DROPPED_ROUTES = [
    {"global": 0, "label": "Nowhere", "needs_global": 0, "needs_label": ""},
    {"global": 9033, "label": "", "needs_global": 0, "needs_label": ""},
    {"global": 9034, "label": "Ocean Beach Bridge",
     "needs_global": 9031, "needs_label": ""},
]


class Recorder:
    def __init__(self) -> None:
        self.checks: list[int] = []
        self.connected = 0

    def seed_hash(self) -> str:
        return EXPECTED_HASH

    async def on_check(self, location: int) -> None:
        self.checks.append(location)

    async def on_goal(self) -> None:
        pass

    async def on_connected(self, bridge: AsiBridge) -> None:
        self.connected += 1
        # package_coords rides the same config frame; the harness does not echo
        # it back, so this check sends an empty map and asserts the rest.
        await bridge.send_config(
            CONFIG["item_globals"], CONFIG["completion_watch"],
            CONFIG["item_effects"], CONFIG["config_globals"], {},
            CONFIG["pickup_layout"], CONFIG["mainland_routes"] + DROPPED_ROUTES,
            CONFIG["content_district_globals"],
            CONFIG["content_districts"] + DROPPED_PICKUP_DISTRICTS,
        )
        await bridge.send_items(RESYNC_ITEMS)
        await bridge.send_checked(RESYNC_CHECKED)


async def run(harness: str) -> int:
    recorder = Recorder()
    bridge = AsiBridge(
        "127.0.0.1", 0,
        expected_seed_hash=recorder.seed_hash,
        on_check=recorder.on_check,
        on_goal_reached=recorder.on_goal,
        on_connected=recorder.on_connected,
    )
    await bridge.start()
    process = await asyncio.create_subprocess_exec(
        harness,
        "--host", "127.0.0.1", "--port", str(bridge.port),
        "--seed-hash", "", "--emit-check", str(EMITTED_CHECK), "--run-ms", "1500",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
    except TimeoutError:
        process.kill()
        await process.wait()
        print("FAIL: the harness did not exit in time")
        return 1
    finally:
        await bridge.stop()

    summary_line = stdout.decode(errors="replace").strip().splitlines()
    summary = json.loads(summary_line[-1]) if summary_line else {}
    failures: list[str] = []
    if recorder.checks != [EMITTED_CHECK]:
        failures.append(f"bridge checks {recorder.checks} != [{EMITTED_CHECK}]")
    if summary.get("welcome_seed_hash") != EXPECTED_HASH:
        failures.append(f"welcome hash {summary.get('welcome_seed_hash')!r} != {EXPECTED_HASH!r}")
    if summary.get("items") != [list(pair) for pair in RESYNC_ITEMS]:
        failures.append(f"items {summary.get('items')} != {RESYNC_ITEMS}")
    if summary.get("checked") != RESYNC_CHECKED:
        failures.append(f"checked {summary.get('checked')} != {RESYNC_CHECKED}")
    if summary.get("item_globals") != CONFIG["item_globals"]:
        failures.append(f"item_globals {summary.get('item_globals')} != {CONFIG['item_globals']}")
    if summary.get("completion_watch") != CONFIG["completion_watch"]:
        failures.append(f"completion_watch {summary.get('completion_watch')} != {CONFIG['completion_watch']}")
    if summary.get("item_effects") != CONFIG["item_effects"]:
        failures.append(f"item_effects {summary.get('item_effects')} != {CONFIG['item_effects']}")
    if summary.get("config_globals") != CONFIG["config_globals"]:
        failures.append(f"config_globals {summary.get('config_globals')} != {CONFIG['config_globals']}")
    if summary.get("pickup_layout") != CONFIG["pickup_layout"]:
        failures.append(f"pickup_layout {summary.get('pickup_layout')} != {CONFIG['pickup_layout']}")
    # The routes echo as rows rather than objects, so compare them that way: the
    # point of the assertion is that the C++ side read every field, including the
    # second requirement only one route carries.
    expected_routes = [
        [route["global"], route["label"], route["needs_global"], route["needs_label"]]
        for route in CONFIG["mainland_routes"]
    ]
    if summary.get("mainland_routes") != expected_routes:
        failures.append(
            f"mainland_routes {summary.get('mainland_routes')} != {expected_routes}")

    if failures:
        print("FAIL: C++ ASI interop check")
        for failure in failures:
            print("  " + failure)
        print("harness stderr:\n" + stderr.decode(errors="replace"))
        return 1
    print("OK: C++ ASI interop check passed")
    print(f"  handshake used protocol version {protocol.PROTOCOL_VERSION}")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/asi_interop_check.py <path-to-harness.exe>")
        return 2
    return asyncio.run(run(sys.argv[1]))


if __name__ == "__main__":
    sys.exit(main())
