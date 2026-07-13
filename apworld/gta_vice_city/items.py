"""Item tables. Names, ids, classification, and groups, derived from data.py.

Classification is decided here in one place. Progressive giver unlocks and
area access are progression; package rewards are useful; cash and ammo are
filler. Money never gates logic, so cash is never progression.
"""

from __future__ import annotations

from BaseClasses import ItemClassification

from . import data

ID_BASE = 542_100_000

# Progression: one progressive unlock item per giver, plus the two area items.
PROGRESSIVE_ITEM_NAMES: list[str] = [
    data.progressive_item_name(giver) for giver in data.STORY_GIVERS
]

# Ordered, stable item name list. Order fixes the id assignment, so never
# reorder existing entries; append only.
_ORDERED_ITEM_NAMES: list[str] = (
    PROGRESSIVE_ITEM_NAMES
    + data.AREA_ITEMS
    + data.PACKAGE_REWARD_ITEMS
    + data.FILLER_ITEMS
)

ITEM_NAME_TO_ID: dict[str, int] = {
    name: ID_BASE + index for index, name in enumerate(_ORDERED_ITEM_NAMES)
}

FILLER_NAMES: list[str] = list(data.FILLER_ITEMS)


def _classify(name: str) -> ItemClassification:
    if name in PROGRESSIVE_ITEM_NAMES or name in data.AREA_ITEMS:
        return ItemClassification.progression
    if name in data.PACKAGE_REWARD_ITEMS:
        return ItemClassification.useful
    return ItemClassification.filler


ITEM_CLASSIFICATIONS: dict[str, ItemClassification] = {
    name: _classify(name) for name in _ORDERED_ITEM_NAMES
}

ITEM_GROUPS: dict[str, list[str]] = {
    "Progressive Unlocks": list(PROGRESSIVE_ITEM_NAMES),
    "Area Access": list(data.AREA_ITEMS),
    "Package Rewards": list(data.PACKAGE_REWARD_ITEMS),
    "Filler": list(data.FILLER_ITEMS),
}

# The item quantity each name contributes to the pool. Progressive items have
# one per gated mission; everything else is a single copy (filler is topped up
# separately to match the location count).
ITEM_QUANTITIES: dict[str, int] = {
    data.progressive_item_name(giver): data.progressive_item_count(giver)
    for giver in data.STORY_GIVERS
}
