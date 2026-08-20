"""Item tables. Names, ids, classification, and groups, derived from data.py.

Classification is decided here in one place. Progressive giver unlocks, area
access, the business property ownerships, every content lock, and every ability
item except Crouch are progression; package rewards, emergency-vehicle rewards,
radio stations, the minimap, the safehouse ownerships, and Crouch are useful;
cash denominations, the weapon pickup, the health and armor top-ups, and the
wanted-level clear are filler; the trap items are traps. Money amounts never
gate logic, so cash is never progression.
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
    + [data.PACKAGE_FRAGMENT_ITEM]
    + data.TRAP_ITEMS
    + data.RADIO_STATION_ITEMS
    + data.PROPERTY_OWNERSHIP_ITEMS
    + [data.MINIMAP_ITEM]
    + data.ABILITY_ITEMS
    + data.CONTENT_ITEMS
)

# The ordered names as the id table read them, so a test can see a duplicate the
# dict below would silently collapse.
ORDERED_ITEM_NAMES: list[str] = list(_ORDERED_ITEM_NAMES)

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
    if name in data.BUSINESS_OWNERSHIP_ITEMS:
        # A business ownership gates its venue missions or, for Pole Position,
        # counts toward the finale's asset threshold, so logic may require it.
        return ItemClassification.progression
    if name == data.PACKAGE_FRAGMENT_ITEM:
        # A goal macguffin: progression so the generator guarantees enough are
        # reachable, skip_balancing because there are many and none unlocks
        # anything, so they must not distort progression balancing.
        return ItemClassification.progression_skip_balancing
    if name in data.CONTENT_ITEMS:
        # A content lock gates every check in its class, and stays progression
        # even in a seed whose class toggle is off and the item gates nothing:
        # the Sprint precedent, so a term found later needs no classification
        # flip.
        return ItemClassification.progression
    if name in data.ABILITY_ITEMS:
        # Crouch gates nothing, so it is useful; every other locked ability may
        # appear in a rule. Sprint and Jump hold no term today but stay
        # progression, so a term found in the runthrough needs no
        # classification flip.
        return (ItemClassification.useful if name in data.ABILITY_USEFUL_ITEMS
                else ItemClassification.progression)
    if (name in data.PACKAGE_REWARD_ITEMS or name in data.EMERGENCY_REWARD_ITEMS
            or name in data.RADIO_STATION_ITEMS
            or name in data.SAFEHOUSE_OWNERSHIP_ITEMS
            or name == data.MINIMAP_ITEM):
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
    "Property Ownership": list(data.PROPERTY_OWNERSHIP_ITEMS),
    "Abilities": list(data.ABILITY_ITEMS),
    "Content Locks": list(data.CONTENT_ITEMS),
}

# The item quantity each name contributes to the pool. Progressive items have
# one per gated mission; everything else is a single copy (filler is topped up
# separately to match the location count).
ITEM_QUANTITIES: dict[str, int] = {
    data.progressive_item_name(strand): data.progressive_item_count(strand)
    for strand in data.progressive_strands()
}
