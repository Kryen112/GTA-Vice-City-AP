"""Location tables. Names, ids, region, group, and check class, from data.py.

Story missions are always on. Every other check class is optional and governed
by its toggle (data.optional_check_classes). Story missions are placed by their
giver's island; every collectible and activity location sits on the start
island for now, refined per location in a Phase 3 audit.
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

OPTIONAL_CLASSES: dict[str, tuple[str, list[str]]] = data.optional_check_classes()

# Location name -> the option attribute that enables it. Story missions are
# absent (always on).
LOCATION_TOGGLE: dict[str, str] = {}
# Location name -> check class key, for grouping and the tracker.
LOCATION_CLASS: dict[str, str] = dict.fromkeys(STORY_MISSION_NAMES, "story_missions")
for _class_key, (_option_attr, _names) in OPTIONAL_CLASSES.items():
    for _name in _names:
        LOCATION_TOGGLE[_name] = _option_attr
        LOCATION_CLASS[_name] = _class_key

PACKAGE_NAMES: list[str] = list(OPTIONAL_CLASSES["hidden_packages"][1])

# Stable ordered location list: story missions, then each optional class in
# registry order. Order fixes ids; append only, never reorder.
_ORDERED_LOCATION_NAMES: list[str] = list(STORY_MISSION_NAMES)
for _class_key, (_option_attr, _names) in OPTIONAL_CLASSES.items():
    _ORDERED_LOCATION_NAMES.extend(_names)

LOCATION_NAME_TO_ID: dict[str, int] = {
    name: ID_BASE + index for index, name in enumerate(_ORDERED_LOCATION_NAMES)
}

LOCATION_GROUPS: dict[str, list[str]] = {
    "Story Missions": list(STORY_MISSION_NAMES),
    "Hidden Packages": list(OPTIONAL_CLASSES["hidden_packages"][1]),
    "Rampages and Stunt Jumps": list(OPTIONAL_CLASSES["rampages_stunts"][1]),
    "Emergency Vehicle Missions": list(OPTIONAL_CLASSES["emergency_vehicles"][1]),
    "Side Events": list(OPTIONAL_CLASSES["side_events"][1]),
    "Robbable Stores": list(OPTIONAL_CLASSES["robbable_stores"][1]),
}

# Location name to region. Story missions follow their giver's island;
# collectibles and activities are on the start island for now.
LOCATION_REGIONS: dict[str, str] = {}
for _giver, _mission in STORY_MISSIONS:
    LOCATION_REGIONS[_mission] = data.mission_region(_giver, _mission)
for _name in _ORDERED_LOCATION_NAMES:
    if _name not in LOCATION_REGIONS:
        LOCATION_REGIONS[_name] = data.REGION_VICE_CITY

# Which giver and 0-based index each story mission has, for the access rules.
MISSION_GIVER: dict[str, str] = {}
MISSION_INDEX: dict[str, int] = {}
for _giver, _missions in data.STORY_GIVERS.items():
    for _index, _mission in enumerate(_missions):
        MISSION_GIVER[_mission] = _giver
        MISSION_INDEX[_mission] = _index
