"""Headless C++ ASI to Python client interop check.

Starts the real Python AsiBridge, runs the compiled C++ harness against it as a
subprocess, and asserts the round trip: the harness receives the welcome, the
resync items and checked locations, and its emitted check and completion
percentage reach the bridge.
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

# One toast row, in the shape protocol.toast_message writes and the C++ side reads
# by key and by pair position. The seam is worth a case of its own: a rename on
# either side degrades to a caught json exception and a log line, so toasts would
# vanish in game with nothing failing anywhere. Every role the mod knows appears,
# so a name dropped from either table is caught too.
#
# The harness reports a row as its lines joined by " | ", so what comes back proves
# both the newline marker breaking the row and the segment order inside each line.
#
# The client no longer emits the marker (a movement is one line now), but the mod
# still has to honour it, since that is how a notice too long for the band is broken
# across lines. This is the only thing that exercises it end to end.
TOAST_SEGMENTS = [
    ("You", protocol.TOAST_OWN_SLOT),
    (" sent ", protocol.TOAST_CONNECTIVE),
    ("Minigun", protocol.TOAST_PROGRESSION),
    (" to ", protocol.TOAST_CONNECTIVE),
    ("PlayerTwo", protocol.TOAST_OTHER_SLOT),
    protocol.toast_newline(),
    ("(", protocol.TOAST_CONNECTIVE),
    ("Hidden Package 42", protocol.TOAST_LOCATION),
    (")", protocol.TOAST_CONNECTIVE),
]
EXPECTED_TOAST = "You sent Minigun to PlayerTwo | (Hidden Package 42)"
EMITTED_CHECK = 542000042
EMITTED_PERCENTAGE = 93
CONFIG = {
    "item_globals": {"542100000": 9010, "542100001": 9011},
    "completion_watch": {"9035": 542000000, "9036": 542000042},
    "item_effects": {
        "542100050": ["cash", 5000], "542100051": ["weapon"],
        # Traps ride the same channel: one with a duration param, one without,
        # so the round trip proves the param list is preserved either way.
        "542100052": ["trap_speed_up", 30], "542100053": ["trap_weather"],
    },
    # The item ids here are invented; the globals are NOT. They are taken from
    # the real layout so the frame reads like one the game would receive, which
    # means a shift of the reserved block moves the ones above the completion
    # block and this fixture is one of the places to move them. Below that block
    # nothing moves, which is why the unlock globals and the completion globals
    # elsewhere in this frame stay put. In completion_watch above, 9035 is the
    # last UNLOCK global rather than a completion global; 9036 is the first
    # completion one.
    "config_globals": {"9501": 1, "9502": 0},
    # Two ambient pickup rows, one weapon with ammo and one consumable, so the
    # round trip proves the layout decode end to end.
    # Three rows, one shape each the decode has to survive: a slot that is a
    # check and carries its completion global as a seventh element, a slot that
    # is not, and a six-element row from a world that predates the checks, which
    # the ASI reads as no check rather than as a malformed frame.
    "pickup_layout": [
        [393.9, -60.2, 11.5, 15, 274, 34, 9376],
        [-37.7, -938.3, 10.5, 15, 375, 0, 0],
        [201.4, -1077.6, 10.9, 2, 366, 0],
    ],
    # What the six-element row above becomes once decoded: no check. The
    # comparison is against the echo, so the expectation carries the shape the
    # ASI produces rather than the shape the world sent.
    "pickup_layout_echoed": [
        [393.9, -60.2, 11.5, 15, 274, 34, 9376],
        [-37.7, -938.3, 10.5, 15, 375, 0, 0],
        [201.4, -1077.6, 10.9, 2, 366, 0, 0],
    ],
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
        "542100200": [9570, 9571, 9572],
        "542100201": [9581],
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


# The counts a status frame carries: checks done, checks total, items received,
# and whether AP has the slot finished, plus the two row lists only the client can
# compose (the goal's own progress and each mission strand's) and the finale warp
# ask, which the hunt goal raises to play the story's ending.
STATUS = (61, 214, 43, False)
STATUS_FINALE_WARP = True
STATUS_GOAL_ROWS = [["Goal", "Package Fragments", False], ["Fragments", "7 of 20", False]]
STATUS_STRAND_ROWS = [["Cortez", "3 of 5", False], ["Diaz", "6 of 6", True]]


class Recorder:
    def __init__(self) -> None:
        self.checks: list[int] = []
        self.percentages: list[int] = []
        self.connected = 0

    def seed_hash(self) -> str:
        return EXPECTED_HASH

    async def on_check(self, location: int) -> None:
        self.checks.append(location)

    async def on_goal(self) -> None:
        pass

    async def on_progress(self, percentage: int) -> None:
        self.percentages.append(percentage)

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
        await bridge.send_status(*STATUS, STATUS_GOAL_ROWS, STATUS_STRAND_ROWS,
                                 STATUS_FINALE_WARP)
        await bridge.send_toast(TOAST_SEGMENTS)


async def run(harness: str) -> int:
    recorder = Recorder()
    bridge = AsiBridge(
        "127.0.0.1", 0,
        expected_seed_hash=recorder.seed_hash,
        on_check=recorder.on_check,
        on_goal_reached=recorder.on_goal,
        on_connected=recorder.on_connected,
        on_progress=recorder.on_progress,
    )
    await bridge.start()
    process = await asyncio.create_subprocess_exec(
        harness,
        "--host", "127.0.0.1", "--port", str(bridge.port),
        "--seed-hash", "", "--emit-check", str(EMITTED_CHECK),
        "--emit-percentage", str(EMITTED_PERCENTAGE), "--run-ms", "1500",
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
    if recorder.percentages != [EMITTED_PERCENTAGE]:
        failures.append(
            f"bridge percentages {recorder.percentages} != [{EMITTED_PERCENTAGE}]")
    if summary.get("welcome_seed_hash") != EXPECTED_HASH:
        failures.append(f"welcome hash {summary.get('welcome_seed_hash')!r} != {EXPECTED_HASH!r}")
    if summary.get("items") != [list(pair) for pair in RESYNC_ITEMS]:
        failures.append(f"items {summary.get('items')} != {RESYNC_ITEMS}")
    if summary.get("checked") != RESYNC_CHECKED:
        failures.append(f"checked {summary.get('checked')} != {RESYNC_CHECKED}")
    if summary.get("toasts") != [EXPECTED_TOAST]:
        failures.append(f"toasts {summary.get('toasts')} != [{EXPECTED_TOAST!r}]")
    # A welcomed session clears the handshake-refusal notice on its way through, so
    # a player refused for one game and welcomed into the next does not keep
    # reading that the seed was refused. Both slots empty is what proves the clear
    # ran on this path and did not raise anything of its own.
    if summary.get("notices") != ["", ""]:
        failures.append(f"notices {summary.get('notices')} are not both clear "
                        f"after a welcome")
    if summary.get("status") != list(STATUS):
        failures.append(f"status {summary.get('status')} != {list(STATUS)}")
    if summary.get("status_finale_warp") is not STATUS_FINALE_WARP:
        failures.append(
            f"status finale warp {summary.get('status_finale_warp')} != "
            f"{STATUS_FINALE_WARP}")
    expected_rows = [STATUS_GOAL_ROWS, STATUS_STRAND_ROWS]
    if summary.get("status_rows") != expected_rows:
        failures.append(f"status rows {summary.get('status_rows')} != {expected_rows}")
    # The welcome is what marks the client up for the pause menu's page. The live
    # flag is false again by the time the harness prints, since the session ended,
    # so what is asserted is that the welcome set it at all.
    if summary.get("client_was_connected") is not True:
        failures.append(
            f"client_was_connected {summary.get('client_was_connected')} is not True")
    if summary.get("item_globals") != CONFIG["item_globals"]:
        failures.append(f"item_globals {summary.get('item_globals')} != {CONFIG['item_globals']}")
    if summary.get("completion_watch") != CONFIG["completion_watch"]:
        failures.append(f"completion_watch {summary.get('completion_watch')} != {CONFIG['completion_watch']}")
    if summary.get("item_effects") != CONFIG["item_effects"]:
        failures.append(f"item_effects {summary.get('item_effects')} != {CONFIG['item_effects']}")
    if summary.get("config_globals") != CONFIG["config_globals"]:
        failures.append(f"config_globals {summary.get('config_globals')} != {CONFIG['config_globals']}")
    if summary.get("pickup_layout") != CONFIG["pickup_layout_echoed"]:
        failures.append(f"pickup_layout {summary.get('pickup_layout')} != "
                        f"{CONFIG['pickup_layout_echoed']}")
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
