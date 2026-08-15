"""Item tables. Names, ids, classification, and groups, derived from data.py.

Classification is decided here in one place. Progressive giver unlocks and
area access are progression; package rewards, emergency-vehicle rewards, and
radio stations are useful; cash denominations, the weapon pickup, the health
and armor top-ups, and the wanted-level clear are filler; the trap items are
traps. Money never gates logic, so cash is never progression.
"""

from __future__ import annotations

from BaseClasses import ItemClassification

from . import data

ID_BASE = 542_100_000

# Progression: one progressive unlock item per mission strand (story givers and
# venue strands), plus the area item(s).
STORY_PROGRESSIVE_NAMES: list[str] = [
    data.progressive_item_name(giver) for giver in data.STORY_GIVERS
]
VENUE_PROGRESSIVE_NAMES: list[str] = [
    data.progressive_item_name(venue) for venue in data.VENUE_STRANDS
]
PROGRESSIVE_ITEM_NAMES: list[str] = STORY_PROGRESSIVE_NAMES + VENUE_PROGRESSIVE_NAMES

# Ordered item name list; the id assignment follows this order. The table is
# not frozen until the first public release. After that, only append and never
# reorder or remove, so existing seeds stay valid; until then it is free to
# change. Venue progressives sit at the end.
_ORDERED_ITEM_NAMES: list[str] = (
    STORY_PROGRESSIVE_NAMES
    + data.AREA_ITEMS
    + data.PACKAGE_REWARD_ITEMS
    + data.EMERGENCY_REWARD_ITEMS
    + data.FILLER_ITEMS
    + VENUE_PROGRESSIVE_NAMES
    + [data.HIDDEN_PACKAGE_ITEM]
    + data.TRAP_ITEMS
    + data.RADIO_STATION_ITEMS
)

ITEM_NAME_TO_ID: dict[str, int] = {
    name: ID_BASE + index for index, name in enumerate(_ORDERED_ITEM_NAMES)
}

# The generic (non-cash) filler. get_filler_item_name draws only from these, so
# AP's cross-world and plando filler path never mints unbounded cash; the reward-
# mirror cash is placed by the world's own create_items.
GENERAL_FILLER_NAMES: list[str] = list(data.GENERAL_FILLER)


def _classify(name: str) -> ItemClassification:
    if name in PROGRESSIVE_ITEM_NAMES or name in data.AREA_ITEMS:
        return ItemClassification.progression
    if name == data.HIDDEN_PACKAGE_ITEM:
        # A goal macguffin: progression so the generator guarantees enough are
        # reachable, skip_balancing because there are many and none unlocks
        # anything, so they must not distort progression balancing.
        return ItemClassification.progression_skip_balancing
    if (name in data.PACKAGE_REWARD_ITEMS or name in data.EMERGENCY_REWARD_ITEMS
            or name in data.RADIO_STATION_ITEMS):
        return ItemClassification.useful
    if name in data.TRAP_ITEMS:
        return ItemClassification.trap
    return ItemClassification.filler


ITEM_CLASSIFICATIONS: dict[str, ItemClassification] = {
    name: _classify(name) for name in _ORDERED_ITEM_NAMES
}

ITEM_GROUPS: dict[str, list[str]] = {
    "Progressive Unlocks": list(PROGRESSIVE_ITEM_NAMES),
    "Area Access": list(data.AREA_ITEMS),
    "Package Rewards": list(data.PACKAGE_REWARD_ITEMS),
    "Emergency Rewards": list(data.EMERGENCY_REWARD_ITEMS),
    "Filler": list(data.FILLER_ITEMS),
    "Traps": list(data.TRAP_ITEMS),
    "Radio Stations": list(data.RADIO_STATION_ITEMS),
}

# The item quantity each name contributes to the pool. Progressive items have
# one per gated mission; everything else is a single copy (filler is topped up
# separately to match the location count).
ITEM_QUANTITIES: dict[str, int] = {
    data.progressive_item_name(strand): data.progressive_item_count(strand)
    for strand in data.progressive_strands()
}
