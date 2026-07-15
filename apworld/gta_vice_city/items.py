"""Item tables. Names, ids, classification, and groups, derived from data.py.

Classification is decided here in one place. Progressive giver unlocks and
area access are progression; package rewards and emergency-vehicle rewards are
useful; cash denominations, the weapon pickup, and the health and armor top-ups
are filler. Money never gates logic, so cash is never progression.
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
)

ITEM_NAME_TO_ID: dict[str, int] = {
    name: ID_BASE + index for index, name in enumerate(_ORDERED_ITEM_NAMES)
}

FILLER_NAMES: list[str] = list(data.FILLER_ITEMS)


def _classify(name: str) -> ItemClassification:
    if name in PROGRESSIVE_ITEM_NAMES or name in data.AREA_ITEMS:
        return ItemClassification.progression
    if name in data.PACKAGE_REWARD_ITEMS or name in data.EMERGENCY_REWARD_ITEMS:
        return ItemClassification.useful
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
}

# The item quantity each name contributes to the pool. Progressive items have
# one per gated mission; everything else is a single copy (filler is topped up
# separately to match the location count).
ITEM_QUANTITIES: dict[str, int] = {
    data.progressive_item_name(strand): data.progressive_item_count(strand)
    for strand in data.progressive_strands()
}
