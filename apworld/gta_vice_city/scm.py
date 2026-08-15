"""Reserved SCM global layout and the item-to-global contract.

The custom main.scm, the ASI, and this module must agree on these indices. All
reserved globals live above the vanilla maximum ($8583) so they never collide
with the game's own. Global $N is stored at ScriptSpace[N*4]; the ASI writes
the unlock globals from received-item counts and polls the completion globals,
both keyed by the indices here.

Contract shipped to the client (and on to the ASI) in slot_data:
- item_globals: AP item id -> the count global it adds one to. The ASI counts
  received copies of each item and writes the total to that global. Progressive
  giver unlocks count up per strand; an area item writes one; a persistent
  reward writes one, which the main.scm re-gates its vanilla grant on; a radio
  station item writes one to its station unlock global.
- item_effects: AP item id -> a one-shot effect descriptor. The ASI applies
  each consumable (cash, weapon, health, armor, clear_wanted) and trap (trap_*)
  once past the saved applied-index; like all item application, every effect
  waits for the player to be controllable.
- config_globals: config-flag global index -> value. The ASI stamps these once
  from slot_data so the main.scm knows whether each reward group is shuffled.
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

# Persistent-reward globals follow the completion block. The ASI sets each to
# one when its item is received (through item_globals, like an unlock count),
# and the main.scm re-gates the vanilla respawning grant on it.
REWARD_BASE = COMPLETION_BASE + len(_ORDERED_LOCATION_NAMES)
REWARD_KEYS: list[str] = list(data.PERSISTENT_REWARD_ITEMS)

# Config flags the ASI stamps once from slot_data so the main.scm knows whether
# each reward group is shuffled (AP-gated, vanilla trigger suppressed) or
# vanilla. They sit just above the reward block.
PACKAGES_SHUFFLED_GLOBAL = REWARD_BASE + len(REWARD_KEYS)
EMERGENCY_SHUFFLED_GLOBAL = PACKAGES_SHUFFLED_GLOBAL + 1

# Radio globals follow the config flags. The randomized flag gates the ASI's
# radio enforcement. The nine unlock globals (engine station id order, 0
# Wildstyle through 8 Wave 103) each receive one when their station item is
# received, through item_globals like any unlock. From them the ASI recomputes
# the nine resolve globals every frame: station -> itself when unlocked, else
# the next unlocked station scanning upward with wraparound. The main.scm's
# scripted set_radio_channel sites read the resolve globals (the foundation
# initializes them to identity, so with the option off they are vanilla). The
# request global carries an ASI-requested retune to the APRADIO watcher,
# encoded station id plus one so the zero-initialized global idles; the
# watcher decodes, calls set_radio_channel, and resets it to zero. The whole
# block must stay below $9400, where the SCM-internal marker handles begin.
RADIO_RANDOMIZED_GLOBAL = EMERGENCY_SHUFFLED_GLOBAL + 1
RADIO_STATION_COUNT = 9
RADIO_UNLOCK_BASE = RADIO_RANDOMIZED_GLOBAL + 1
RADIO_RESOLVE_BASE = RADIO_UNLOCK_BASE + RADIO_STATION_COUNT
RADIO_REQUEST_GLOBAL = RADIO_RESOLVE_BASE + RADIO_STATION_COUNT


def unlock_global(key: str) -> int:
    return UNLOCK_BASE + UNLOCK_KEYS.index(key)


def completion_global(location_name: str) -> int:
    return COMPLETION_BASE + _ORDERED_LOCATION_NAMES.index(location_name)


def reward_global(item_name: str) -> int:
    return REWARD_BASE + REWARD_KEYS.index(item_name)


def highest_reserved_global() -> int:
    return RADIO_REQUEST_GLOBAL


def item_globals() -> dict[int, int]:
    """AP item id -> the count global it contributes one to (unlock or reward)."""
    mapping: dict[int, int] = {}
    for strand in data.progressive_strands():
        item_id = items.ITEM_NAME_TO_ID[data.progressive_item_name(strand)]
        mapping[item_id] = unlock_global(strand)
    for area_item in data.AREA_ITEMS:
        mapping[items.ITEM_NAME_TO_ID[area_item]] = unlock_global(area_item)
    for reward in data.PERSISTENT_REWARD_ITEMS:
        mapping[items.ITEM_NAME_TO_ID[reward]] = reward_global(reward)
    for index, station in enumerate(data.RADIO_STATION_ITEMS):
        mapping[items.ITEM_NAME_TO_ID[station]] = RADIO_UNLOCK_BASE + index
    return mapping


def item_effects() -> dict[int, list]:
    """AP item id -> one-shot effect descriptor [type, *params], applied once by
    the ASI past the saved applied-index. Covers the consumables (cash, weapon,
    health, armor, clear_wanted) and the traps (trap_*); the ASI holds every
    effect until the player is controllable and reverts the timed traps after
    their duration."""
    combined = {**data.CONSUMABLE_EFFECTS, **data.TRAP_EFFECTS}
    return {
        items.ITEM_NAME_TO_ID[name]: [effect[0], *effect[1:]]
        for name, effect in combined.items()
    }


def config_flags(packages_shuffled: bool, emergency_shuffled: bool,
                 radio_randomized: bool) -> dict[int, int]:
    """Config-flag global index -> value the ASI stamps once from slot_data.

    Each value is the EFFECTIVE shuffled state (whether the reward items are
    actually in the pool), so the SCM only suppresses a vanilla grant when an AP
    item exists to replace it. The caller must AND in the owning check-class
    toggle, matching _item_enabled. The radio flag has no owning class: when the
    option is on the station items are always in the pool."""
    return {
        PACKAGES_SHUFFLED_GLOBAL: int(bool(packages_shuffled)),
        EMERGENCY_SHUFFLED_GLOBAL: int(bool(emergency_shuffled)),
        RADIO_RANDOMIZED_GLOBAL: int(bool(radio_randomized)),
    }


def completion_watch() -> dict[int, int]:
    """Completion global index -> AP location id."""
    return {
        completion_global(name): location_id
        for name, location_id in locations.LOCATION_NAME_TO_ID.items()
    }


def package_coords() -> dict[int, list[float]]:
    """Package completion global index -> [x, y, z] world position.

    The ASI matches a collected collectable pickup to its package by coordinate
    and sets that package's completion global, so each hidden package is its own
    check. Index order follows the SCM create_collectable1 placement order.
    """
    return {
        completion_global(name): list(data.PACKAGE_COORDS[index])
        for index, name in enumerate(locations.PACKAGE_NAMES)
    }
