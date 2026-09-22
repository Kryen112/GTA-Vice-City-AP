"""Temporary physical routes for dispatched missions, independent of AP access."""

import re

from island_gates import MAINLAND_LAUNCHERS, STARFISH_LAUNCHERS

# Mirrors the direct extra-region requirements in the world's data.py.
EXTRA_TRAVEL_MISSIONS = {
    10: "Sir, Yes Sir!", 14: "The Fastest Boat", 17: "Death Row",
    20: "Two Bit Hit", 22: "The Shootist", 24: "The Job",
    27: "Recruitment Drive", 30: "G-spotlight", 52: "Keep Your Friends Close...",
}


def needs_travel(number: int, launcher: str) -> bool:
    return (number in EXTRA_TRAVEL_MISSIONS
            or launcher in MAINLAND_LAUNCHERS | STARFISH_LAUNCHERS)


def route_lines(source: list[str], *, restore: bool) -> list[str]:
    """Move closed barriers aside; item-owned objects are taken care of by the watcher."""
    area = source[source.index(":APAREA"):source.index(":APAREA_SHARED")]
    result = []
    for handle, unlock in ((1781, 9032), (1782, 9033), (1783, 9034), (1780, 9031), (1779, 9035)):
        label = f"AP_TRAVEL_{'CLOSE' if restore else 'OPEN'}_{handle}"
        model = r"#[A-Z0-9_]+CLOSED" if handle in (1779, 1780) else r"\S+"
        closed = [match.groups() for line in source
                  if (match := re.fullmatch(
                      rf"create_object_no_offset \${handle} = init_object {model} at (\S+) (\S+) (\S+)", line))]
        assert len(closed) == 1, f"travel: missing barrier {handle}"
        x, y, z = closed[0]
        deletion = area.index(f"delete_object ${handle}")
        start = deletion
        while area[start - 1].startswith(("switch_roads_on ", "switch_ped_roads_on ")):
            start -= 1
        roads = area[start:deletion]
        assert roads, f"travel: missing road switches for {handle}"
        if handle == 1780:
            owned = ["if ", "  $9031 >= 1", f"goto_if_false @{label}_LOCKED"]
        elif handle == 1779:
            owned = ["if ", "  $9031 >= 1", f"goto_if_false @{label}_LOCKED",
                     "if or", "  $9030 >= 1", "  $9035 >= 1", f"goto_if_false @{label}_LOCKED"]
        else:
            owned = ["if or", "  $9030 >= 1", f"  ${unlock} >= 1", f"goto_if_false @{label}_LOCKED"]
        # Z <= -100 asks the opcode to find ground height instead of moving underground.
        result += [*owned, f"goto @{label}_DONE", f":{label}_LOCKED",
                   "if ", f"  does_object_exist ${handle}", f"goto_if_false @{label}_DONE",
                   f"set_object_coordinates ${handle} at {x} {y} {z if restore else '-90.0'}",
                   *(line.replace("_on ", "_off ") if restore else line for line in roads),
                   f":{label}_DONE"]
    return result
