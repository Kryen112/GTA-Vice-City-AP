"""Location tables. Names, ids, region, and group, derived from data.py.

Two check classes so far: story missions (one location per mission) and
hidden packages (100 locations). Region assignment comes from data.py and is
provisional until the SCM barrier extraction lands.
"""

from __future__ import annotations

from . import data

ID_BASE = 542_000_000

# (giver, mission) for every story mission, in giver then play order.
STORY_MISSIONS: list[tuple[str, str]] = [
    (giver, mission)
    for giver, missions in data.STORY_GIVERS.items()
    for mission in missions
]

STORY_MISSION_NAMES: list[str] = [mission for _, mission in STORY_MISSIONS]

PACKAGE_NAMES: list[str] = [
    data.hidden_package_name(index)
    for index in range(1, data.HIDDEN_PACKAGE_COUNT + 1)
]

# Stable ordered location list. Order fixes ids; append only, never reorder.
_ORDERED_LOCATION_NAMES: list[str] = STORY_MISSION_NAMES + PACKAGE_NAMES

LOCATION_NAME_TO_ID: dict[str, int] = {
    name: ID_BASE + index for index, name in enumerate(_ORDERED_LOCATION_NAMES)
}

LOCATION_GROUPS: dict[str, list[str]] = {
    "Story Missions": list(STORY_MISSION_NAMES),
    "Hidden Packages": list(PACKAGE_NAMES),
}

# Location name to region. Packages are on the start island for now.
LOCATION_REGIONS: dict[str, str] = {}
for _giver, _mission in STORY_MISSIONS:
    LOCATION_REGIONS[_mission] = data.mission_region(_giver, _mission)
for _package in PACKAGE_NAMES:
    LOCATION_REGIONS[_package] = data.REGION_VICE_CITY

# Which giver and 0-based index each story mission has, for the access rules.
MISSION_GIVER: dict[str, str] = {}
MISSION_INDEX: dict[str, int] = {}
for _giver, _missions in data.STORY_GIVERS.items():
    for _index, _mission in enumerate(_missions):
        MISSION_GIVER[_mission] = _giver
        MISSION_INDEX[_mission] = _index
