"""Location tables. Names, ids, region, group, and check class, from data.py.

Story missions are always on. Every other check class is optional and governed
by its toggle (data.optional_check_classes). Each location's region (island) is
assigned below from the audited district for the collectible classes and from the
game's own coordinates for the rest (givers, payphones, venues). The
bespoke-trigger side events are provisionally on the mainland, safe over-gating,
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

# The ordered names as the id table read them, so a test can see a duplicate the
# dict below would silently collapse: the second one would take the first one's
# id and a check would go missing.
ORDERED_LOCATION_NAMES: list[str] = list(_ORDERED_LOCATION_NAMES)

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
    "Pickups": list(OPTIONAL_CLASSES["pickups"][1]),
    "Shops": list(OPTIONAL_CLASSES["shops"][1]),
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
# per-mission overrides; rampages, hidden packages, stunt jumps and robbable stores
# follow their audited district; property purchases follow their business or
# safehouse island; the upper half of each emergency activity gates on the mainland
# for logic pacing; and the mainland side events gate on the mainland. Anything
# left over is the start island.
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
for _name in data.STARFISH_STUNT_JUMPS:
    LOCATION_REGIONS[_name] = data.REGION_STARFISH
for _name in data.MAINLAND_STUNT_JUMPS:
    LOCATION_REGIONS[_name] = data.REGION_MAINLAND
# A pickup's region comes from its own district rather than from a membership
# list, since every district is known for all 110 of them and the districts are
# what the names already read from. Derived rather than audited, so a wrong
# district here is a wrong region too: see district_data.PICKUP_DISTRICTS.
for _index in range(data.PICKUP_COUNT):
    # The island a slot actually sits on. The district NAME here is derived and
    # about 90 per cent accurate, but the REGION it maps to is verified for all
    # 110 against the nearest audited anchor, at a minimum margin of 92 units,
    # so the island gate is sound even for a slot whose district name the hand
    # audit will correct. That is what lets these hold progression: a wrong
    # name misnames a check, a wrong island would strand one.
    LOCATION_REGIONS[data.pickup_name(_index)] = data.pickup_region(_index)
# A shop's region comes from its district too, so the two mainland shops wait on
# the crossing and the four on the starting island do not.
for _shop_item in data.shop_data.SHOP_ITEMS:
    LOCATION_REGIONS[data.shop_data.shop_item_name(_shop_item)] = (
        data.shop_item_region(_shop_item))
for _name in _ORDERED_LOCATION_NAMES:
    LOCATION_REGIONS.setdefault(_name, data.REGION_VICE_CITY)
