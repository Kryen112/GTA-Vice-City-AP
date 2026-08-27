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
  station item writes one to its station unlock global; the Minimap item
  writes one to the minimap unlock global.
- item_effects: AP item id -> a one-shot effect descriptor. The ASI applies
  each consumable (cash, weapon, health, armor, clear_wanted) and trap (trap_*)
  once past the saved applied-index; like all item application, every effect
  waits for the player to be controllable.
- config_globals: config-flag global index -> value. The ASI stamps these once
  from slot_data so the main.scm knows whether each reward group is shuffled.
  With the properties class disabled the map also carries the vanilla-collapse
  writes (properties_vanilla_globals), maxing the venue unlock and ownership
  globals so every property gate reduces to purchase-only. Not every key is a
  reserved global: with the pickup randomizer on the map also carries a VANILLA
  script flag below the reserved block (pickups_randomized_globals), so nothing
  downstream may filter this map to the reserved range.
- completion_watch: completion global index -> AP location id. The mission or
  collectible sets its completion global to one when done; the ASI polls these
  and reports the location.

The main.scm reads each strand's unlock global in its launcher gate and writes
each location's completion global on completion, at these same indices.
"""

from __future__ import annotations

from . import data, district_data, items, locations, package_data

# The reserved block starts here, clear of the vanilla maximum global ($8583).
RESERVED_BASE = 9000
# Every ambient pickup slot's handle lives in a vanilla global. The generated
# APPICK watcher polls all 110 of them, and one at or above the reserved base
# would be a global the mod also writes, so the check would fire on whatever the
# mod put there. Asserted here because this is where the base is defined.
assert all(handle < RESERVED_BASE
           for handle in data.PICKUP_HANDLE_GLOBALS), (
    "a pickup handle global sits inside the reserved block"
)

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
# watcher decodes, calls set_radio_channel, and resets it to zero.
RADIO_RANDOMIZED_GLOBAL = EMERGENCY_SHUFFLED_GLOBAL + 1
RADIO_STATION_COUNT = 9
RADIO_UNLOCK_BASE = RADIO_RANDOMIZED_GLOBAL + 1
RADIO_RESOLVE_BASE = RADIO_UNLOCK_BASE + RADIO_STATION_COUNT
RADIO_REQUEST_GLOBAL = RADIO_RESOLVE_BASE + RADIO_STATION_COUNT

# Property ownership globals follow the radio block, one per purchasable
# property in purchase order. The ASI writes one when the property's ownership
# item is received (through item_globals like any unlock); the main.scm gates
# venue missions, the safehouse and business save threads, and the Pole Position
# and Sunshine Autos asset-completion recognitions on them, alongside each
# purchase's completion global. What a purchase physically opens up, a venue's
# doors and gates, stays at the purchase. With the properties class disabled the client
# instead stamps every ownership global through config_globals
# (properties_vanilla_globals below), so the static gates collapse to
# purchase-only, the vanilla semantics.
OWNERSHIP_BASE = RADIO_REQUEST_GLOBAL + 1
OWNERSHIP_KEYS: list[str] = list(data.PROPERTY_OWNERSHIP_ITEMS)

# Minimap globals follow the ownership block. Both are ASI-facing only (the
# main.scm never reads them; they persist inside saves like every reserved
# global): the shuffled flag gates the ASI's per-frame radar enforcement, and
# the unlock global receives one when the Minimap item arrives, through
# item_globals like any unlock. While the flag is set and the unlock is zero
# the ASI holds the game's script-facing radar-hide flag; on unlock it
# releases the flag back to the game once.
MINIMAP_SHUFFLED_GLOBAL = OWNERSHIP_BASE + len(OWNERSHIP_KEYS)
MINIMAP_UNLOCK_GLOBAL = MINIMAP_SHUFFLED_GLOBAL + 1

# Class-cash flags follow the minimap globals, one per check class whose
# one-time completion cash the main.scm suppresses while the class is enabled
# (the AP check is the reward; the suppressed amounts return as the filler
# mirror). At zero everything pays vanilla, the toggle invariant. Side events
# and the Sunshine Autos races suppress the first completion only, so replay
# prizes stay grindable; repeatable earnings (emergency pay, till cash,
# in-mission bonuses) are never touched.
SIDE_EVENTS_CASH_GLOBAL = MINIMAP_UNLOCK_GLOBAL + 1
STUNT_JUMPS_CASH_GLOBAL = SIDE_EVENTS_CASH_GLOBAL + 1
RAMPAGES_CASH_GLOBAL = STUNT_JUMPS_CASH_GLOBAL + 1
PROPERTIES_CASH_GLOBAL = RAMPAGES_CASH_GLOBAL + 1

# One while the shuffle_shops class is on, stamped from slot_data. The shop
# threads read it before they hide what a shop sells or withhold what it hands
# over, so a seed without the class behaves exactly as vanilla does: the wall
# wears its own model and the first purchase pays out. A check class that is off
# leaves no trace in the world, and the shops are the one place the script would
# otherwise act on the completion global alone.
SHOPS_ENABLED_GLOBAL = PROPERTIES_CASH_GLOBAL + 1

# Ability lock globals follow the class-cash flags, ASI-facing only (the
# main.scm never reads them; as reserved globals they persist inside saves, so
# the locks keep enforcing offline from a save, the minimap pattern). One
# lock-flag global per ability item (one while the item's ability_locks key is
# selected, stamped from slot_data), then one unlock global per item (one when
# the item is received, through item_globals like any unlock). The ASI
# enforces a lock per frame while its flag is set and its unlock is zero.
# Order is data.ABILITY_ITEMS and never reorders. The content lock block sits
# directly above this one.
ABILITY_KEYS: list[str] = list(data.ABILITY_ITEMS)
ABILITY_LOCK_FLAG_BASE = SHOPS_ENABLED_GLOBAL + 1
ABILITY_UNLOCK_BASE = ABILITY_LOCK_FLAG_BASE + len(ABILITY_KEYS)

# Content lock globals follow the ability block in the same shape: one lock
# flag per content item (one while its content_locks key is selected, stamped
# from slot_data), then one unlock global per item (one when the item is
# received). Unlike the ability block the main.scm DOES read two of these: the
# stunt jump and store classes have no icon to hold, so their gates live in the
# script, while holding the other three belongs to the ASI. Order is
# data.CONTENT_ITEMS and never reorders. The SCM-internal marker scratch begins
# right above this block.
CONTENT_KEYS: list[str] = list(data.CONTENT_ITEMS)
CONTENT_LOCK_FLAG_BASE = ABILITY_UNLOCK_BASE + len(ABILITY_KEYS)
CONTENT_UNLOCK_BASE = CONTENT_LOCK_FLAG_BASE + len(CONTENT_KEYS)

# District content unlock globals: one per class per district, a uniform grid
# rather than only the pairs that hold something, so a class and a district
# index by formula.
#
# The districts here are the ones holding something a content key covers, not
# every district on the map. The Junk Yard is the difference: it holds two
# ambient pickups and nothing of the five classes, so no gate could ever read
# its column and reserving one would push the block into the marker scratch for
# a district with nothing to hold. Every district that HAS content of a class
# still gets its cell, empty pairs included, so the formula stands.
#
# These are what the game actually reads, at every granularity. An item releases
# the globals it covers (content_district_globals below), so a whole-class item
# releases all eleven of its class's and the script needs no idea which mode the
# seed chose: one code path, and no gate has to ask. The per-class unlock
# globals above stay, still driven by item_globals, since they are what tells the
# ASI a whole class went at once for its own status listing.
DISTRICT_KEYS: list[str] = list(data.CONTENT_DISTRICTS)
DISTRICT_UNLOCK_BASE = CONTENT_UNLOCK_BASE + len(CONTENT_KEYS)
DISTRICT_UNLOCK_COUNT = len(CONTENT_KEYS) * len(DISTRICT_KEYS)

# The finale warp flag sits one below the top of the reserved block. The client sets it in the status
# frame once the hidden-packages goal is met and the ASI writes it here; the
# main.scm's APFIN watcher reads it and launches Keep Your Friends Close...
# straight into its ending cutscene, wherever the player is standing. A hunt goal
# ends the story the way the story ends, so the last fragment plays the ending
# rather than leaving the finale to be walked into. Nothing else reads it: the
# other two goals cannot be met before that mission has passed, and the watcher
# holds on the mission's own passed flag, so a game that has seen the ending
# never sees it again.
FINALE_WARP_GLOBAL = DISTRICT_UNLOCK_BASE + DISTRICT_UNLOCK_COUNT

# The finale raises this while it runs and drops it at its single exit, so the
# ASI can keep the ambient pickup layout off the pool for the length of the
# mansion siege: that fight places its own pickups to be survived with, and one
# ambient slot stands in the same grounds.
#
# On top of the block and derived like every other base. The unused space lower
# down looks free and is not: build_scm.py takes every one of those for scratch,
# and the package watcher alone touches RESERVED_BASE + 6 a hundred and one
# times, once to write the collected count and a hundred to compare against it.
FINALE_ACTIVE_GLOBAL = FINALE_WARP_GLOBAL + 1


def unlock_global(key: str) -> int:
    return UNLOCK_BASE + UNLOCK_KEYS.index(key)


def ownership_global(item_name: str) -> int:
    return OWNERSHIP_BASE + OWNERSHIP_KEYS.index(item_name)


def completion_global(location_name: str) -> int:
    return COMPLETION_BASE + _ORDERED_LOCATION_NAMES.index(location_name)


def reward_global(item_name: str) -> int:
    return REWARD_BASE + REWARD_KEYS.index(item_name)


def ability_lock_flag_global(item_name: str) -> int:
    return ABILITY_LOCK_FLAG_BASE + ABILITY_KEYS.index(item_name)


def ability_unlock_global(item_name: str) -> int:
    return ABILITY_UNLOCK_BASE + ABILITY_KEYS.index(item_name)


def content_lock_flag_global(item_name: str) -> int:
    return CONTENT_LOCK_FLAG_BASE + CONTENT_KEYS.index(item_name)


def content_unlock_global(item_name: str) -> int:
    return CONTENT_UNLOCK_BASE + CONTENT_KEYS.index(item_name)


def district_unlock_global(content_item: str, district: str) -> int:
    return (DISTRICT_UNLOCK_BASE
            + CONTENT_KEYS.index(content_item) * len(DISTRICT_KEYS)
            + DISTRICT_KEYS.index(district))


def content_district_globals() -> dict[int, list[int]]:
    """AP item id -> every district unlock global that item releases.

    One entry per content item the item table holds, all three granularities at
    once, because the table is one table for every seed and a seed only ever
    receives the items it placed. A whole-class item lists its class's eleven, a
    district item lists one per class that has content there, and a class-in-one-
    district item lists exactly one.
    """
    mapping: dict[int, list[int]] = {}
    for content_item in data.CONTENT_ITEMS:
        mapping[items.ITEM_NAME_TO_ID[content_item]] = [
            district_unlock_global(content_item, district)
            for district in DISTRICT_KEYS
        ]
    for district in data.CONTENT_DISTRICTS:
        item_id = items.ITEM_NAME_TO_ID[data.district_content_item_name(district)]
        mapping[item_id] = [
            district_unlock_global(content_item, district)
            for content_item in data.CONTENT_ITEMS
            if district in data.CONTENT_CLASS_DISTRICTS[content_item]
        ]
    for content_item in data.CONTENT_ITEMS:
        for district in data.CONTENT_CLASS_DISTRICTS[content_item]:
            item_id = items.ITEM_NAME_TO_ID[
                data.district_class_item_name(district, content_item)]
            mapping[item_id] = [district_unlock_global(content_item, district)]
    return mapping


# What a district unlock holds. Zero is the absence of these: still held.
# The script's gates ask ">= 1", so released and absent both pass, and the
# difference is only for the status page, which must not offer a district that
# holds nothing of a class as somewhere the player can now go and collect.
DISTRICT_RELEASED = 1
DISTRICT_ABSENT = 2


def unlocked_district_globals(selected_keys: frozenset[str]) -> dict[int, int]:
    """Global index -> released or absent for every district unlock no item covers.

    Every gate the script makes for the two classes with no icon is a single
    condition, "this district is released", and so is every hold the ASI makes.
    That works only if the globals no item covers start released, which is what
    this stamps at config time. Without it each gate would have to ask whether
    the class was locked at all, which the script cannot express in one
    condition, and the toggle invariant would need a second code path. This
    function is therefore the whole of that invariant: with no key selected it
    stamps the entire block.

    Two kinds of global qualify. A class the seed does not lock, which is the
    invariant proper. And a class-district pair holding no content of that class
    at all, in any seed: 13 of the 55 pairs, since Leaf Links has only packages
    and Escobar International no properties. Those get no item either, so
    leaving them zero would read as permanently held, which the ASI's own
    accounting believes: a class would report as part-held on the status page
    forever, and a pickup the district table failed to place would never be
    released by anything.

    The two kinds are stamped apart, DISTRICT_RELEASED and DISTRICT_ABSENT, and
    every gate passes either since all of them ask ">= 1". The page is what needs
    them apart: a district holding no content of a class is not somewhere the
    class became available, so counting it as released told the player Leaf Links
    rampages were theirs to collect, and read the five districts that are all the
    robbable stores there are as five of eleven.
    """
    stamped: dict[int, int] = {}
    for content_item in CONTENT_KEYS:
        locked = data.CONTENT_ITEM_KEY[content_item] in selected_keys
        for district in DISTRICT_KEYS:
            if district not in data.CONTENT_CLASS_DISTRICTS[content_item]:
                # Absence outranks the lock state: it is true of every seed, and
                # an unlocked class is not displayed at all.
                stamped[district_unlock_global(content_item, district)] = DISTRICT_ABSENT
            elif not locked:
                stamped[district_unlock_global(content_item, district)] = DISTRICT_RELEASED
    return stamped


def content_districts() -> list[dict]:
    """Where every holdable pickup is and which district it belongs to.

    The three classes the ASI holds are found in the pickup pool by type or
    model, which says what a pickup is but not where, and the district table is
    keyed by index rather than by position. This joins the two, so the ASI can
    put a pool entry in a district without carrying the audit itself. Coordinates
    only, since a held pickup keeps its x and y and only sinks in z.
    """
    positions: list[tuple[str, list[str], list[tuple[float, float, float]]]] = [
        (data.HIDDEN_PACKAGES_ITEM, district_data.PACKAGE_DISTRICTS,
         package_data.PACKAGE_COORDS),
        (data.RAMPAGES_ITEM, district_data.RAMPAGE_DISTRICTS,
         district_data.RAMPAGE_COORDS),
        (data.PROPERTY_PURCHASES_ITEM,
         [district_data.PROPERTY_DISTRICTS[purchase.removesuffix(" Purchase")]
          for purchase in data.PROPERTY_PURCHASES],
         [district_data.PROPERTY_COORDS[purchase.removesuffix(" Purchase")]
          for purchase in data.PROPERTY_PURCHASES]),
    ]
    entries: list[dict] = []
    for content_item, districts, coordinates in positions:
        for district, (x, y, _z) in zip(districts, coordinates, strict=True):
            entries.append({"x": x, "y": y,
                            "class": CONTENT_KEYS.index(content_item),
                            "district": DISTRICT_KEYS.index(district)})
    return entries


def highest_reserved_global() -> int:
    return FINALE_ACTIVE_GLOBAL


def reserved_global_map() -> dict[str, int]:
    """Every reserved global this module hands out, by a name for it.

    Published so the numbering can be frozen the way the ids are, and it needs
    freezing for a reason the ids do not have: these numbers are compiled into
    main.scm and the CLEO scripts and written into save files, so a global that
    moves does not merely mislabel a check, it points a running seed's save at
    the wrong word. Every block below is numbered from a list's ORDER, so
    inserting a strand, a reward, a district or an ability renumbers everything
    after it in silence.

    Prefixed keys rather than nested maps, so one comparison covers the lot and
    a block added later cannot be a block nobody compares.
    """
    reserved = {
        "base:SEED_HASH_BASE": SEED_HASH_BASE,
        "base:APPLIED_INDEX_GLOBAL": APPLIED_INDEX_GLOBAL,
        "base:UNLOCK_BASE": UNLOCK_BASE,
        "base:COMPLETION_BASE": COMPLETION_BASE,
        "base:REWARD_BASE": REWARD_BASE,
        "base:PACKAGES_SHUFFLED_GLOBAL": PACKAGES_SHUFFLED_GLOBAL,
        "base:EMERGENCY_SHUFFLED_GLOBAL": EMERGENCY_SHUFFLED_GLOBAL,
        "base:RADIO_RANDOMIZED_GLOBAL": RADIO_RANDOMIZED_GLOBAL,
        "base:RADIO_UNLOCK_BASE": RADIO_UNLOCK_BASE,
        "base:RADIO_RESOLVE_BASE": RADIO_RESOLVE_BASE,
        "base:RADIO_REQUEST_GLOBAL": RADIO_REQUEST_GLOBAL,
        "base:OWNERSHIP_BASE": OWNERSHIP_BASE,
        "base:MINIMAP_SHUFFLED_GLOBAL": MINIMAP_SHUFFLED_GLOBAL,
        "base:MINIMAP_UNLOCK_GLOBAL": MINIMAP_UNLOCK_GLOBAL,
        "base:SIDE_EVENTS_CASH_GLOBAL": SIDE_EVENTS_CASH_GLOBAL,
        "base:STUNT_JUMPS_CASH_GLOBAL": STUNT_JUMPS_CASH_GLOBAL,
        "base:RAMPAGES_CASH_GLOBAL": RAMPAGES_CASH_GLOBAL,
        "base:PROPERTIES_CASH_GLOBAL": PROPERTIES_CASH_GLOBAL,
        "base:SHOPS_ENABLED_GLOBAL": SHOPS_ENABLED_GLOBAL,
        "base:ABILITY_LOCK_FLAG_BASE": ABILITY_LOCK_FLAG_BASE,
        "base:ABILITY_UNLOCK_BASE": ABILITY_UNLOCK_BASE,
        "base:CONTENT_LOCK_FLAG_BASE": CONTENT_LOCK_FLAG_BASE,
        "base:CONTENT_UNLOCK_BASE": CONTENT_UNLOCK_BASE,
        "base:DISTRICT_UNLOCK_BASE": DISTRICT_UNLOCK_BASE,
        "base:FINALE_WARP_GLOBAL": FINALE_WARP_GLOBAL,
        "base:FINALE_ACTIVE_GLOBAL": FINALE_ACTIVE_GLOBAL,
    }
    for word in range(SEED_HASH_GLOBAL_COUNT):
        reserved[f"seed hash:{word}"] = SEED_HASH_BASE + word
    for key in UNLOCK_KEYS:
        reserved[f"unlock:{key}"] = unlock_global(key)
    for location_name in _ORDERED_LOCATION_NAMES:
        reserved[f"completion:{location_name}"] = completion_global(location_name)
    for item_name in REWARD_KEYS:
        reserved[f"reward:{item_name}"] = reward_global(item_name)
    for item_name in OWNERSHIP_KEYS:
        reserved[f"ownership:{item_name}"] = ownership_global(item_name)
    for station in range(RADIO_STATION_COUNT):
        reserved[f"radio unlock:{station}"] = RADIO_UNLOCK_BASE + station
        reserved[f"radio resolve:{station}"] = RADIO_RESOLVE_BASE + station
    for item_name in ABILITY_KEYS:
        reserved[f"ability lock:{item_name}"] = ability_lock_flag_global(item_name)
        reserved[f"ability unlock:{item_name}"] = ability_unlock_global(item_name)
    for item_name in CONTENT_KEYS:
        reserved[f"content lock:{item_name}"] = content_lock_flag_global(item_name)
        reserved[f"content unlock:{item_name}"] = content_unlock_global(item_name)
        for district in DISTRICT_KEYS:
            reserved[f"district unlock:{item_name}|{district}"] = (
                district_unlock_global(item_name, district))
    # The top of the block, frozen deliberately and not merely as a duplicate of
    # the last global: add_markers.py sizes the marker scratch from it, so where
    # the reserved block ends is itself a number main.scm is built against.
    reserved["base:highest_reserved_global"] = highest_reserved_global()
    return reserved


def mainland_routes(split_mainland_access: bool) -> list[dict]:
    """Every crossing off the start island, for the ASI to announce and to list.

    The ASI needs three things it cannot work out for itself: which globals are
    crossings, what to call them, and whether the seed split the mainland ones,
    since item_globals maps every area item whatever the setting. It gets them
    here rather than mirroring the layout or the names, so this stays the only
    place a crossing is named. One mainland entry means the routes are whole and
    Mainland Access opens them together; four means they are split. A route
    needing a second item carries it, which is the causeway and the island its
    gate stands on.

    Starfish Island is one of these and used to be missing, which left the page
    silent about the crossing a player asks about as often as any bridge. It is
    listed last because it is the one a mainland route can depend on.
    """
    starfish = "Starfish Island Access"
    starfish_row = {
        "global": unlock_global(starfish),
        "label": "Starfish Island",
        "needs_global": 0,
        "needs_label": "",
    }
    if not split_mainland_access:
        return [{"global": unlock_global(data.AREA_ITEM_BY_REGION[data.REGION_MAINLAND]),
                 "label": "The mainland", "needs_global": 0, "needs_label": ""},
                starfish_row]
    routes: list[dict] = []
    for crossing, also in data.MAINLAND_CROSSINGS.items():
        # One extra requirement is all a route can carry over the wire, and all
        # any crossing has. A second would be dropped here and the route would
        # then announce itself open with that item still missing.
        assert len(also) <= 1, crossing
        needs = also[0] if also else None
        routes.append({
            "global": unlock_global(crossing),
            "label": crossing,
            "needs_global": unlock_global(needs) if needs else 0,
            "needs_label": needs or "",
        })
    assert all(route["needs_label"] in ("", starfish) for route in routes)
    routes.append(starfish_row)
    return routes


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
    for ownership in data.PROPERTY_OWNERSHIP_ITEMS:
        mapping[items.ITEM_NAME_TO_ID[ownership]] = ownership_global(ownership)
    mapping[items.ITEM_NAME_TO_ID[data.MINIMAP_ITEM]] = MINIMAP_UNLOCK_GLOBAL
    for ability in data.ABILITY_ITEMS:
        mapping[items.ITEM_NAME_TO_ID[ability]] = ability_unlock_global(ability)
    for content in data.CONTENT_ITEMS:
        mapping[items.ITEM_NAME_TO_ID[content]] = content_unlock_global(content)
    return mapping


def properties_vanilla_globals() -> dict[int, int]:
    """Global index -> value the client adds to config_globals when the
    properties class is disabled, so the game behaves fully vanilla: the venue
    unlock globals maxed (every gate's progressive condition always holds) and
    every ownership global set (every ownership condition always holds),
    leaving each purchase's completion global as the only live condition, the
    vanilla purchase-grants-everything semantics."""
    globals_map = {
        unlock_global(venue): len(missions)
        for venue, missions in data.VENUE_STRANDS.items()
    }
    globals_map.update({
        ownership_global(ownership): 1
        for ownership in data.PROPERTY_OWNERSHIP_ITEMS
    })
    return globals_map


def pickups_randomized_globals() -> dict[int, int]:
    """Global index -> value the client adds to config_globals when the pickup
    randomizer is on.

    The vanilla script shows a one-time help text the first time any police
    bribe pickup is collected, explaining that the star lowers the wanted level.
    It fires on whatever model the shuffle put on a bribe spot, so it describes
    an item that is no longer there. The text is guarded by the vanilla
    already-shown flag, so stamping that flag retires the text for the seed.

    Only this one text is model-specific: the other first-collection texts key
    on the four INFO tutorial icons, which are not ambient pickups and which the
    shuffle never touches.

    The stamp reaches one step further, which is accepted rather than unnoticed.
    The same flag is one of six the vanilla HELP thread ANDs to decide it has
    shown everything and can end, so with it pre-stamped the thread can end
    without a bribe ever being collected. Two one-time texts sit past that check
    and are lost in a seed where vanilla would still have shown them: the
    wanted-level tip and the bridges-reopened help. Both are tutorial text, and
    the mod drives the bridges from the area item anyway."""
    return {data.BRIBE_HELP_SHOWN_FLAG: 1}


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
                 radio_randomized: bool, minimap_shuffled: bool) -> dict[int, int]:
    """Config-flag global index -> value the ASI stamps once from slot_data.

    Each value is the EFFECTIVE shuffled state (whether the reward items are
    actually in the pool), so the SCM only suppresses a vanilla grant when an AP
    item exists to replace it. The caller must AND in the owning check-class
    toggle, matching _item_enabled. The radio and minimap flags have no owning
    class: when their option is on their items are always in the pool."""
    return {
        PACKAGES_SHUFFLED_GLOBAL: int(bool(packages_shuffled)),
        EMERGENCY_SHUFFLED_GLOBAL: int(bool(emergency_shuffled)),
        RADIO_RANDOMIZED_GLOBAL: int(bool(radio_randomized)),
        MINIMAP_SHUFFLED_GLOBAL: int(bool(minimap_shuffled)),
    }


def shops_enabled_flag(shops: bool) -> dict[int, int]:
    """The shuffle_shops flag global -> the raw class toggle.

    Its own function rather than a fifth argument above, because those four are
    effective SHUFFLED states, meaning an AP item exists to replace a vanilla
    grant. This one is the class toggle itself: with the class off the shops are
    vanilla, and there is no reward being replaced to reason about.
    """
    return {SHOPS_ENABLED_GLOBAL: int(bool(shops))}


def class_cash_flags(side_events: bool, stunt_jumps: bool,
                     rampages: bool, properties: bool) -> dict[int, int]:
    """Class-cash flag global index -> value the ASI stamps once from
    slot_data. Each value is the raw check-class toggle: while a class is
    enabled its one-time completion cash is suppressed in the main.scm (the
    AP check is the reward, mirrored back as filler); while it is disabled
    the cash pays vanilla, the toggle invariant. Unlike config_flags there is
    no item-existence AND, because no single item replaces the cash."""
    return {
        SIDE_EVENTS_CASH_GLOBAL: int(bool(side_events)),
        STUNT_JUMPS_CASH_GLOBAL: int(bool(stunt_jumps)),
        RAMPAGES_CASH_GLOBAL: int(bool(rampages)),
        PROPERTIES_CASH_GLOBAL: int(bool(properties)),
    }


def ability_lock_flags(selected_keys: set[str]) -> dict[int, int]:
    """Ability lock-flag global index -> value the ASI stamps once from
    slot_data. One while the item's ability starts locked this seed (its
    ability_locks key is selected, which also puts the item in the pool);
    zero leaves that ability fully vanilla, the toggle invariant. All eight
    flags are always stamped so a stale save state cannot linger."""
    locked_items = {
        item for key in selected_keys for item in data.ABILITY_LOCK_ITEMS[key]
    }
    return {
        ability_lock_flag_global(item): int(item in locked_items)
        for item in ABILITY_KEYS
    }


def content_lock_flags(selected_keys: set[str]) -> dict[int, int]:
    """Content lock-flag global index -> value the ASI stamps once from
    slot_data. One while the class starts held this seed (its content_locks
    key is selected, which also puts the item in the pool); zero leaves that
    class fully vanilla. A key holds its class whether or not the class is
    also a check class, so this reads content_locks alone. All five flags are
    always stamped so a stale save state cannot linger."""
    locked_items = {data.CONTENT_LOCK_ITEMS[key] for key in selected_keys}
    return {
        content_lock_flag_global(item): int(item in locked_items)
        for item in CONTENT_KEYS
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
