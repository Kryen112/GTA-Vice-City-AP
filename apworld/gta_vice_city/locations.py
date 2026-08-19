"""Location tables. Names, ids, region, group, and check class, from data.py.

Story missions are always on. Every other check class is optional and governed
by its toggle (data.optional_check_classes). Each location's region (island) is
assigned below from the game's own coordinates where available (givers, rampages,
payphones, stores) and from the district otherwise. Stunt jumps and the
bespoke-trigger side events are provisionally on the mainland (safe over-gating)
until an in-game audit places each one.
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
# absent (always on). Order within a class follows registry order; ids are not
# frozen until first release.
LOCATION_TOGGLE: dict[str, str] = {}
# Location name -> check class key, for grouping and the tracker.
LOCATION_CLASS: dict[str, str] = dict.fromkeys(STORY_MISSION_NAMES, "story_missions")
for _class_key, (_option_attr, _names) in OPTIONAL_CLASSES.items():
    for _name in _names:
        LOCATION_TOGGLE[_name] = _option_attr
        LOCATION_CLASS[_name] = _class_key

# Check class key -> the option attribute that enables it. Story missions are
# always on and are absent.
CLASS_TOGGLE: dict[str, str] = {
    class_key: option_attr
    for class_key, (option_attr, _names) in OPTIONAL_CLASSES.items()
}

PACKAGE_NAMES: list[str] = list(OPTIONAL_CLASSES["hidden_packages"][1])

# Ordered location list: story missions, then each optional class in registry
# order; the id assignment follows this order. Not frozen until the first
# public release, after which only append and never reorder or remove.
_ORDERED_LOCATION_NAMES: list[str] = list(STORY_MISSION_NAMES)
for _class_key, (_option_attr, _names) in OPTIONAL_CLASSES.items():
    _ORDERED_LOCATION_NAMES.extend(_names)

LOCATION_NAME_TO_ID: dict[str, int] = {
    name: ID_BASE + index for index, name in enumerate(_ORDERED_LOCATION_NAMES)
}

LOCATION_GROUPS: dict[str, list[str]] = {
    "Story Missions": list(STORY_MISSION_NAMES),
    "Hidden Packages": list(OPTIONAL_CLASSES["hidden_packages"][1]),
    "Rampages": list(OPTIONAL_CLASSES["rampages"][1]),
    "Stunt Jumps": list(OPTIONAL_CLASSES["stunt_jumps"][1]),
    "Emergency Vehicle Missions": list(OPTIONAL_CLASSES["emergency_vehicles"][1]),
    "Side Events": list(OPTIONAL_CLASSES["side_events"][1]),
    "Robbable Stores": list(OPTIONAL_CLASSES["robbable_stores"][1]),
}

# Which strand and 0-based index each mission has, and each strand's missions in
# play order, for the access rules. Covers story givers and venue strands, since
# both are progressive.
MISSION_GIVER: dict[str, str] = {}
MISSION_INDEX: dict[str, int] = {}
STRAND_MISSIONS: dict[str, list[str]] = {}
for _strand, (_class_key, _missions) in data.progressive_strands().items():
    STRAND_MISSIONS[_strand] = list(_missions)
    for _index, _mission in enumerate(_missions):
        MISSION_GIVER[_mission] = _strand
        MISSION_INDEX[_mission] = _index

# Location name to region (island). Missions (story and venue) follow their
# giver or venue island, and a venue's activities follow their venue, with
# per-mission overrides; rampages, hidden packages, and robbable stores follow
# their world position; property purchases follow their
# business or safehouse island; the upper half of each emergency activity gates on
# the mainland for logic pacing; the mainland side events and (provisionally) all
# stunt jumps gate on the mainland. Anything left over is the start island.
LOCATION_REGIONS: dict[str, str] = {}
for _mission, _strand in MISSION_GIVER.items():
    LOCATION_REGIONS[_mission] = data.mission_region(_strand, _mission)
for _venue, _activities in data.VENUE_ACTIVITIES.items():
    for _activity in _activities:
        LOCATION_REGIONS[_activity] = data.mission_region(_venue, _activity)
for _name in data.MAINLAND_RAMPAGES:
    LOCATION_REGIONS[_name] = data.REGION_MAINLAND
for _name in data.STARFISH_RAMPAGES:
    LOCATION_REGIONS[_name] = data.REGION_STARFISH
for _name in data.MAINLAND_PACKAGES:
    LOCATION_REGIONS[_name] = data.REGION_MAINLAND
for _name in data.STARFISH_PACKAGES:
    LOCATION_REGIONS[_name] = data.REGION_STARFISH
for _activity, _level_count in data.EMERGENCY_LEVELS.items():
    for _level in range(_level_count // 2 + 1, _level_count + 1):
        LOCATION_REGIONS[data.emergency_name(_activity, _level)] = data.REGION_MAINLAND
for _name in data.MAINLAND_PROPERTIES:
    LOCATION_REGIONS[_name] = data.REGION_MAINLAND
for _name in data.MAINLAND_STORES:
    LOCATION_REGIONS[_name] = data.REGION_MAINLAND
for _name in data.MAINLAND_SIDE_EVENTS:
    LOCATION_REGIONS[_name] = data.REGION_MAINLAND
for _name in data.MAINLAND_STUNT_JUMPS:
    LOCATION_REGIONS[_name] = data.REGION_MAINLAND
for _name in _ORDERED_LOCATION_NAMES:
    LOCATION_REGIONS.setdefault(_name, data.REGION_VICE_CITY)
