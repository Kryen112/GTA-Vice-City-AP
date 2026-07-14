"""Reserved SCM global layout and the item-to-global contract.

The custom main.scm, the ASI, and this module must agree on these indices. All
reserved globals live above the vanilla maximum ($8583) so they never collide
with the game's own. Global $N is stored at ScriptSpace[N*4]; the ASI writes
the unlock globals from received-item counts and polls the completion globals,
both keyed by the indices here.

Contract shipped to the client (and on to the ASI) in slot_data:
- item_globals: AP item id -> the unlock global it adds one to. The ASI counts
  received copies of each item and writes the total to that global. Progressive
  giver unlocks count up per strand; an area item writes one.
- completion_watch: completion global index -> AP location id. The mission or
  collectible sets its completion global to one when done; the ASI polls these
  and reports the location.

The main.scm reads each strand's unlock global in its launcher gate and writes
each location's completion global on completion, at these same indices.
"""

from __future__ import annotations

from . import data, items, locations

# The reserved block starts here, clear of the vanilla maximum global ($8583).
RESERVED_BASE = 9000
# The seed-and-slot hash, sixteen hex characters packed four per global.
SEED_HASH_BASE = RESERVED_BASE
SEED_HASH_GLOBAL_COUNT = 4
# The last-applied received-item index, so one-shot grants are not re-applied.
APPLIED_INDEX_GLOBAL = RESERVED_BASE + 5
# Unlock globals begin here, leaving a small gap after the bookkeeping globals.
UNLOCK_BASE = RESERVED_BASE + 10

# Every progressive strand, then each area item, in a stable order. Each gets
# one unlock global holding a count (progressive) or one (area).
UNLOCK_KEYS: list[str] = list(data.progressive_strands().keys()) + list(data.AREA_ITEMS)

# Completion globals follow the unlock block, one per location in id order.
COMPLETION_BASE = UNLOCK_BASE + len(UNLOCK_KEYS)
_ORDERED_LOCATION_NAMES: list[str] = list(locations.LOCATION_NAME_TO_ID.keys())


def unlock_global(key: str) -> int:
    return UNLOCK_BASE + UNLOCK_KEYS.index(key)


def completion_global(location_name: str) -> int:
    return COMPLETION_BASE + _ORDERED_LOCATION_NAMES.index(location_name)


def highest_reserved_global() -> int:
    return COMPLETION_BASE + len(_ORDERED_LOCATION_NAMES) - 1


def item_globals() -> dict[int, int]:
    """AP item id -> the unlock global it contributes one to."""
    mapping: dict[int, int] = {}
    for strand in data.progressive_strands():
        item_id = items.ITEM_NAME_TO_ID[data.progressive_item_name(strand)]
        mapping[item_id] = unlock_global(strand)
    for area_item in data.AREA_ITEMS:
        mapping[items.ITEM_NAME_TO_ID[area_item]] = unlock_global(area_item)
    return mapping


def completion_watch() -> dict[int, int]:
    """Completion global index -> AP location id."""
    return {
        completion_global(name): location_id
        for name, location_id in locations.LOCATION_NAME_TO_ID.items()
    }
