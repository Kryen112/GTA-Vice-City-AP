"""Content tables for GTA: Vice City, hand-written from the SCM decompile.

This is plain owned data, not a generated format. Mission names and their
per-giver order come from the vanilla main.scm DEFINE MISSION table. Giver
grouping and the region (island) assignment below are provisional first
readings; the cross-giver edges and island barriers are pinned from the SCM
in a dedicated extraction pass and refined in per-giver Phase 3 audits.
Nothing here gates logic on money.
"""

from __future__ import annotations

from . import district_data, package_data, pickup_data, shop_data

# Story missions grouped by giver, each list in vanilla play order. Progressive
# unlocks follow this order (Progressive <giver> #n opens the giver's nth
# mission). Names are the in-game mission names from the decompile.
STORY_GIVERS: dict[str, list[str]] = {
    "Rosenberg": [
        "An Old Friend", "The Party", "Back Alley Brawl", "Jury Fury", "Riot",
    ],
    "Cortez": [
        "Treacherous Swine", "Mall Shootout", "Guardian Angels",
        "Sir, Yes Sir!", "All Hands On Deck!",
    ],
    "Diaz": [
        "The Chase", "Phnom Penh '86", "The Fastest Boat",
        "Supply & Demand", "Rub Out",
    ],
    "Death Row": [
        "Death Row",
    ],
    "Avery": [
        "Four Iron", "Demolition Man", "Two Bit Hit",
    ],
    "Phil Cassidy": [
        "Gun Runner", "Boomshine Saigon",
    ],
    "Vercetti Protection": [
        "Shakedown", "Bar Brawl", "Cop Land",
    ],
    "Big Mitch Baker": [
        "Alloy Wheels of Steel", "Messing with the Man", "Hog Tied",
    ],
    "Umberto Robina": [
        "Stunt Boat Challenge", "Cannon Fodder", "Naval Engagement",
        "Trojan Voodoo",
    ],
    "Auntie Poulet": [
        "Juju Scramble", "Bombs Away!", "Dirty Lickin's",
    ],
    "Love Fist": [
        "Love Juice", "Psycho Killer", "Publicity Tour",
    ],
    "Mr. Black": [
        "Road Kill", "Waste the Wife", "Autocide",
        "Check Out at the Check In", "Loose Ends",
    ],
    "Vercetti Finale": [
        "Cap the Collector", "Keep Your Friends Close...",
    ],
}

# Venue mission strands, the Properties class. Each venue is bought (a purchase
# check) and then plays its own mission strand. The purchase price is money,
# which is grindable and never a gate, but a venue mission needs its property
# bought in game and the businesses go on sale only when Shakedown passes, so
# venue missions carry the items to pass Shakedown as a requirement (see
# PROPERTY_UNLOCK_MISSION). Progressive unlocks work the same as story givers.
# Sunshine Autos' strand is its four import garage lists, which vanilla chains:
# each list's completion thread starts the next and terminates itself, so the
# play order the progressives impose is the order the game already forces.
VENUE_STRANDS: dict[str, list[str]] = {
    "Malibu Club": ["No Escape?", "The Shootist", "The Driver", "The Job"],
    "Film Studio": [
        "Recruitment Drive", "Dildo Dodo", "Martha's Mug Shot", "G-spotlight",
    ],
    "Printworks": ["Spilling the Beans", "Hit the Courier"],
    "Kaufman Cabs": ["V.I.P.", "Friendly Rivalry", "Cabmaggedon"],
    "Cherry Popper": ["Distribution"],
    "Boatyard": ["Checkpoint Charlie"],
    "Sunshine Autos": [
        "Sunshine Autos Import List 1", "Sunshine Autos Import List 2",
        "Sunshine Autos Import List 3", "Sunshine Autos Import List 4",
    ],
}

# Sunshine Autos' six street races, in the showroom menu's own order: menu arm n
# displays GXT 'RACES0n' and sets vanilla flag $1587+n on its first win. The menu
# wraps 1 through 6 freely with no completion gate, so vanilla opens all six the
# moment the showroom is bought and the only cost is the entry fee, which is
# money. They are flat locations sharing one rule, not a strand.
SUNSHINE_RACES: list[str] = [
    "Sunshine Autos Race: Terminal Velocity",
    "Sunshine Autos Race: Ocean Drive",
    "Sunshine Autos Race: Border Run",
    "Sunshine Autos Race: Capital Cruise",
    "Sunshine Autos Race: Tour!",
    "Sunshine Autos Race: V.C. Endurance",
]

# Venue locations that are not strand missions: a venue's own activities, gated
# alike on the venue being bought and owned and on nothing else. They take their
# island and their ownership term from their venue and carry no progressive
# unlock, so a venue's strand length still names its unlock count.
VENUE_ACTIVITIES: dict[str, list[str]] = {
    "Sunshine Autos": list(SUNSHINE_RACES),
}

# Property purchase checks. The businesses front the venue strands above (plus
# Pole Position, a business with no strand); the rest are safehouses. A
# safehouse is for sale from a new game, so its purchase carries no rule beyond
# its region (money is grindable). A business goes on sale only when Shakedown
# passes, so its purchase also requires the items to pass Shakedown.
PROPERTY_PURCHASES: list[str] = [
    "Printworks Purchase", "Sunshine Autos Purchase", "Film Studio Purchase",
    "Cherry Popper Purchase", "Kaufman Cabs Purchase", "Malibu Club Purchase",
    "Boatyard Purchase", "Pole Position Purchase", "El Swanko Casa Purchase",
    "Links View Apartment Purchase", "Hyman Condo Purchase",
    "Ocean Heights Apartment Purchase", "1102 Washington Street Purchase",
    "3321 Vice Point Purchase", "Skumole Shack Purchase",
]

# The mission that puts the businesses up for sale. Pinned from the vanilla
# decompile: init creates the eight business pickups unavailable, and
# Shakedown's pass path flips all eight to for-sale and starts their buy
# watcher threads; the seven safehouse pickups are for sale from init. In the
# SCM the ownership gate reads each purchase's completion global directly; in
# logic the stand-in is the items to pass this mission.
PROPERTY_UNLOCK_MISSION = "Shakedown"

# The business purchases: the seven venue fronts plus Pole Position.
BUSINESS_PURCHASES: list[str] = [
    f"{venue} Purchase" for venue in VENUE_STRANDS
] + ["Pole Position Purchase"]


def ownership_item_name(property_name: str) -> str:
    # The property's base name, the purchase name without its suffix.
    return f"{property_name} Ownership"


# Property ownership items, one per purchasable property in purchase order.
# Buying a property stays the check; the building itself arrives as this item.
# Nothing a property provides works until it is bought AND owned, in either
# order: a venue's missions, a safehouse's save point and garage, and an
# income asset's completion recognition. The eight business ownerships are
# progression (seven gate venue mission strands, and Pole Position counts
# toward the finale's asset threshold); the seven safehouse ownerships are
# useful, since a save point gates no location.
PROPERTY_OWNERSHIP_ITEMS: list[str] = [
    ownership_item_name(purchase.removesuffix(" Purchase"))
    for purchase in PROPERTY_PURCHASES
]

BUSINESS_OWNERSHIP_ITEMS: list[str] = [
    ownership_item_name(purchase.removesuffix(" Purchase"))
    for purchase in BUSINESS_PURCHASES
]

SAFEHOUSE_OWNERSHIP_ITEMS: list[str] = [
    item for item in PROPERTY_OWNERSHIP_ITEMS if item not in BUSINESS_OWNERSHIP_ITEMS
]

# The Rosenberg strand opens on a new game with no unlock item (sphere 0).
# Every other giver's first mission needs its first progressive unlock.
SPHERE_ZERO_GIVER = "Rosenberg"

# The default goal mission.
FINAL_MISSION = "Keep Your Friends Close..."

HIDDEN_PACKAGE_COUNT = len(package_data.PACKAGE_NAMES)

# The macguffin item of the hidden-packages goal. Collecting a physical package
# is a check like any other; the goal is a hunt on how many of these items you
# receive from the multiworld, one per physical package in the pool. It carries
# no in-game effect, so it maps to no SCM global. Named apart from the packages
# themselves and from the Hidden Packages content lock, since all three print
# side by side in hints, spoilers and trackers in a package-goal seed.
PACKAGE_FRAGMENT_ITEM = "Package Fragment"


def hidden_package_name(index: int) -> str:
    # Per physical package, in the SCM create_collectable1 placement order (index
    # i is the ith placed package). Names carry the district; the ASI detects each
    # one individually by coordinate.
    return package_data.PACKAGE_NAMES[index - 1]


# Rewards that leave the vanilla hidden-package threshold and enter the pool
# when the hidden-packages class is on. Useful items, never progression. Every
# non-cash reward is a respawning safehouse pickup or vehicle, so each name
# carries the Spawn suffix; nothing lands in the inventory on receipt.
PACKAGE_REWARD_ITEMS: list[str] = [
    "Body Armor Spawn", "Chainsaw Spawn", ".357 Spawn", "Flamethrower Spawn",
    ".308 Sniper Spawn", "Minigun Spawn", "Rocket Launcher Spawn",
    "Sea Sparrow Spawn", "Rhino Spawn", "Hunter Spawn", "$100,000",
]

# The four vanilla crossings from the start island to the mainland: three bridge
# roadblocks and the Starfish Island causeway gate, which the mainland flip
# removes together. With split_mainland_access on, each becomes its own item that
# opens only its own barrier, so crossing means travelling to a crossing the
# multiworld has opened; any one is enough, since the west island is roamable
# once the player is on it. Every roadblock stands on the start-island side, in
# the district that names it (the game's own navig.zon), so the item name says
# where to go: Prawn Island crosses to Downtown, Leaf Links to Downtown and
# Little Haiti, Ocean Beach to Viceport. The causeway needs the island as well,
# which is the one crossing behind two items.
MAINLAND_CROSSINGS: dict[str, list[str]] = {
    "Prawn Island Bridge": [],
    "Leaf Links Bridge": [],
    "Ocean Beach Bridge": [],
    "Starfish Island Causeway": ["Starfish Island Access"],
}
MAINLAND_CROSSING_ITEMS: list[str] = list(MAINLAND_CROSSINGS)

# Area items, in unlock-global order. Mainland Access and the crossings are
# alternatives, never both: the option picks which enters the pool, and the
# other's unlock global is simply never written. Both stay in the id table and
# the reserved layout, which are static across seeds.
AREA_ITEMS: list[str] = [
    "Mainland Access", "Starfish Island Access", *MAINLAND_CROSSING_ITEMS,
]

# The five emergency-vehicle completion rewards. When the shuffle option is on
# they enter the pool as useful items and the vanilla full-completion grant is
# suppressed; when off they grant vanilla and stay out of the pool.
EMERGENCY_REWARD_ITEMS: list[str] = [
    "Infinite Sprint", "Fireproof", "Max Armor Upgrade", "Taxi Jump Ability",
    "Max Health Upgrade",
]

# Which reward item each activity's full completion grants.
EMERGENCY_REWARD_BY_ACTIVITY: dict[str, str] = {
    "Paramedic": "Infinite Sprint",
    "Firefighter": "Fireproof",
    "Vigilante": "Max Armor Upgrade",
    "Taxi": "Taxi Jump Ability",
    "Pizza": "Max Health Upgrade",
}

# The nine radio stations, in the engine's station id order (0..8). When the
# randomize option is on each becomes a useful item: the player starts with one
# at random and the other eight enter the pool. The MP3 player and the police
# scanner are not stations here: the scanner is not music and the MP3 slot
# depends on the player's own files.
RADIO_STATION_ITEMS: list[str] = [
    "Radio Station: Wildstyle", "Radio Station: Flash FM",
    "Radio Station: K-Chat", "Radio Station: Fever 105",
    "Radio Station: V-Rock", "Radio Station: VCPR",
    "Radio Station: Radio Espantoso", "Radio Station: Emotion 98.3",
    "Radio Station: Wave 103",
]

# The minimap as an item. When the shuffle option is on the radar disc (map,
# blips, and north marker together) stays hidden until this item is received;
# when off the minimap is fully vanilla and the item stays out of the pool.
MINIMAP_ITEM = "Minimap"

# Ability locking. Each ability_locks key locks its ability at new game until
# its item arrives and puts that item in the pool; an unselected key is fully
# vanilla (no lock, no item, no logic terms). The vehicles key locks all
# vehicle entry and adds the three access items. The ASI enforces every lock
# per frame from the reserved lock-flag and unlock globals: the sprint lock
# masks the sprint input only (the jog is untouched), the weapon lock blocks
# scrolling to owned weapons and all in-vehicle fire while bare fists keep
# working, and the wallet lock pins the balance to zero, burning every kind of
# income while it holds, cash items included (deliberate, not a bug).
SPRINT_ITEM = "Sprint"
JUMP_ITEM = "Jump"
CROUCH_ITEM = "Crouch"
LAND_VEHICLES_ITEM = "Land Vehicles"
SEA_VEHICLES_ITEM = "Sea Vehicles"
AIR_VEHICLES_ITEM = "Air Vehicles"
WEAPON_EQUIP_ITEM = "Weapon Equip"
WALLET_ITEM = "Wallet"

ABILITY_LOCK_ITEMS: dict[str, list[str]] = {
    "sprint": [SPRINT_ITEM],
    "jump": [JUMP_ITEM],
    "crouch": [CROUCH_ITEM],
    "vehicles": [LAND_VEHICLES_ITEM, SEA_VEHICLES_ITEM, AIR_VEHICLES_ITEM],
    "weapon_equip": [WEAPON_EQUIP_ITEM],
    "wallet": [WALLET_ITEM],
}

# The eight ability items in a stable order; the reserved lock-flag and unlock
# globals follow this order, so it never reorders.
ABILITY_ITEMS: list[str] = [
    item for items in ABILITY_LOCK_ITEMS.values() for item in items
]

# Which ability_locks key owns each ability item.
ABILITY_ITEM_KEY: dict[str, str] = {
    item: key for key, items in ABILITY_LOCK_ITEMS.items() for item in items
}

# Crouch gates nothing (an accuracy comfort, never required); every other
# ability item may appear in a rule, so it is progression.
ABILITY_USEFUL_ITEMS: list[str] = [CROUCH_ITEM]

# Content locking. Each content_locks key holds a whole class inert at new game
# until its item arrives and puts that item in the pool; an unselected key is
# fully vanilla. A key holds its content even while the class's own toggle is
# off, so a seed can lock world content without making it checks; that is the
# one place a disabled class does not behave vanilla, and CLAUDE.md's toggle
# invariant names the exception. Enforcement splits by whether the content has
# an icon: holding the pickups belongs to the ASI (packages, rampage icons, and
# all 15 property icons), while the main.scm gates the two classes with nothing to
# hold, so a locked stunt jump registers nothing on landing and a locked store
# never starts its robbery.
HIDDEN_PACKAGES_ITEM = "Hidden Packages"
RAMPAGES_ITEM = "Rampages"
STUNT_JUMPS_ITEM = "Stunt Jumps"
PROPERTY_PURCHASES_ITEM = "Property Purchases"
ROBBABLE_STORES_ITEM = "Robbable Stores"

CONTENT_LOCK_ITEMS: dict[str, str] = {
    "hidden_packages": HIDDEN_PACKAGES_ITEM,
    "rampages": RAMPAGES_ITEM,
    "stunt_jumps": STUNT_JUMPS_ITEM,
    "properties": PROPERTY_PURCHASES_ITEM,
    "robbable_stores": ROBBABLE_STORES_ITEM,
}

# The five content items in a stable order; the reserved lock-flag and unlock
# globals follow this order, so it never reorders.
CONTENT_ITEMS: list[str] = list(CONTENT_LOCK_ITEMS.values())

# Which content_locks key owns each content item.
CONTENT_ITEM_KEY: dict[str, str] = {
    item: key for key, item in CONTENT_LOCK_ITEMS.items()
}

# How wide one content item's reach is, matching options.SplitContentLocks.
# OFF is one item per class, the whole city at once. PER_DISTRICT is one item
# per district covering every selected class there. PER_CLASS is one item per
# class per district, the finest.
CONTENT_SPLIT_OFF = 0
CONTENT_SPLIT_PER_DISTRICT = 1
CONTENT_SPLIT_PER_CLASS = 2


def district_content_item_name(district: str) -> str:
    # PER_DISTRICT: everything lockable in one district. "Content" rather than a
    # list of classes, since which classes it covers is the seed's choice.
    return f"{district} Content"


def district_class_item_name(district: str, content_item: str) -> str:
    # PER_CLASS: one class in one district. The class item's own name is the
    # plural, so this reads as the place followed by what it holds.
    return f"{district} {content_item}"


# Which class each district table belongs to. The tables are keyed by index, so
# index i is content i of that class in the world's own order.
CONTENT_DISTRICT_TABLES: dict[str, list[str]] = {
    HIDDEN_PACKAGES_ITEM: district_data.PACKAGE_DISTRICTS,
    RAMPAGES_ITEM: district_data.RAMPAGE_DISTRICTS,
    STUNT_JUMPS_ITEM: district_data.STUNT_JUMP_DISTRICTS,
    PROPERTY_PURCHASES_ITEM: [
        district_data.PROPERTY_DISTRICTS[purchase.removesuffix(" Purchase")]
        for purchase in PROPERTY_PURCHASES
    ],
    ROBBABLE_STORES_ITEM: district_data.STORE_DISTRICTS,
}

# Which districts hold each class, in DISTRICTS order. A class-district pair
# with nothing in it gets no item, which is why the PER_CLASS pool is 42 and not
# five times twelve. Eighteen pairs are empty: packages reach eleven of the
# twelve districts, rampages and stunt jumps nine each, properties eight and
# stores five. Leaf Links holds packages alone and the Junk Yard holds none of
# the five, only ambient pickups, which no content key covers.
CONTENT_CLASS_DISTRICTS: dict[str, list[str]] = {
    item: [district for district in district_data.DISTRICTS if district in set(table)]
    for item, table in CONTENT_DISTRICT_TABLES.items()
}

# Every district that holds anything lockable, in DISTRICTS order. Eleven of the
# twelve do, the Junk Yard being the exception, so PER_DISTRICT is eleven items,
# but this is derived rather than assumed.
CONTENT_DISTRICTS: list[str] = [
    district for district in district_data.DISTRICTS
    if any(district in districts for districts in CONTENT_CLASS_DISTRICTS.values())
]


def content_item_district(name: str) -> str | None:
    """The district a district-scoped content item holds, or None for a whole one.

    Both split forms lead with the district name, `Downtown Content` and
    `Downtown Hidden Packages`, and no district name is a prefix of another
    followed by a space, so the leading name identifies it. A whole-class item
    covers every district and belongs to no one of them.
    """
    for district in district_data.DISTRICTS:
        if name.startswith(f"{district} "):
            return district
    return None


def content_item_on_start_island(name: str) -> bool:
    """Whether a content item holds something reachable on a new game.

    A whole-class item always does, since it covers the start island among the
    rest. A district item does only if its district is on the start island: one
    holding Downtown is worth nothing until the mainland opens, which is not what
    a STARTING unlock is for.
    """
    district = content_item_district(name)
    return district is None or district_region(district) == REGION_VICE_CITY


def content_items(selected_keys: frozenset[str], split: int) -> list[str]:
    """The content items a seed puts in the pool, in a stable order.

    A key holds its class whether or not that class is a check class, so this
    reads the selected keys alone. Splitting changes only how many items carry
    the same holding, never which content is held.
    """
    locked = [item for item in CONTENT_ITEMS if CONTENT_ITEM_KEY[item] in selected_keys]
    if split == CONTENT_SPLIT_OFF or not locked:
        return locked
    if split == CONTENT_SPLIT_PER_DISTRICT:
        covered = {district for item in locked
                   for district in CONTENT_CLASS_DISTRICTS[item]}
        return [district_content_item_name(district)
                for district in district_data.DISTRICTS if district in covered]
    return [district_class_item_name(district, item)
            for item in locked for district in CONTENT_CLASS_DISTRICTS[item]]


def all_district_content_items() -> list[str]:
    """Every district content item any seed can produce, in id order.

    The item table is one table for all seeds, so it holds both granularities
    at once: the PER_DISTRICT items first, then the PER_CLASS items grouped by
    class. A seed uses one group or the other, never both.
    """
    names = [district_content_item_name(district) for district in CONTENT_DISTRICTS]
    names.extend(district_class_item_name(district, item)
                 for item in CONTENT_ITEMS
                 for district in CONTENT_CLASS_DISTRICTS[item])
    return names


def location_district(location_name: str) -> str | None:
    """The district a lockable location sits in, or None if it has no district.

    Only the five content classes have one. A business purchase is listed like
    any other purchase, though its rule is built from the sale requirements plus
    its own property term rather than from a lookup here.
    """
    return _LOCATION_DISTRICTS.get(location_name)

# Ability requirements per mission, from the manual runthrough of every mission.
# A term only takes effect while its ability_locks key is selected.
#
# Each entry says what that mission itself needs. rules.py propagates a strand's
# lock terms forward, so a mission also carries what every mission before it
# needs, which makes an entry that restates an inherited term harmless: Martha's
# Mug Shot inherits Dildo Dodo's helicopter whether or not it names one.
MISSION_ABILITY_REQUIREMENTS: dict[str, list[str]] = {
    "The Driver": [LAND_VEHICLES_ITEM],
    "Demolition Man": [LAND_VEHICLES_ITEM],
    "G-spotlight": [LAND_VEHICLES_ITEM],
    "Sunshine Autos Import List 1": [LAND_VEHICLES_ITEM],
    "Sunshine Autos Import List 2": [LAND_VEHICLES_ITEM],
    "Sunshine Autos Import List 3": [LAND_VEHICLES_ITEM],
    "Sunshine Autos Import List 4": [LAND_VEHICLES_ITEM],
    "The Fastest Boat": [SEA_VEHICLES_ITEM],
    "Supply & Demand": [SEA_VEHICLES_ITEM, WEAPON_EQUIP_ITEM],
    "Stunt Boat Challenge": [SEA_VEHICLES_ITEM],
    "Checkpoint Charlie": [SEA_VEHICLES_ITEM],
    "Dildo Dodo": [AIR_VEHICLES_ITEM],
    # From the runthrough. A weapon means the mission cannot be finished with
    # fists, a vehicle means it cannot be walked.
    "Alloy Wheels of Steel": [LAND_VEHICLES_ITEM],
    "Autocide": [WEAPON_EQUIP_ITEM],
    "Back Alley Brawl": [LAND_VEHICLES_ITEM],
    "Bar Brawl": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    "Bombs Away!": [LAND_VEHICLES_ITEM],
    "Boomshine Saigon": [LAND_VEHICLES_ITEM],
    "Cabmaggedon": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    "Cannon Fodder": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    "Cap the Collector": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    "Check Out at the Check In": [WEAPON_EQUIP_ITEM],
    "Cop Land": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    "Death Row": [WEAPON_EQUIP_ITEM],
    "Dirty Lickin's": [WEAPON_EQUIP_ITEM],
    "Distribution": [LAND_VEHICLES_ITEM],
    "Four Iron": [WEAPON_EQUIP_ITEM],
    "Friendly Rivalry": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    "Guardian Angels": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    "Hit the Courier": [WEAPON_EQUIP_ITEM],
    "Hog Tied": [LAND_VEHICLES_ITEM],
    "Jury Fury": [WEAPON_EQUIP_ITEM],
    "Keep Your Friends Close...": [WEAPON_EQUIP_ITEM],
    "Loose Ends": [WEAPON_EQUIP_ITEM],
    "Love Juice": [LAND_VEHICLES_ITEM],
    "Mall Shootout": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    "Martha's Mug Shot": [WEAPON_EQUIP_ITEM],
    "Messing with the Man": [WEAPON_EQUIP_ITEM],
    "Naval Engagement": [WEAPON_EQUIP_ITEM],
    "No Escape?": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    "Psycho Killer": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    "Publicity Tour": [LAND_VEHICLES_ITEM],
    "Recruitment Drive": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    # A foot chase, which the audit runs down with an infinite sprint or a car.
    # Infinite Sprint is the Paramedic reward and a useful item, which no access
    # rule may name, so the car is what is left.
    "The Chase": [LAND_VEHICLES_ITEM],
    "Rub Out": [WEAPON_EQUIP_ITEM],
    "Shakedown": [WEAPON_EQUIP_ITEM],
    "Spilling the Beans": [WEAPON_EQUIP_ITEM],
    "The Job": [WEAPON_EQUIP_ITEM],
    "The Shootist": [WEAPON_EQUIP_ITEM],
    "Trojan Voodoo": [LAND_VEHICLES_ITEM],
    "Two Bit Hit": [WEAPON_EQUIP_ITEM],
    "V.I.P.": [WEAPON_EQUIP_ITEM, LAND_VEHICLES_ITEM],
    "Waste the Wife": [LAND_VEHICLES_ITEM],
}

# Ability requirements per finale income asset, beyond the asset's own venue
# missions: the Sunshine Autos import lists take delivering vehicles.
ASSET_ABILITY_REQUIREMENTS: dict[str, list[str]] = {
    "Sunshine Autos": [LAND_VEHICLES_ITEM],
}

# The two rampages whose kill frenzy hands no weapon and expects the player to
# run the targets down, read from the RAMPAGE controller ($1518 carries no
# model for them): they need a land vehicle instead of the weapon equip. The
# ASI holds the other rampage icons by the same split, keyed on their pickup
# coordinates (-679.66, -419.712) and (468.656, -1608.79); a rampage with no
# weapon in its name is exactly a member of this set, which the tests pin.
VEHICLE_RAMPAGE_INDICES: frozenset[int] = frozenset({14, 21})

# Side events started by entering a helicopter: each checkpoint launcher
# requires the player to be flying a Sparrow (model 199).
AIR_SIDE_EVENTS: frozenset[str] = frozenset({
    "Downtown Chopper Checkpoint", "Ocean Beach Chopper Checkpoint",
    "Vice Point Chopper Checkpoint", "Little Haiti Chopper Checkpoint",
})

def cash_item_name(amount: int) -> str:
    # The amount alone: an item called "$100" says everything a player needs, and
    # the package bonus is named the same way. The two share one namespace, which
    # FILLER_ITEMS guards.
    return f"${amount:,}"


# Generic filler for checks with no vanilla cash reward (properties, robbable
# stores, emergency milestones) and for zero-reward missions: one-shot health and
# armor top-ups, a random weapon pickup, and a wanted-level clear like the
# LEAVEMEALONE cheat. All one-shot, all filler, none gate logic. The cash filler
# items are derived from the reward mirror at the end of this module.
GENERAL_FILLER: list[str] = [
    "Weapon Pickup", "Health Top-up", "Armor Top-up", "Remove Wanted Level",
]

# The bonus the game pays as the hundredth package lands, alongside the Hunter.
# Vanilla pays it from the executable's pickup code, not the script, so unlike
# the ten threshold rewards there is no vanilla trigger to re-gate: the ASI takes
# the payout back and this is a one-shot cash item like the filler denominations.
PACKAGE_CASH_REWARD = "$100,000"

# Persistent rewards re-gate a vanilla respawning grant (safehouse weapon pickup,
# car generator, or completion ability) onto an AP reward global instead of the
# vanilla trigger. The ten package weapon/vehicle rewards plus the five
# emergency abilities. Order is stable: it drives the reward-global indices.
PERSISTENT_REWARD_ITEMS: list[str] = (
    [item for item in PACKAGE_REWARD_ITEMS if item != PACKAGE_CASH_REWARD]
    + EMERGENCY_REWARD_ITEMS
)

# Traps take an equally weighted share of the filler slots, tuned by the
# trap_percentage option. Like consumables they are one-shot effects the ASI
# applies once past the applied-index, so a reconnect never re-fires one. Like
# all item application they wait for the player to be controllable (the one
# deferral condition the design allows). Hostile pedestrians, sped-up time,
# slowed time, and drunk vision last a fixed duration then revert. Most effect
# types mirror the cheat each imitates: wanted level like YOUWONTTAKEMEALIVE,
# hostile peds like NOBODYLIKESME, stormy weather like CATSANDDOGS, foggy
# weather like CANTSEEATHING, speed up like ONSPEED, and slow down like
# BOOOOOORING. Drunk vision has no cheat: it imitates the Boomshine Saigon
# drunk drive. Unlike the cheats, which pin the forced weather until a script
# changes it, a weather trap releases immediately after forcing, so the game's
# own hourly weather cycle resumes and blends the trap weather away naturally.
TRAP_DURATION_SECONDS = 30
TRAP_WANTED_STARS = 3

# Engine weather ids (eWeather) the weather traps carry as their param.
WEATHER_RAINY = 2
WEATHER_FOGGY = 3

TRAP_EFFECTS: dict[str, tuple] = {
    "Wanted Level Trap": ("trap_wanted", TRAP_WANTED_STARS),
    "Hostile Pedestrians Trap": ("trap_hostile_peds", TRAP_DURATION_SECONDS),
    "Stormy Weather Trap": ("trap_weather", WEATHER_RAINY),
    "Speed Up Trap": ("trap_speed_up", TRAP_DURATION_SECONDS),
    "Slow Motion Trap": ("trap_slow_down", TRAP_DURATION_SECONDS),
    "Foggy Weather Trap": ("trap_weather", WEATHER_FOGGY),
    "Drunk Vision Trap": ("trap_drunk", TRAP_DURATION_SECONDS),
}

# The trap item names, in a stable order.
TRAP_ITEMS: list[str] = list(TRAP_EFFECTS.keys())

# Other check classes beyond story missions and hidden packages. Counts come
# from the game design in PLAN and the decompiled mission table. These are
# free-roam collectibles and activities; their locations carry no access rule
# beyond the region they sit in.
RAMPAGE_COUNT = 35
STUNT_JUMP_COUNT = 36


# Rampage names, from the hand audit of every location: the district the icon
# stands in, then which weapon it hands and where to find it. Order is fixed:
# index i is rampage i, so location ids and completion globals do not move when
# a name does.
RAMPAGE_NAMES: list[str] = [
    "Rampage - Ocean Beach - Molotov",
    "Rampage - Escobar International - RPG",
    "Rampage - Vice Point - Uzi drive-by south",
    "Rampage - Vice Point - M4",
    "Rampage - Vice Point - Rocket Launcher",
    "Rampage - Washington Beach - MP",
    "Rampage - Downtown - Flamethrower",
    "Rampage - Downtown - Uzi drive-by",
    "Rampage - Downtown - Molotov",
    "Rampage - Downtown - M60",
    "Rampage - Little Haiti - Tec-9",
    "Rampage - Ocean Beach - Chainsaw",
    "Rampage - Ocean Beach - .308 Sniper Rifle",
    "Rampage - Starfish Island - Vehicle",
    "Rampage - Little Havana - Kruger",
    "Rampage - Viceport - Rocket Launcher",
    "Rampage - Escobar International - Minigun",
    "Rampage - Viceport - Grenade",
    "Rampage - Little Havana - Sniper Rifle",
    "Rampage - Ocean Beach - Katana",
    "Rampage - Ocean Beach - Vehicle",
    "Rampage - Vice Point - .357",
    "Rampage - Vice Point - Uzi drive-by north",
    "Rampage - Vice Point - Chainsaw",
    "Rampage - Viceport - RPG",
    "Rampage - Downtown - Minigun",
    "Rampage - Downtown - .357",
    "Rampage - Little Havana - Shotgun",
    "Rampage - Vice Point - .308 Sniper",
    "Rampage - Ocean Beach - Shotgun",
    "Rampage - Vice Point - S.P.A.S. 12",
    "Rampage - Little Havana - S.P.A.S. 12",
    "Rampage - Escobar International - S.P.A.S. 12",
    "Rampage - Ocean Beach - M4",
    "Rampage - Little Havana - Katana",
]


def rampage_name(index: int) -> str:
    return RAMPAGE_NAMES[index - 1]


# Unique stunt jump names, from the audit: the district, then the ramp itself.
# The engine's own jump ids order this, which is the order the per-jump flags
# $795..$830 and the district table follow, so index i is jump i everywhere.
STUNT_JUMP_NAMES: list[str] = [
    "Unique Stunt Jump - Escobar International - Western aircraft staircase over the airbridge east",
    "Unique Stunt Jump - Escobar International - Vice Surf board onto the terminal roof",
    "Unique Stunt Jump - Escobar International - Aircraft staircase east of the terminal",
    "Unique Stunt Jump - Escobar International - Steep metal ramp at the end of the angled runway",
    "Unique Stunt Jump - Escobar International - Western aircraft staircase over the airbridge west",
    "Unique Stunt Jump - Escobar International - Aircraft staircase south of red radar dish",
    "Unique Stunt Jump - Escobar International - Runway marker north of red radar dish",
    "Unique Stunt Jump - Escobar International - Eastern aircraft staircase over the airbridge",
    "Unique Stunt Jump - Prawn Island - To Film Studio",
    "Unique Stunt Jump - Vice Point - Avery's construction site",
    "Unique Stunt Jump - Downtown - Large staircase going over Ammu-Nation",
    "Unique Stunt Jump - Downtown - First G-spotlight jump",
    "Unique Stunt Jump - Downtown - Second G-spotlight jump",
    "Unique Stunt Jump - Downtown - Third G-spotlight jump",
    "Unique Stunt Jump - Little Haiti - Wooden ramp southwest of Auntie Poulet's",
    "Unique Stunt Jump - Little Haiti - Wooden ramp over a canal",
    "Unique Stunt Jump - Little Haiti - East of Kaufman Cabs",
    "Unique Stunt Jump - Little Havana - Roof of Calle Cafetaria",
    "Unique Stunt Jump - Ocean Beach - Alley rooftop",
    "Unique Stunt Jump - Ocean Beach - Parking Garage east of Hospital",
    "Unique Stunt Jump - Washington Beach - Over northern bridge",
    "Unique Stunt Jump - Ocean Beach - Cone Crazy parking lot rooftop",
    "Unique Stunt Jump - Ocean Beach - Stairs north of Pay 'n' Spray",
    "Unique Stunt Jump - Ocean Beach - Pink roof south of Gas station",
    "Unique Stunt Jump - Ocean Beach - Cortez's docks south",
    "Unique Stunt Jump - Ocean Beach - Cortez's docks north",
    "Unique Stunt Jump - Ocean Beach - Alley pallets south",
    "Unique Stunt Jump - Ocean Beach - Alley pallets north",
    "Unique Stunt Jump - Vice Point - Over the river near Club Malibu",
    "Unique Stunt Jump - Washington Beach - River jump east",
    "Unique Stunt Jump - Washington Beach - Alley stairs south",
    "Unique Stunt Jump - Washington Beach - Alley stairs northeast",
    "Unique Stunt Jump - Washington Beach - Alley stairs northwest",
    "Unique Stunt Jump - Washington Beach - Ramp north of alley",
    "Unique Stunt Jump - Washington Beach - River jump west",
    "Unique Stunt Jump - Starfish Island - Northeast house staircase",
]


def stunt_jump_name(index: int) -> str:
    return STUNT_JUMP_NAMES[index - 1]


# The canonical side-events list (14), pinned from the SCM mission table: three
# stadium events, four chopper checkpoints, three RC Top Fun events, and the
# four dirt and bike time trials.
SIDE_EVENTS: list[str] = [
    "Hotring", "Bloodring", "Dirtring",
    "Downtown Chopper Checkpoint", "Ocean Beach Chopper Checkpoint",
    "Vice Point Chopper Checkpoint", "Little Haiti Chopper Checkpoint",
    "RC Bandit Race", "RC Baron Race", "RC Raider Pickup",
    "Trial by Dirt", "Test Track", "PCJ Playground", "Cone Crazy",
]

# Emergency-vehicle milestone checks, one per level. Milestone means per level,
# never per fare or kill. Taxi and pizza count every tenth fare and level 1-10.
EMERGENCY_LEVELS: dict[str, int] = {
    "Paramedic": 12, "Vigilante": 12, "Firefighter": 12, "Taxi": 10, "Pizza": 10,
}


def emergency_name(activity: str, level: int) -> str:
    return f"{activity} Level {level:02d}"


def emergency_names() -> list[str]:
    return [
        emergency_name(activity, level)
        for activity, levels in EMERGENCY_LEVELS.items()
        for level in range(1, levels + 1)
    ]


# Robbable stores. The SCM has 15 add_stores_knocked_off sites, matching the
# 100 percent stat. A store is robbed by holding up its cashier, reachable
# once its area is, so these carry no access rule beyond their region.
ROBBABLE_STORE_COUNT = 15


# Store names, from the audit: the district, then the shop. Ordered by the
# add_stores_knocked_off site each one owns, which is what the completion globals
# and the district table follow.
ROBBABLE_STORE_NAMES: list[str] = [
    "Store Robbery - Washington Beach - Hardware store",
    "Store Robbery - North Point Mall - Tooled Up",
    "Store Robbery - Little Havana - Screw This",
    "Store Robbery - Little Havana - Calleggi Delicatessen Restaurant",
    "Store Robbery - Downtown - The Jewelers",
    "Store Robbery - Downtown - Dispensary",
    "Store Robbery - Little Haiti - Ryton Aide",
    "Store Robbery - Vice Point - The Jewelers",
    "Store Robbery - Vice Point - Dispensary",
    "Store Robbery - Vice Point - Corner store",
    "Store Robbery - North Point Mall - Vinyl Countdown",
    "Store Robbery - North Point Mall - Gash",
    "Store Robbery - North Point Mall - Family Jewels",
    "Store Robbery - Little Havana - Café Robina",
    "Store Robbery - Little Havana - Laundromat",
]


def robbable_store_name(index: int) -> str:
    return ROBBABLE_STORE_NAMES[index - 1]


# Optional check classes: class key -> (option attribute, ordered location
# names). Story missions are always on and are not listed here. The order fixes
# location ids, so append new classes at the end and never reorder.
def optional_check_classes() -> dict[str, tuple[str, list[str]]]:
    return {
        "hidden_packages": (
            "enable_hidden_packages",
            [hidden_package_name(index) for index in range(1, HIDDEN_PACKAGE_COUNT + 1)],
        ),
        "rampages": (
            "enable_rampages",
            [rampage_name(index) for index in range(1, RAMPAGE_COUNT + 1)],
        ),
        "stunt_jumps": (
            "enable_stunt_jumps",
            [stunt_jump_name(index) for index in range(1, STUNT_JUMP_COUNT + 1)],
        ),
        "emergency_vehicles": ("enable_emergency_vehicles", emergency_names()),
        "side_events": ("enable_side_events", list(SIDE_EVENTS)),
        "robbable_stores": (
            "enable_robbable_stores",
            [robbable_store_name(index) for index in range(1, ROBBABLE_STORE_COUNT + 1)],
        ),
        "properties": (
            "enable_properties",
            list(PROPERTY_PURCHASES)
            + [mission for missions in VENUE_STRANDS.values() for mission in missions]
            + [
                activity
                for activities in VENUE_ACTIVITIES.values()
                for activity in activities
            ],
        ),
        # LAST on purpose. Ids and completion globals are index-derived, so a
        # class inserted mid-registry shifts every class after it and every
        # reserved global above the completion block. Appending moves nothing
        # that already exists.
        "pickups": ("enable_pickups", list(PICKUP_NAMES)),
        # Appended after pickups, for that same reason.
        "shops": ("shuffle_shops", list(shop_data.SHOP_ITEM_NAMES)),
    }


def progressive_strands() -> dict[str, tuple[str, list[str]]]:
    """Every progressive mission strand: strand name -> (check class, missions).

    Story givers are always on; venue strands belong to the Properties class.
    """
    strands: dict[str, tuple[str, list[str]]] = {}
    for giver, missions in STORY_GIVERS.items():
        strands[giver] = ("story_missions", missions)
    for venue, missions in VENUE_STRANDS.items():
        strands[venue] = ("properties", missions)
    return strands


def progressive_item_name(strand: str) -> str:
    return f"Progressive {strand}"


def progressive_item_count(strand: str) -> int:
    # The sphere-0 giver's first mission is free, so it needs one fewer unlock.
    missions = len(STORY_GIVERS[strand] if strand in STORY_GIVERS else VENUE_STRANDS[strand])
    return missions - 1 if strand == SPHERE_ZERO_GIVER else missions


# Cross-giver prerequisites that gate a whole strand, from the hand audit of
# every mission. These are the audit's "After <mission>" clauses that no earlier
# mission of the same strand already covers, expressed as the progressive count
# that stands for having passed the mission named.
#
# The mod severs the vanilla marker reveals and launcher starts, so the game
# itself no longer enforces most of this and a player may well be able to start
# a strand early. Logic requires the chain regardless: it is what makes a seed
# beatable by the route the audit walked, and being stricter than the game costs
# only linearity.
#
# The audit opens every strand "After An Old Friend", and that clause costs
# nothing, so it is not here. An Old Friend is the sphere-zero mission: its rule
# is empty, it is reachable in every state, and passing it takes no item. The
# smallest progressive count that would stand for it, one Progressive Rosenberg,
# stands for reaching The Party instead, which is a mission further on than the
# audit asks for. So An Old Friend roots the play order and adds no term.
STRAND_PREREQUISITES: dict[str, list[tuple[str, int]]] = {
    # Death Row is Lance's rescue, which the audit puts after Cortez's fourth
    # and Diaz's fourth.
    "Death Row": [("Cortez", 4), ("Diaz", 4)],
    # The protection strand starts once Rub Out hands over the mansion, which is
    # Diaz's fifth and last.
    "Vercetti Protection": [("Diaz", 5)],
    "Vercetti Finale": [("Vercetti Protection", 3)],
}

# Where a strand's in-game gate waits on a vanilla mission having PASSED, and
# not just on the items that open it. One entry: the protection strand gives
# from the estate Rub Out takes off Diaz, and vanilla reveals its marker in that
# mission's own pass block, so on the unlock alone its beam and blip stand
# inside the mansion while Diaz still owns it. The mod reads the mission's
# vanilla passed flag, the way the finale gate reads Cop Land and Hit the
# Courier.
#
# Logic keeps the progressive stand-in above and is not tightened: a protection
# mission inherits Rub Out, so its rule already carries everything passing Rub
# Out takes, and a gate on the pass can never hold a mission the rules call
# reachable. Only the strands named here wait on a pass; every other strand
# opens on its own unlocks, which is the independent-strand-starts decision.
IN_GAME_PASSED_PREREQUISITES: dict[str, str] = {
    "Vercetti Protection": "Rub Out",
}

# Cross-giver edges that gate a single mission rather than a whole strand. Rub
# Out (Diaz's last) needs Lance rescued in Death Row first, and Publicity Tour
# needs the bikers on side from Hog Tied.
MISSION_PREREQUISITES: dict[str, list[tuple[str, int]]] = {
    "Rub Out": [("Death Row", 1)],
    "Publicity Tour": [("Big Mitch Baker", 3)],
    # The Cubans move on the Haitians only once Auntie Poulet's last is done.
    "Trojan Voodoo": [("Auntie Poulet", 3)],
}

# The same, for an edge into a venue strand: Cap the Collector needs the
# Printworks courier dealt with. Kept apart because a venue strand's progressive
# leaves the pool when the properties class is off, and no rule may name an item
# that is not in the pool, so rules.py carries these only while the class is on.
PROPERTY_MISSION_PREREQUISITES: dict[str, list[tuple[str, int]]] = {
    "Cap the Collector": [("Printworks", 2)],
}


# The finale's vanilla asset prerequisite, pinned from the decompile. The CELL
# controller starts Cap the Collector's launcher once Hit the Courier ($273)
# and Cop Land ($268) have passed and the owned-asset count $1175 exceeds six:
# seven of the nine income assets complete. Each asset completes differently:
# a venue strand's last mission, the first Sunshine Autos import garage list, the
# Pole Position back-room spend, or Cop Land for the Vercetti Estate. The
# custom FIN1 gate reads the same vanilla globals, and an asset's completion
# is recognized only while its property is bought and owned, so logic mirrors
# the prerequisite as the items to complete each asset.
# The vanilla already-shown flag for the bribe help text, which the pickup
# randomizer retires by stamping it. The vanilla HELP thread reads it in two
# places: the guard on its three bribe-text sites, and the all-tutorials-shown
# condition that ends the thread.
BRIBE_HELP_SHOWN_FLAG = 105

FINALE_HIT_THE_COURIER_FLAG = 273
FINALE_COP_LAND_FLAG = 268
FINALE_ASSET_COUNT_GLOBAL = 1175
FINALE_ASSET_THRESHOLD = 7

# The assets logic may pick from for the threshold: venue or business name ->
# the progressive unlocks its completion needs (0 = free-roam money once the
# property is bought and owned). Printworks is absent because Hit the Courier
# is individually mandatory, and the Vercetti Estate because Cop Land arrives
# through the protection progressives the finale already requires; both count
# toward the threshold, leaving this many to pick from the seven below.
FINALE_OPTIONAL_ASSETS: dict[str, int] = {
    "Malibu Club": 4, "Film Studio": 4, "Kaufman Cabs": 3, "Cherry Popper": 1,
    "Boatyard": 1, "Sunshine Autos": 1, "Pole Position": 0,
}
FINALE_OPTIONAL_ASSETS_REQUIRED = FINALE_ASSET_THRESHOLD - 2


# Region model, pinned from the SCM. The vanilla map has two persistent
# barriers. The mainland barrier: three bridge roadblocks that all delete
# together, and the flag $847 that all set, when Phnom Penh '86 (Diaz's second
# mission) passes, opening the whole west island; the AP item Mainland Access
# stands in for that flip. The Starfish Island barrier: two gates, the east
# gate ($1780) that the phone-chain thread opens after Guardian Angels and the
# west gate ($1779) that the mainland flip opens; the AP item Starfish Island
# Access stands in for the island, opening the east gate alone and the west
# gate together with Mainland Access, so neither area item ever implies the
# other. Leaf Links is not a roamable gated area (its gate opens inside Four
# Iron), so the start island is the east beaches plus Prawn and Leaf Links;
# the mainland is everything west of the bridge channel; Starfish Island is
# its own region between them. Island membership below is read from each
# check's world coordinates in the decompile (giver marker positions, rampage
# pickup positions, and payphone positions), with the Starfish members
# verified against the island's map instances (starisl.ipl and mansion.ipl).
REGION_VICE_CITY = "Vice City"
REGION_MAINLAND = "Mainland"
REGION_STARFISH = "Starfish Island"

# The area item that opens each gated region when the crossings are not split,
# for requirements that must name the item itself (the region carries it for the
# locations inside it). Anything deciding what a region DEMANDS reads
# region_access_groups instead, so the split reaches it; this table is for the
# three callers that want the unsplit item by name: the pool when the option is
# off, the generated spec, and the tracker's soft-requirement match.
AREA_ITEM_BY_REGION: dict[str, str] = {
    REGION_MAINLAND: "Mainland Access",
    REGION_STARFISH: "Starfish Island Access",
}

# Story givers whose whole strand sits on the mainland (marker west of the
# channel). Mr. Black is absent because his payphones span both islands (his
# mainland ones are in MAINLAND_MISSIONS). The finale giver marker is at the
# mansion, so its missions are split per mission below: Cap the Collector
# starts at the Print Works on the mainland, Keep Your Friends Close... at the
# mansion on Starfish.
MAINLAND_GIVERS: frozenset[str] = frozenset({
    "Big Mitch Baker", "Umberto Robina", "Auntie Poulet",
    "Phil Cassidy", "Love Fist",
})

# Story givers whose whole strand gives from the Vercetti (Diaz) mansion on
# Starfish Island: Diaz's markers sit at the mansion and near the island's
# east entrance, Vercetti Protection's all sit on the estate.
STARFISH_GIVERS: frozenset[str] = frozenset({
    "Diaz", "Vercetti Protection",
})

# Venue strands whose business sits on the mainland.
MAINLAND_VENUES: frozenset[str] = frozenset({
    "Kaufman Cabs", "Printworks", "Cherry Popper", "Boatyard", "Sunshine Autos",
})

# Individual mainland missions whose giver is not a whole-mainland giver. Mr.
# Black's last two payphones (Check Out at the Check In at X = -1482, Loose Ends
# at X = -978) are on the mainland; his first three are on the start island.
# Cap the Collector, the finale's first mission, starts at the Print Works.
MAINLAND_MISSIONS: frozenset[str] = frozenset({
    "Check Out at the Check In", "Loose Ends", "Cap the Collector",
})

# Individual Starfish Island missions whose giver is not a whole-island giver.
# The finale's last mission starts at the mansion.
STARFISH_MISSIONS: frozenset[str] = frozenset({
    "Keep Your Friends Close...",
})

# Which island each district is on, which is what turns the audited district of
# a package, a rampage, a stunt jump or a store into the region that gates it.
# Every crossing's roadblock stands on the start-island side, so Prawn Island and
# Leaf Links belong to the start island even though they are separate land;
# Starfish Island is its own gated area.
MAINLAND_DISTRICTS: frozenset[str] = frozenset({
    "Downtown", "Little Haiti", "Junk Yard", "Little Havana", "Viceport",
    "Escobar International",
})
STARFISH_DISTRICTS: frozenset[str] = frozenset({"Starfish Island"})
START_ISLAND_DISTRICTS: frozenset[str] = frozenset({
    "Ocean Beach", "Washington Beach", "Vice Point", "Prawn Island",
    "Leaf Links",
})

# The three name every district and none twice, so a district misspelt in
# district_data raises below instead of quietly reading as the start island,
# which would let the fill strand a crossing item behind a mainland check.
_ISLAND_DISTRICTS = (MAINLAND_DISTRICTS, STARFISH_DISTRICTS,
                     START_ISLAND_DISTRICTS)
assert frozenset.union(*_ISLAND_DISTRICTS) == frozenset(district_data.DISTRICTS), (
    "on no island, or on no part of the map: "
    f"{sorted(frozenset(district_data.DISTRICTS) ^ frozenset.union(*_ISLAND_DISTRICTS))}"
)
assert sum(len(island) for island in _ISLAND_DISTRICTS) == len(
    district_data.DISTRICTS), "a district is on two islands at once"


def district_region(district: str) -> str:
    if district in MAINLAND_DISTRICTS:
        return REGION_MAINLAND
    if district in STARFISH_DISTRICTS:
        return REGION_STARFISH
    if district in START_ISLAND_DISTRICTS:
        return REGION_VICE_CITY
    raise ValueError(f"{district} is not one of the map's districts")


def _districted_region_members(districts: list[str], names: list[str],
                               region: str) -> frozenset[str]:
    return frozenset(name for district, name in zip(districts, names, strict=True)
                     if district_region(district) == region)


# Regions a mission needs beyond its own. Keep Your Friends Close... sits on
# Starfish, but its launcher only activates once Cap the Collector passes, and
# that mission is on the mainland, so the finale also needs the mainland. Named
# by region rather than by item, so the crossing split reaches it too.
# Missions the mainland is not enough for: they need one particular crossing
# open, whichever way the seed hands the mainland over. Death Row is the one,
# from the runthrough: the drive it puts the player on only works across the
# Leaf Links bridge, so a seed opening any other crossing first leaves the
# mission uncompletable even though the mainland is reachable.
#
# With the crossings whole this says nothing, since the single Mainland Access
# item removes all four roadblocks at once.
MISSION_CROSSING_REQUIREMENTS: dict[str, str] = {
    "Death Row": "Leaf Links Bridge",
}

MISSION_REGION_REQUIREMENTS: dict[str, list[str]] = {
    # The nine below are played on the mainland while their own region is the
    # start island or Starfish. Four of them carry Starfish Island Access
    # already, through the property sale requirements, which is a different
    # island and opens no bridge. The Fastest Boat is Diaz's, so its own region
    # is the mansion's island, but the boat it steals is in the Viceport
    # boatyard.
    "Sir, Yes Sir!": [REGION_MAINLAND],
    "The Fastest Boat": [REGION_MAINLAND],
    "Death Row": [REGION_MAINLAND],
    "Two Bit Hit": [REGION_MAINLAND],
    "The Shootist": [REGION_MAINLAND],
    "The Job": [REGION_MAINLAND],
    "Recruitment Drive": [REGION_MAINLAND],
    "G-spotlight": [REGION_MAINLAND],
    "Keep Your Friends Close...": [REGION_MAINLAND],
}


# Missions whose passing something else needs: a way onto an island, a vehicle
# that spawns afterwards, a place the mission opens up, or a weapon a shop only
# racks once it passes. Passing a mission is not an item a seed can place, so
# each of these gets an event location carrying what reaching the mission takes,
# and the tables below name the event.
#
# G-spotlight and The Job are venue missions, so with the properties class off
# their progressives are not in the pool. Their events still stand: what one
# costs then is everything the mission takes except the property and its
# unlocks, which is the player's call on how the class-off case should read.
# The Job is here for the knife it leaves on the pavement outside the Malibu
# Club, which is a pickup that does not exist until it passes, and an event is
# the only way a pickup can wait on a mission whose own class may be off.
# Boomshine Saigon is here for the four stands it racks at Phil's Place, which
# are shop checks the same way: the stands are not in the world before it.
ROUTE_MISSIONS: list[str] = [
    "All Hands On Deck!", "Phnom Penh '86", "Rub Out", "G-spotlight",
    "Jury Fury", "Riot", "Treacherous Swine", "Mall Shootout",
    "Guardian Angels", "Four Iron", "The Chase", "Trojan Voodoo",
    "Loose Ends", "Shakedown", "Bar Brawl", "The Job",
    "Boomshine Saigon",
]

# Where the audit names a mission a check waits on, read off the sheet row by
# row. The two vehicle cases are the ones to know: a helicopter is on the start
# island only once Rub Out has spawned the Vice Point Sparrow, and the Downtown
# checkpoint takes the one G-spotlight leaves behind. Where a row names a bare
# vehicle and no mission, there is none here, because the mission the check
# belongs to hands the vehicle over.
CHOPPER_MISSION_REQUIREMENTS: dict[str, list[str]] = {
    "Ocean Beach Chopper Checkpoint": ["Rub Out"],
    "Vice Point Chopper Checkpoint": ["Rub Out"],
    "Little Haiti Chopper Checkpoint": ["Rub Out"],
    "Downtown Chopper Checkpoint": ["G-spotlight"],
}


def stunt_jump_mission_requirements() -> dict[str, list[str]]:
    """Stunt jumps a mission opens the way to, by jump name.

    The three G-spotlight jumps are the ramps that mission builds, and the two on
    Cortez's docks are behind the boat leaving.
    """
    return {
        **{stunt_jump_name(index): ["G-spotlight"] for index in (12, 13, 14)},
        **{stunt_jump_name(index): ["All Hands On Deck!"] for index in (25, 26)},
    }


def mission_passed_item_name(mission: str) -> str:
    return f"{mission} Passed"


def mission_event_name(mission: str) -> str:
    return f"{mission} (event)"


# Ways onto Starfish Island besides its barrier, from the audit. A roadblock
# stops a car and nothing else, so the island's gates are not the only way in:
#
#   fly a helicopter over, which the audit gets from the mainland
#   sail a boat, which the audit gets from Cortez's last mission
#
# The mainland has no route and gets none. The audit's mainland rows carry a
# plain Mainland Access and no alternative to it, and the mod enforces that
# barrier where it matters: the last mission's launcher gate reads a mainland
# unlock global, so a seed logic called beatable without one could not be played.
#
# Two of the audit's helicopters are left out. The Vice Point Sparrow that
# passing Rub Out spawns cannot open this island, since Rub Out needs the island
# already. The Sea Sparrow at the mansion arrives as the eighty-package reward,
# which is a useful item, and no access rule may name one. The audit's boat out
# of Phnom Penh '86 is left out for the first reason too: that mission is played
# here.
#
# Each route's vehicle term binds only while the vehicles key is selected. With
# the key off the vehicle is free and the route reduces to the way to the
# mainland or the mission behind it, which is the truth about the game: nothing
# in the mod stops a boat.
def region_route_groups(region: str,
                        split_mainland_access: bool) -> list[list[str]]:
    if region != REGION_STARFISH:
        return []
    crossings = region_access_groups(REGION_MAINLAND, split_mainland_access,
                                     routes_allowed=False)
    return [
        *([AIR_VEHICLES_ITEM, *crossing] for crossing in crossings),
        [SEA_VEHICLES_ITEM, mission_passed_item_name("All Hands On Deck!")],
    ]


def region_access_groups(region: str, split_mainland_access: bool,
                         routes_allowed: bool = True) -> list[list[str]]:
    """The alternative item sets that reach a region, any one of them enough.

    An island's barrier item is the first group. With the crossings split, the
    mainland has one group per crossing instead of the single Mainland Access
    group. The audit's other ways in follow, unless routes_allowed says to leave
    them out, which is how the Starfish air route asks for the mainland's own
    barriers without recursing. A region needing nothing (the start island) has
    no groups at all.
    """
    if region == REGION_MAINLAND and split_mainland_access:
        groups = [[crossing, *also] for crossing, also in MAINLAND_CROSSINGS.items()]
    else:
        area_item = AREA_ITEM_BY_REGION.get(region)
        groups = [] if area_item is None else [[area_item]]
    if groups and routes_allowed:
        # A route naming the barrier it is an alternative to reaches nothing new,
        # which the Starfish air route does for the causeway crossing.
        barrier = AREA_ITEM_BY_REGION.get(region)
        groups += [route for route in region_route_groups(region, split_mainland_access)
                   if barrier not in route]
    return groups


def active_route_groups(groups: list[list[str]],
                        active_items: frozenset[str]) -> list[list[str]]:
    """The same groups with every unselected lock item dropped.

    A route names a vehicle, and that term binds only while the vehicles key is
    selected; with the key off the vehicle is free and the route reduces to the
    mission that hands it over. Dropping the term rather than the route is what
    keeps a rule from naming an item no seed has.
    """
    active = [[item for item in group
               if item not in ABILITY_ITEMS or item in active_items]
              for group in groups]
    # An empty group reads as satisfied, so it would make the region free. Every
    # route carries an event item or a barrier and cannot empty, and this says so
    # rather than leaving the hole silent.
    assert all(active), f"a route emptied to nothing: {groups}"
    return active


def mission_region(giver: str, mission: str) -> str:
    if mission in MAINLAND_MISSIONS:
        return REGION_MAINLAND
    if mission in STARFISH_MISSIONS:
        return REGION_STARFISH
    if giver in STARFISH_GIVERS:
        return REGION_STARFISH
    if giver in MAINLAND_GIVERS or giver in MAINLAND_VENUES:
        return REGION_MAINLAND
    return REGION_VICE_CITY


# Rampages by island, from the audited district of each. The kill-frenzy pickup
# coordinates in the RAMPAGE controller are what the districts were audited
# against, and pickup order equals flag order equals check order there.
MAINLAND_RAMPAGES: frozenset[str] = _districted_region_members(
    district_data.RAMPAGE_DISTRICTS, RAMPAGE_NAMES, REGION_MAINLAND)

# Rampage 14 is the one on Starfish Island, its pickup at (-679.7, -419.7) on the
# island's west tip, verified against the starisl.ipl map instances.
STARFISH_RAMPAGES: frozenset[str] = _districted_region_members(
    district_data.RAMPAGE_DISTRICTS, RAMPAGE_NAMES, REGION_STARFISH)

# Hidden packages are per package, each detected individually by the ASI (by
# coordinate) rather than by a running count. Coordinates come from package_data
# in the SCM placement order, and PACKAGE_COORDS is sent to the ASI via slot_data
# so it can match a collected pickup to its package. Island membership follows
# the audited district, like every other class.
MAINLAND_PACKAGES: frozenset[str] = _districted_region_members(
    district_data.PACKAGE_DISTRICTS, package_data.PACKAGE_NAMES, REGION_MAINLAND)
STARFISH_PACKAGES: frozenset[str] = _districted_region_members(
    district_data.PACKAGE_DISTRICTS, package_data.PACKAGE_NAMES,
    REGION_STARFISH)
PACKAGE_COORDS: list[tuple[float, float, float]] = package_data.PACKAGE_COORDS

# Ambient pickup slots for the randomize_pickups permutation, extracted from
# the decompile by scripts/dump_pickups.py: the MAIN-section bribes, the Mission
# 0 street weapons, hearts, armors, and adrenalines, and the six a MISSION
# creates and never removes, which stand in the world for the rest of the game
# once their mission passes and so behave like any other ambient slot. Each slot
# keeps its position and pickup type; the permutation moves the model and ammo.
#
# The six are last in the table, appended rather than placed where the decompile
# puts them, which is what keeps every existing location id and completion global
# where it was. What they cost instead is a mission term each, in
# PICKUP_MISSION_REQUIREMENTS below.
#
# Bribes never land on shop-type slots. Not because the price breaks: an in-shop
# pickup prices from a field that means a weapon type only for a weapon model, and
# the bribe is a simple model whose field is zero, so the cost table's zeroth
# entry prices it, which is nothing. A free police bribe that respawns is the
# problem: each one takes a star off the wanted level, so an endless supply of
# them at a fixed spot is an endless supply of stars.
PICKUP_SLOTS: list[tuple[float, float, float, int, int, int]] = pickup_data.PICKUP_SLOTS
PICKUP_MODEL_NAMES: dict[int, str] = pickup_data.PICKUP_MODEL_NAMES
PICKUP_BRIBE_MODEL: int = pickup_data.BRIBE_MODEL
PICKUP_SHOP_TYPE: int = pickup_data.SHOP_PICKUP_TYPE
PICKUP_HANDLE_GLOBALS: list[int] = pickup_data.PICKUP_HANDLE_GLOBALS

# The four in-shop stands Boomshine Saigon racks at Phil's Place. They are
# pickups, so the pickup layout is what puts the AP marker on them and what puts
# their model back once the check is taken; they are the SHOP class's, so the
# location, the item and the toggle are all the shop table's. Keyed by handle
# global here because that is the one field both tables carry.
SHOP_STAND_SLOTS: list[tuple[float, float, float, int, int, int, int]] = (
    pickup_data.SHOP_STAND_SLOTS)
SHOP_STAND_ITEMS: dict[int, shop_data.ShopItem] = {
    item.script_global: item for item in shop_data.SHOP_ITEMS
    if item.thread in shop_data.SHOP_PICKUP_THREADS
}
assert sorted(SHOP_STAND_ITEMS) == sorted(stand[6] for stand in SHOP_STAND_SLOTS), (
    f"{sorted(SHOP_STAND_ITEMS)} shop stands in shop_data and "
    f"{sorted(stand[6] for stand in SHOP_STAND_SLOTS)} in the decompile"
)

# How far apart the ASI may look for the pool entry standing at a slot, and the
# two measurements that bound it, all in game units. Mirrored in
# scm_pickup_layout.hpp, which is what actually does the matching; the mirror
# checker compares the two.
#
# Below the nearest same-type pickup no table of ours owns, or the matcher could
# pair a slot with that pickup instead: the body armour Rub Out leaves in the
# estate courtyard has the finale's Tec-9 less than a unit away, both street
# type. Above nothing in particular, since the positions round-trip through JSON
# as decimals and back to the same float the script literal compiled to, so what
# the tolerance actually absorbs is a fraction of a unit at most.
PICKUP_MATCH_TOLERANCE: float = 0.25
PICKUP_CLOSEST_SLOT_PAIR: float = pickup_data.CLOSEST_SLOT_PAIR
PICKUP_NEAREST_FOREIGN: float = pickup_data.NEAREST_FOREIGN_PICKUP
assert PICKUP_MATCH_TOLERANCE < PICKUP_NEAREST_FOREIGN, (
    f"a match tolerance of {PICKUP_MATCH_TOLERANCE} reaches the foreign pickup "
    f"{PICKUP_NEAREST_FOREIGN} units from a slot, so a slot could be matched to "
    f"a pickup that is not it"
)
assert PICKUP_MATCH_TOLERANCE < PICKUP_CLOSEST_SLOT_PAIR, (
    f"a match tolerance of {PICKUP_MATCH_TOLERANCE} reaches from one slot to "
    f"the next, {PICKUP_CLOSEST_SLOT_PAIR} units away"
)

# Every ambient slot is also a check, the first time it is taken, while
# enable_pickups is on. Afterwards the slot behaves as randomize_pickups says:
# shuffled when that option is on, vanilla when it is off. The two options
# compose and neither overrides the other.

# Whether any mod code reports an ambient pickup as taken. True since the
# appickup CLEO watcher shipped: it polls every slot handle and latches each
# slot's completion global, which the ASI already reads like any other check.
MOD_REPORTS_PICKUPS: bool = True

# The reach terms are audited now too, and they are in
# PICKUP_ABILITY_REQUIREMENTS, PICKUP_ABILITY_ALTERNATIVES and
# PICKUP_MISSION_REQUIREMENTS below: 26 of the slots carry one and the rest are
# walked to. Twenty of those were the original audit, twenty and not twenty-one
# because the Viceport bridge rail is in the first two tables at once; the six
# the missions create carry theirs because the pickup is not in the world before
# the mission. Data in the requirement tables rather than a flag anything reads,
# which is why there is no flag here for it.


# One check per slot, so the count is the slot table's and not a number written
# down twice.
PICKUP_COUNT: int = len(pickup_data.PICKUP_SLOTS)

# The district table must cover the slot table exactly. The zip in the region
# derivation is strict, so either table being longer raises there on its own,
# and this assert adds no safety that lacks. It is kept for its message: the zip
# names an argument number and which way it is wrong, while this names the two
# counts, which is what tells a re-audit what it left the wrong length.
assert len(district_data.PICKUP_DISTRICTS) == PICKUP_COUNT, (
    f"{len(district_data.PICKUP_DISTRICTS)} pickup districts for "
    f"{PICKUP_COUNT} slots"
)
# The name table the same way. Both are keyed by slot index and neither derives
# from the other, so a table the wrong length renames every slot past the gap,
# and a name table that is LONGER goes unnoticed otherwise: the region loop walks
# range(PICKUP_COUNT) and drops the extras without a word.
assert len(pickup_data.PICKUP_NAMES) == PICKUP_COUNT, (
    f"{len(pickup_data.PICKUP_NAMES)} pickup names for {PICKUP_COUNT} slots"
)

# The ten in-shop stands charge for what they give, so their checks need the
# Wallet item while that key is selected. The other hundred need nothing at all:
# walking over a pickup takes no ability.
# Keyed on the slot's TYPE and never on its model. The type is what decides
# whether a slot charges at all; the model only decides how much. So keying on
# type keeps the term right under randomize_pickups, which moves models between
# slots and would otherwise move the Wallet term with them.
PICKUP_PAY_STAND_INDICES: frozenset[int] = frozenset(
    index
    for index, (_x, _y, _z, pickup_type, _model, _ammo)
    in enumerate(pickup_data.PICKUP_SLOTS)
    if pickup_type == PICKUP_SHOP_TYPE
)


# The vanilla global each slot's creation stores its pickup handle in, in slot
# order. The generated APPICK watcher reads every one of them, polling
# has_pickup_been_collected on each handle, since a handle is the game's own name
# for a slot and there is nothing else to detect a taken pickup by.
#
# A handle alone is NOT a stable identity, and no assert here can see why: the
# reuse is in the game's script rather than in this table. Mission 52 creates a
# new pickup into slot 62's handle without removing slot 62's own first, so for
# part of that mission the handle names a pickup at the mansion instead, and
# slot 62's original is left in the world named by nothing. Every other
# re-creation puts the pickup back at its own slot's coordinates: mission 32 on
# this same slot, mission 52 again once it has removed the one it moved, and
# mission 21 on slot 24, which is the only other slot touched at all. So
# whatever reads a handle has to check the pickup it resolves to still stands
# where the slot does.
#
# What the asserts below DO cover: one handle per slot and never shared, plus a
# third in scm.py, which owns the reserved base and can compare against it
# without importing back into here.
assert len(pickup_data.PICKUP_HANDLE_GLOBALS) == PICKUP_COUNT, (
    f"{len(pickup_data.PICKUP_HANDLE_GLOBALS)} handles for {PICKUP_COUNT} slots"
)
assert len(set(pickup_data.PICKUP_HANDLE_GLOBALS)) == PICKUP_COUNT, (
    "two slots share a pickup handle global"
)


def pickup_handle_global(index: int) -> int:
    return pickup_data.PICKUP_HANDLE_GLOBALS[index]


# One name per slot, from the hand audit, the way the package names read: the
# district the slot is in and then where in it to look, so a name alone takes a
# player to the pickup.
#
# The district the name says is the district table's own, and a test compares
# them slot by slot, since the two came from one audit and are stored apart.
PICKUP_NAMES: list[str] = list(pickup_data.PICKUP_NAMES)


def pickup_name(index: int) -> str:
    return PICKUP_NAMES[index]


def pickup_region(index: int) -> str:
    return district_region(district_data.PICKUP_DISTRICTS[index])


def shop_item_region(item: shop_data.ShopItem) -> str:
    # A shop's island comes from the district it stands in, the same way a
    # pickup's does. Two of the six are on the mainland, the Downtown
    # Ammu-Nation and the Little Havana tool store, so those wait on the
    # crossing; the other four are on the starting island.
    #
    # Except that reaching a shop and it having the thing in stock are two
    # questions. The Vice Point sniper stocks off the flag the crossing sets, so
    # it gates on Mainland Access despite standing on the starting island, for
    # the same reason the mainland property purchases below do: left on the
    # starting island the fill can hide Mainland Access itself behind a check
    # that only stocks once the mainland is open, which is unwinnable.
    if (item.thread, item.script_global) in shop_data.CROSSING_STOCKED_ITEMS:
        return REGION_MAINLAND
    return district_region(shop_data.SHOP_DISTRICTS[item.thread])


# Property purchases on the mainland: the five mainland venue businesses and the
# two mainland safehouses (Hyman Condo in Downtown, Skumole Shack in Little
# Haiti). A purchase needs its island reached, so a mainland purchase must gate on
# Mainland Access; leaving it start-island lets the fill hide Mainland Access
# itself behind a mainland business, an unwinnable loop.
MAINLAND_PROPERTIES: frozenset[str] = frozenset({
    "Printworks Purchase", "Sunshine Autos Purchase", "Cherry Popper Purchase",
    "Kaufman Cabs Purchase", "Boatyard Purchase",
    "Hyman Condo Purchase", "Skumole Shack Purchase",
})

# Robbable stores on the mainland, from the audited district of each. Source
# order equals check order, which is how a store's district reaches its site.
MAINLAND_STORES: frozenset[str] = _districted_region_members(
    district_data.STORE_DISTRICTS, ROBBABLE_STORE_NAMES, REGION_MAINLAND)

# Side events on the mainland. The three stadium events (Hyman Stadium, Downtown)
# and the Downtown and Little Haiti chopper checkpoints are confirmed mainland. RC
# Raider, Trial by Dirt, and Test Track are not coordinate-pinned, so they count
# as mainland provisionally; the in-game audit refines them and must also confirm
# none sits on Starfish Island, since mainland gating no longer covers the island
# (with Mainland Access alone both island gates stay shut). RC Bandit, RC Baron,
# PCJ Playground, Cone Crazy, and the Ocean Beach and Vice Point chopper
# checkpoints are on the start island.
MAINLAND_SIDE_EVENTS: frozenset[str] = frozenset({
    "Hotring", "Bloodring", "Dirtring",
    "Downtown Chopper Checkpoint", "Little Haiti Chopper Checkpoint",
    "RC Raider Pickup", "Trial by Dirt", "Test Track",
})

# Stunt jump islands, from the audited district of each jump: 19 of the 36 sit on
# the start island, 16 on the mainland, and jump 36 is the one on Starfish Island,
# which needs its own item, since Mainland Access alone leaves both island gates
# shut. This is the one island set with no in-repo cross-check, there being no
# per-jump coordinates to derive from and the names coming from the same audit,
# so it waits on the in-game gate.
STARFISH_STUNT_JUMPS: frozenset[str] = _districted_region_members(
    district_data.STUNT_JUMP_DISTRICTS, STUNT_JUMP_NAMES, REGION_STARFISH)

MAINLAND_STUNT_JUMPS: frozenset[str] = _districted_region_members(
    district_data.STUNT_JUMP_DISTRICTS, STUNT_JUMP_NAMES, REGION_MAINLAND)


# Ability terms the runthrough found beyond a class's own rule, keyed by index
# rather than by name so the tables survive a rename.
#
# Vigilante is the emergency activity that needs a weapon: the others are driving
# or carrying, and shooting the criminal is the whole of this one.
EMERGENCY_ABILITY_EXTRAS: dict[str, list[str]] = {
    "Vigilante": [WEAPON_EQUIP_ITEM],
}

# Five rampages need more than their class rule gives them. Three are drive-bys,
# needing the car as well as the weapon; rampage 19 is reachable only from the
# air; and rampage 14, one of the run-them-down pair, takes a jump to its icon.
RAMPAGE_ABILITY_EXTRAS: dict[int, list[str]] = {
    3: [LAND_VEHICLES_ITEM],
    8: [LAND_VEHICLES_ITEM],
    14: [JUMP_ITEM],
    19: [AIR_VEHICLES_ITEM],
    23: [LAND_VEHICLES_ITEM],
}

# Packages a player cannot simply walk to. Four need a jump and one an aircraft
# outright; the other four the audit used to put here are one-of rows instead,
# and they are in PACKAGE_ABILITY_ALTERNATIVES: 21 and 40 because a helicopter
# has to come from somewhere and a route is what says where, and 54 because the
# wall around the Starfish northeast pool can be flown over as well as jumped.
PACKAGE_ABILITY_REQUIREMENTS: dict[int, list[str]] = {
    18: [JUMP_ITEM],
    57: [JUMP_ITEM],
    74: [JUMP_ITEM],
    81: [AIR_VEHICLES_ITEM],
    92: [JUMP_ITEM],
}


# Where the audit gives a location several routes and any one is enough. Each
# entry is a list of alternatives, and each alternative the items that route takes
# together, so [[A], [B, C]] reads "A, or B and C". These sit beside the tables
# above rather than in them, since those mean AND.
#
# A route whose items are none of them locked is always open, which makes the
# whole requirement free, and rules.py drops it rather than emitting a one-of
# nobody can fail.
#
# A route this cannot express is left out, and leaving one out only narrows, so
# it is the safe direction. Two are left out. The audit opens package 42 from
# inside the Film Studio as well, once the studio is bought and owned. And it
# opens The Chase on foot with an infinite sprint, which is not a thing the game
# or the mod has, so The Chase keeps the car alone, in
# MISSION_ABILITY_REQUIREMENTS rather than here: an or with one route left is a
# requirement. Whether the plain sprint is enough is an in-game question, and if
# it is, The Chase gains a route.
MISSION_ABILITY_ALTERNATIVES: dict[str, list[list[str]]] = {
    "Death Row": [[LAND_VEHICLES_ITEM], [AIR_VEHICLES_ITEM]],
    "Gun Runner": [[WEAPON_EQUIP_ITEM], [LAND_VEHICLES_ITEM]],
    "Road Kill": [[WEAPON_EQUIP_ITEM], [LAND_VEHICLES_ITEM]],
    "Hit the Courier": [[LAND_VEHICLES_ITEM], [AIR_VEHICLES_ITEM]],
}

# The five ways onto Leaf Links the audit gives, which the golf course's five
# packages and its three ambient pickups all carry: drive in, fly in, sail in,
# jump the fence, or walk in through the gate Four Iron opens.
LEAF_LINKS_ROUTES: list[list[str]] = [
    [LAND_VEHICLES_ITEM],
    [AIR_VEHICLES_ITEM],
    [SEA_VEHICLES_ITEM],
    [JUMP_ITEM],
    [mission_passed_item_name("Four Iron")],
]

# Packages that can be got at more than one way: the first two sit out in the
# water, most of the rest are on roofs a car can be jumped off or a helicopter
# landed on, and five are inside Leaf Links.
PACKAGE_ABILITY_ALTERNATIVES: dict[int, list[list[str]]] = {
    3: [[AIR_VEHICLES_ITEM], [SEA_VEHICLES_ITEM]],
    4: [[AIR_VEHICLES_ITEM], [SEA_VEHICLES_ITEM]],
    7: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    12: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    21: [[AIR_VEHICLES_ITEM]],
    25: [[AIR_VEHICLES_ITEM], [mission_passed_item_name("Treacherous Swine")]],
    40: [[AIR_VEHICLES_ITEM]],
    41: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    42: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    46: LEAF_LINKS_ROUTES,
    47: LEAF_LINKS_ROUTES,
    48: LEAF_LINKS_ROUTES,
    49: LEAF_LINKS_ROUTES,
    50: LEAF_LINKS_ROUTES,
    54: [[AIR_VEHICLES_ITEM], [JUMP_ITEM]],
    65: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    86: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM], [SPRINT_ITEM, JUMP_ITEM]],
    89: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    91: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM, JUMP_ITEM]],
    92: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    100: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
}

# The ambient pickup slots the audit gives a reach term, by slot index. Walking
# over a pickup takes nothing; getting to one is the question these answer, and
# only the slots the audit writes a term on are here.
#
# The three bribes are over ramps a car has to take, and the Viceport sniper is
# on the bridge rail, which takes a jump and then either a car to jump off or a
# sprint into it.
PICKUP_ABILITY_REQUIREMENTS: dict[int, list[str]] = {
    8: [LAND_VEHICLES_ITEM],
    10: [LAND_VEHICLES_ITEM],
    12: [LAND_VEHICLES_ITEM],
    41: [JUMP_ITEM],
}

# The pickup slots with several ways in, same shape as the package table. Three
# are inside Leaf Links and one is the Viceport bridge rail, reached off a car or
# at a run; the other ten are roofs, which is why so many read "a helicopter or
# the mission that leaves one standing there".
PICKUP_ABILITY_ALTERNATIVES: dict[int, list[list[str]]] = {
    22: [[AIR_VEHICLES_ITEM], [JUMP_ITEM]],
    31: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    33: LEAF_LINKS_ROUTES,
    41: [[LAND_VEHICLES_ITEM], [SPRINT_ITEM]],
    46: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    59: LEAF_LINKS_ROUTES,
    64: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    65: [[AIR_VEHICLES_ITEM], [mission_passed_item_name("G-spotlight")]],
    66: [[AIR_VEHICLES_ITEM], [mission_passed_item_name("Trojan Voodoo")]],
    69: [[AIR_VEHICLES_ITEM], [mission_passed_item_name("Loose Ends")]],
    85: LEAF_LINKS_ROUTES,
    86: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    87: [[AIR_VEHICLES_ITEM], [mission_passed_item_name("G-spotlight")]],
    103: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
}

# The pickup slots a mission stands between the player and.
#
# Two different reasons sit in one table, because the term is the same either
# way. The first three are inside Diaz's mansion, which is shut until Rub Out
# hands the place over: the pickup is there from a new game and the DOOR is what
# waits. The last six are the permanent creations, and for those the pickup
# itself does not exist until the mission passes, which is a harder gate than a
# door and needs no separate expression.
#
# The six also need nothing else. Four are in the estate courtyard Rub Out hands
# over, so the mission carries the island with it; the knife stands on the
# pavement outside the Malibu Club; and the minigun is up the ruins of the drugs
# factory, which the same mission that places it is what opens, the way slot 66
# inside that factory already reads.
PICKUP_MISSION_REQUIREMENTS: dict[int, list[str]] = {
    61: ["Rub Out"],
    62: ["Rub Out"],
    101: ["Rub Out"],
    110: ["Rub Out"],
    111: ["Rub Out"],
    112: ["Rub Out"],
    113: ["Rub Out"],
    114: ["The Job"],
    115: ["Trojan Voodoo"],
}


# Two rampages whose icon cannot be walked to. There are four rocket launcher
# rampages and two of them are in Viceport, so these are named by index and by
# the name the table gives them: 2 is "Rampage - Escobar International - RPG",
# reached by air or by road, and 25 is "Rampage - Viceport - RPG", out in the
# water and reached by air or by boat.
#
# Both keep the weapon their class rule gives them. The audit names the weapon
# for 25 and not for 2, and the two are the same kind of site, so the weapon
# stays on both as the stricter reading of a sheet that disagrees with itself.
RAMPAGE_ABILITY_ALTERNATIVES: dict[int, list[list[str]]] = {
    2: [[AIR_VEHICLES_ITEM], [LAND_VEHICLES_ITEM]],
    25: [[AIR_VEHICLES_ITEM], [SEA_VEHICLES_ITEM]],
}


# Where a route's vehicle comes from, for the rows the audit writes it on. Those
# are the collectible rows whose only way in is a vehicle, never a mission row:
# a mission that needs a boat or a helicopter is handed one, which is why Dildo
# Dodo and Checkpoint Charlie name a bare vehicle and stop there.
#
# A helicopter is on the mainland, or on the start island once Rub Out has
# spawned the Vice Point Sparrow. The audit's third source, the Sea Sparrow at
# the mansion, is the eighty-package reward and a useful item, so no rule may
# name it. A boat comes from Cortez's last mission or Diaz's second.
#
# The mainland is named by whatever the seed's crossings setting puts in the
# pool, which is why this is a function and not a table: with the crossings split
# there is no Mainland Access item to name.
SEA_SOURCES: list[list[str]] = [
    [mission_passed_item_name("All Hands On Deck!")],
    [mission_passed_item_name("Phnom Penh '86")],
]
SOURCED_VEHICLES: frozenset[str] = frozenset({AIR_VEHICLES_ITEM, SEA_VEHICLES_ITEM})


def vehicle_source_groups(vehicle: str,
                          split_mainland_access: bool) -> list[list[str]]:
    if vehicle == SEA_VEHICLES_ITEM:
        return [list(source) for source in SEA_SOURCES]
    return [
        *region_access_groups(REGION_MAINLAND, split_mainland_access,
                              routes_allowed=False),
        [mission_passed_item_name("Rub Out")],
    ]


def sourced_routes(routes: list[list[str]],
                   split_mainland_access: bool) -> list[list[str]]:
    """The same routes with each vehicle's sources spelled out.

    One route in becomes one route per source, since a route is a set of things
    all needed and the sources are alternatives. A route naming no vehicle comes
    back as it went in.
    """
    expanded: list[list[str]] = []
    for route in routes:
        vehicles = [item for item in route if item in SOURCED_VEHICLES]
        assert len(vehicles) < 2, f"{route} names two vehicles"
        if not vehicles:
            expanded.append(list(route))
            continue
        expanded.extend(
            [*route, *source]
            for source in vehicle_source_groups(vehicles[0], split_mainland_access))
    return expanded


def sourced_route_locations() -> frozenset[str]:
    """Locations whose routes name where the vehicle comes from.

    The collectible rows, which is where the audit writes the condition. A
    mission's routes are left alone: the mission hands the vehicle over, and
    sourcing them would put Rub Out inside Death Row's rule and Death Row is what
    Rub Out waits on.
    """
    return frozenset(
        [hidden_package_name(index) for index in PACKAGE_ABILITY_ALTERNATIVES]
        + [rampage_name(index) for index in RAMPAGE_ABILITY_ALTERNATIVES]
        + [pickup_name(index) for index in PICKUP_ABILITY_ALTERNATIVES]
    )


def location_ability_alternatives() -> dict[str, list[list[str]]]:
    """Every location's several-routes requirement, by location name.

    Built the same way as location_ability_requirements, so a rename of a
    collectible moves its routes with it. The routes are the audit's own, with no
    vehicle source spelled out: rules.py adds those, since which item names the
    mainland depends on the seed.
    """
    alternatives: dict[str, list[list[str]]] = {
        mission: [list(route) for route in routes]
        for mission, routes in MISSION_ABILITY_ALTERNATIVES.items()
    }
    for index, routes in PACKAGE_ABILITY_ALTERNATIVES.items():
        alternatives[hidden_package_name(index)] = [list(route) for route in routes]
    for index, routes in RAMPAGE_ABILITY_ALTERNATIVES.items():
        alternatives[rampage_name(index)] = [list(route) for route in routes]
    for index, routes in PICKUP_ABILITY_ALTERNATIVES.items():
        alternatives[pickup_name(index)] = [list(route) for route in routes]
    return alternatives


def location_ability_requirements() -> dict[str, list[str]]:
    """Every location's ability items, the minimal day-one set. A term binds
    only while its ability_locks key is selected (rules.py filters); with the
    key off the item is not in the pool and the location plays vanilla.

    Class-wide entries: every unique stunt jump and every emergency level takes
    a land vehicle, and a Vigilante level takes a weapon besides; a chopper
    checkpoint takes a helicopter and every other side event a land vehicle, the
    stadium events included, since the event is driven even where its launcher
    warps the player into the car rather than asking them to arrive in one;
    robbing a store takes aiming a
    weapon (bare fists cannot); a weapon rampage wields its handed weapon while
    the two run-them-down rampages take a land vehicle, with five rampages
    needing more than that; five hidden packages cannot be walked to; a
    safehouse purchase takes holdable money (a business purchase carries
    the wallet through the property-sale requirements instead); and each Sunshine
    Autos race is driven in the player's own car, since the launcher takes them
    on foot and the mission creates only the opponents.
    """
    requirements: dict[str, list[str]] = {}
    for mission, items in MISSION_ABILITY_REQUIREMENTS.items():
        requirements[mission] = list(items)
    for index in range(1, STUNT_JUMP_COUNT + 1):
        requirements[stunt_jump_name(index)] = [LAND_VEHICLES_ITEM]
    for activity, levels in EMERGENCY_LEVELS.items():
        extras = EMERGENCY_ABILITY_EXTRAS.get(activity, [])
        for level in range(1, levels + 1):
            requirements[emergency_name(activity, level)] = [
                LAND_VEHICLES_ITEM, *extras]
    for name in SIDE_EVENTS:
        requirements[name] = (
            [AIR_VEHICLES_ITEM] if name in AIR_SIDE_EVENTS else [LAND_VEHICLES_ITEM]
        )
    for index in range(1, ROBBABLE_STORE_COUNT + 1):
        requirements[robbable_store_name(index)] = [WEAPON_EQUIP_ITEM]
    # Walking over a pickup takes no ability, so nothing here is about TAKING
    # one. Reaching one is a different question, and the hand audit has now
    # answered it for every slot: 20 carry a reach term, six more wait on the
    # mission that creates them, and the rest are walked to. A slot with no term is one the audit walked and found free,
    # which is what it could not say while the terms were unwritten and the
    # fill was entitled to put progression on a rooftop nothing opened.
    #
    # The ten in-shop stands charge for what they give, and with the wallet key
    # selected the money pins to zero, so those alone wait on the Wallet item.
    for index in PICKUP_PAY_STAND_INDICES:
        requirements[pickup_name(index)] = [WALLET_ITEM]
    # Then the reach terms the hand audit found, added to whatever a slot
    # already carries, since a pay stand can also be somewhere hard to get to.
    for index, items_needed in PICKUP_ABILITY_REQUIREMENTS.items():
        requirements[pickup_name(index)] = [
            *requirements.get(pickup_name(index), []), *items_needed]
    # Every shop item is bought, and with the wallet key selected the money pins
    # to zero, so all 36 wait on the Wallet item. Amounts still gate nothing: the
    # dearest is the minigun at Phil's Place, 10000 dollars from the game's own
    # price table, and money is grindable once Tommy can hold it.
    for shop_item in shop_data.SHOP_ITEMS:
        requirements[shop_data.shop_item_name(shop_item)] = [WALLET_ITEM]
    for index in range(1, RAMPAGE_COUNT + 1):
        base = ([LAND_VEHICLES_ITEM] if index in VEHICLE_RAMPAGE_INDICES
                else [WEAPON_EQUIP_ITEM])
        extras = [item for item in RAMPAGE_ABILITY_EXTRAS.get(index, [])
                  if item not in base]
        requirements[rampage_name(index)] = [*base, *extras]
    for index, items in PACKAGE_ABILITY_REQUIREMENTS.items():
        requirements[hidden_package_name(index)] = list(items)
    for purchase in PROPERTY_PURCHASES:
        if purchase not in BUSINESS_PURCHASES:
            requirements[purchase] = [WALLET_ITEM]
    for name in SUNSHINE_RACES:
        requirements[name] = [LAND_VEHICLES_ITEM]
    return requirements


LOCATION_ABILITY_REQUIREMENTS: dict[str, list[str]] = location_ability_requirements()
LOCATION_ABILITY_ALTERNATIVES: dict[str, list[list[str]]] = location_ability_alternatives()
SOURCED_ROUTE_LOCATIONS: frozenset[str] = sourced_route_locations()
LOCATION_MISSION_REQUIREMENTS: dict[str, list[str]] = {
    **CHOPPER_MISSION_REQUIREMENTS,
    **stunt_jump_mission_requirements(),
    **{pickup_name(index): list(missions)
       for index, missions in PICKUP_MISSION_REQUIREMENTS.items()},
    **{shop_data.shop_item_name(item): [shop_data.SHOP_STOCK_MISSIONS[key]]
       for item in shop_data.SHOP_ITEMS
       for key in [(item.thread, item.script_global)]
       if key in shop_data.SHOP_STOCK_MISSIONS},
}


def _content_class_locations() -> dict[str, list[str]]:
    """Each content class's locations, in the order its district table is in."""
    return {
        HIDDEN_PACKAGES_ITEM: [hidden_package_name(index)
                               for index in range(1, HIDDEN_PACKAGE_COUNT + 1)],
        RAMPAGES_ITEM: [rampage_name(index)
                        for index in range(1, RAMPAGE_COUNT + 1)],
        STUNT_JUMPS_ITEM: [stunt_jump_name(index)
                           for index in range(1, STUNT_JUMP_COUNT + 1)],
        PROPERTY_PURCHASES_ITEM: list(PROPERTY_PURCHASES),
        ROBBABLE_STORES_ITEM: [robbable_store_name(index)
                               for index in range(1, ROBBABLE_STORE_COUNT + 1)],
    }


CONTENT_CLASS_LOCATIONS: dict[str, list[str]] = _content_class_locations()

# Every lockable location's district, from its position in its class's table.
_LOCATION_DISTRICTS: dict[str, str] = {
    location: CONTENT_DISTRICT_TABLES[item][index]
    for item, locations_in_class in CONTENT_CLASS_LOCATIONS.items()
    for index, location in enumerate(locations_in_class)
}

# Which content class each lockable location belongs to. Independent of the
# granularity, so a rule can ask whether a location is locked at all before
# working out which item covers it.
LOCATION_CONTENT_CLASS: dict[str, str] = {
    location: item
    for item, locations_in_class in CONTENT_CLASS_LOCATIONS.items()
    for location in locations_in_class
}


def content_item_for(location_name: str, split: int) -> str | None:
    """The content item covering this location, at this granularity.

    One item either way: a class item holding the whole city, or the item
    holding this location's district. Returns None for a location no content
    key covers.
    """
    item = LOCATION_CONTENT_CLASS.get(location_name)
    if item is None:
        return None
    if split == CONTENT_SPLIT_OFF:
        return item
    district = _LOCATION_DISTRICTS[location_name]
    if split == CONTENT_SPLIT_PER_DISTRICT:
        return district_content_item_name(district)
    return district_class_item_name(district, item)


def property_content_items(split: int) -> list[str]:
    """Every item that has to arrive before ANY property can be bought.

    For the one caller that cannot name a property: the finale with the
    properties class off, where no purchase location exists to carry a term but
    vanilla asset completion still spends money at property icons. Whole, that
    is the one class item. Split, it is every district holding a property, which
    is stricter than vanilla needs and deliberately so, since over-requiring
    here costs a little fill freedom and under-requiring could strand the
    finale behind icons that are still held.
    """
    if split == CONTENT_SPLIT_OFF:
        return [PROPERTY_PURCHASES_ITEM]
    covering = [content_item_for(purchase, split) for purchase in PROPERTY_PURCHASES]
    return list(dict.fromkeys(item for item in covering if item is not None))


def location_content_requirements(
    split: int = CONTENT_SPLIT_OFF,
) -> dict[str, list[str]]:
    """Every location's content-lock item, at the seed's granularity.

    With the locks whole this is uniform across a class, since one key holds one
    whole class: every location in the class carries the one item. Split, it is
    the item covering that location's district instead, so it is still exactly
    one item per location, just a narrower one. A term binds only while its
    content_locks key is selected (rules.py filters); with the key off the item
    is not in the pool and the class plays vanilla.

    Every property purchase is listed, but a business purchase never reads its
    entry: rules.py already rules those through the property-sale requirements,
    which the term rides so it reaches venue missions and the finale as well.
    The entry is what carries a safehouse purchase, which has no other rule.
    """
    requirements: dict[str, list[str]] = {}
    for item, locations_in_class in CONTENT_CLASS_LOCATIONS.items():
        for location in locations_in_class:
            if split == CONTENT_SPLIT_OFF:
                requirements[location] = [item]
            elif split == CONTENT_SPLIT_PER_DISTRICT:
                requirements[location] = [
                    district_content_item_name(_LOCATION_DISTRICTS[location])]
            else:
                requirements[location] = [
                    district_class_item_name(_LOCATION_DISTRICTS[location], item)]
    return requirements


LOCATION_CONTENT_REQUIREMENTS: dict[str, list[str]] = location_content_requirements()


# Reward mirror. The mod pays no cash on a mission pass (build_scm.py strips it);
# the AP check is the reward. To keep money principled instead of arbitrary, each
# enabled check contributes one filler item mirroring the cash it would have paid
# in vanilla: cash for the checks that paid, generic filler for the ones that did
# not. Money never gates logic, so every mirror item is filler. Hidden packages
# are the one deliberate departure: vanilla pays each a flat $100 that the ASI
# takes back, and the pool returns a graded spread instead (PACKAGE_CASH_TIERS).

# Side events each paid a flat $100 pickup in vanilla.
SIDE_EVENT_CASH = 100

# Vanilla pays a flat $100 per package, from the executable's pickup code rather
# than the script (the ASI takes that payout back while this class is on). This
# graded spread is a deliberate variance choice for the pool, not a mirror of the
# flat hundred. The counts sum to HIDDEN_PACKAGE_COUNT.
PACKAGE_CASH_TIERS: list[tuple[int, int]] = [(100, 40), (250, 30), (500, 20), (1000, 10)]


def package_cash_reward(index: int) -> int:
    # Index is 1-based in placement order; the tiers fill in that order. The exact
    # package-to-tier mapping does not matter (the cash is pool filler, not an
    # in-game package reward), only the resulting multiset of values.
    position = index
    for amount, count in PACKAGE_CASH_TIERS:
        if position <= count:
            return amount
        position -= count
    return PACKAGE_CASH_TIERS[-1][0]


def stunt_jump_reward(index: int) -> int:
    # Vanilla pays $100 * n for the nth unique jump, and $10,000 for the last one.
    return 10_000 if index == STUNT_JUMP_COUNT else 100 * index


def rampage_reward(index: int) -> int:
    # Vanilla pays $50 * n for the nth rampage and a flat $1,000 for the last,
    # from the RAMPAGE thread in the decompile ($1401 = count * 50, the final
    # branch pays 1000).
    return 1_000 if index == RAMPAGE_COUNT else 50 * index


# Suppressed vanilla mission cash: the amount build_scm.py strips (story) or
# gates on the properties flag (venue) in each mission's pass path, zero where
# a mission pays nothing (it then mirrors to generic filler). Verified against
# a clean 1.0 decompile with scripts/dump_mission_rewards.py; Checkpoint
# Charlie carries its first-run 5000 only, since the replay tiers stay
# vanilla winnings.
MISSION_REWARDS: dict[str, int] = {
    # Rosenberg
    "An Old Friend": 0, "The Party": 100, "Back Alley Brawl": 200,
    "Jury Fury": 400, "Riot": 1000,
    # Cortez
    "Treacherous Swine": 250, "Mall Shootout": 500, "Guardian Angels": 1000,
    "Sir, Yes Sir!": 2000, "All Hands On Deck!": 5000,
    # Diaz
    "The Chase": 1000, "Phnom Penh '86": 2000, "The Fastest Boat": 4000,
    "Supply & Demand": 10000, "Rub Out": 50000,
    # Death Row
    "Death Row": 0,
    # Avery
    "Four Iron": 500, "Demolition Man": 1000, "Two Bit Hit": 2500,
    # Phil Cassidy
    "Gun Runner": 2000, "Boomshine Saigon": 4000,
    # Vercetti Protection
    "Shakedown": 2000, "Bar Brawl": 4000, "Cop Land": 10000,
    # Big Mitch Baker
    "Alloy Wheels of Steel": 1000, "Messing with the Man": 2000, "Hog Tied": 4000,
    # Umberto Robina
    "Stunt Boat Challenge": 1000, "Cannon Fodder": 2000, "Naval Engagement": 4000,
    "Trojan Voodoo": 10000,
    # Auntie Poulet
    "Juju Scramble": 1000, "Bombs Away!": 2000, "Dirty Lickin's": 5000,
    # Love Fist
    "Love Juice": 2000, "Psycho Killer": 4000, "Publicity Tour": 8000,
    # Mr. Black
    "Road Kill": 500, "Waste the Wife": 2000, "Autocide": 4000,
    "Check Out at the Check In": 8000, "Loose Ends": 16000,
    # Vercetti Finale
    "Cap the Collector": 30000, "Keep Your Friends Close...": 30000,
    # Malibu Club
    "No Escape?": 1000, "The Shootist": 2000, "The Driver": 3000, "The Job": 50000,
    # Film Studio
    "Recruitment Drive": 1000, "Dildo Dodo": 2000, "Martha's Mug Shot": 4000,
    "G-spotlight": 8000,
    # Printworks
    "Spilling the Beans": 2000, "Hit the Courier": 5000,
    # Kaufman Cabs
    "V.I.P.": 1000, "Friendly Rivalry": 2000, "Cabmaggedon": 5000,
    # Cherry Popper
    "Distribution": 0,
    # Boatyard
    "Checkpoint Charlie": 5000,
    # Sunshine Autos. An import list pays no cash of its own: it raises the
    # asset's daily take instead. A race pays its prize on every win, and the
    # check eats the first win only, so the prize is what the mirror returns.
    "Sunshine Autos Import List 1": 0, "Sunshine Autos Import List 2": 0,
    "Sunshine Autos Import List 3": 0, "Sunshine Autos Import List 4": 0,
    "Sunshine Autos Race: Terminal Velocity": 400,
    "Sunshine Autos Race: Ocean Drive": 2000,
    "Sunshine Autos Race: Border Run": 4000,
    "Sunshine Autos Race: Capital Cruise": 8000,
    "Sunshine Autos Race: Tour!": 20000,
    "Sunshine Autos Race: V.C. Endurance": 40000,
}


def _build_location_reward() -> dict[str, int]:
    # Every location name -> the vanilla cash it would have paid (0 = no cash, so
    # generic filler). Built from the same content tables the locations come from,
    # so it stays one entry per location.
    reward: dict[str, int] = {}
    for missions in STORY_GIVERS.values():
        for mission in missions:
            reward[mission] = MISSION_REWARDS[mission]
    for missions in VENUE_STRANDS.values():
        for mission in missions:
            reward[mission] = MISSION_REWARDS[mission]
    for activities in VENUE_ACTIVITIES.values():
        for activity in activities:
            reward[activity] = MISSION_REWARDS[activity]
    for index, name in enumerate(package_data.PACKAGE_NAMES, start=1):
        reward[name] = package_cash_reward(index)
    for name in SIDE_EVENTS:
        reward[name] = SIDE_EVENT_CASH
    for index in range(1, RAMPAGE_COUNT + 1):
        reward[rampage_name(index)] = rampage_reward(index)
    for index in range(1, STUNT_JUMP_COUNT + 1):
        reward[stunt_jump_name(index)] = stunt_jump_reward(index)
    for name in emergency_names():
        reward[name] = 0
    for index in range(1, ROBBABLE_STORE_COUNT + 1):
        reward[robbable_store_name(index)] = 0
    for name in PROPERTY_PURCHASES:
        reward[name] = 0
    # A pickup paid no cash in vanilla, it handed over a weapon or a heart, so
    # the mirror has nothing to give back and these sort last as generic filler.
    # The ten in-shop stands COST money rather than paying it, and a negative
    # entry would ask the mirror to take cash away, which it cannot do; they are
    # zero like the rest.
    for index in range(PICKUP_COUNT):
        reward[pickup_name(index)] = 0
    # A shop item COSTS money rather than paying it, for the same reason the
    # in-shop stands do, so it is zero here too: a negative entry would ask the
    # mirror to take cash away, which it cannot do.
    for name in shop_data.SHOP_ITEM_NAMES:
        reward[name] = 0
    return reward


LOCATION_REWARD: dict[str, int] = _build_location_reward()


def mirror_item(location_name: str) -> str | None:
    # The filler mirroring a location's vanilla reward: a cash item at its value,
    # or None (a generic-filler placeholder) when the check paid no cash.
    amount = LOCATION_REWARD[location_name]
    return cash_item_name(amount) if amount > 0 else None


# The static universe of cash denominations, independent of options so the item
# id table is stable across seeds: every distinct positive reward value.
CASH_VALUES: list[int] = sorted({amount for amount in LOCATION_REWARD.values() if amount > 0})

# All filler item names: one cash item per distinct reward value, plus the
# generic consumables. items.py assigns ids from this list and classifies it
# filler; create_items draws the actual per-seed filler from the reward mirror.
FILLER_ITEMS: list[str] = [cash_item_name(amount) for amount in CASH_VALUES] + GENERAL_FILLER
# A denomination and the package bonus are both named for their amount alone, so
# a check paying exactly the bonus amount gives two items one name, and both the
# id table and the effect table below are dicts that would silently keep one. The
# bonus is a useful one-shot and a denomination is filler, so the collision fails
# here rather than resolving into whichever happens to win.
#
# This is the fast guard, not the only one: the frozen Archipelago build compiles
# with asserts optimized away, so test_no_two_items_share_a_name carries the
# general invariant and covers every other pair as well.
assert PACKAGE_CASH_REWARD not in FILLER_ITEMS, (
    f"the package bonus {PACKAGE_CASH_REWARD} collides with a cash denomination")

# One-shot consumable effects, each applied once by the ASI past the saved
# applied-index. (item name -> (effect type, *params)); cash carries its amount.
# Like all item application they wait for the player to be controllable, so a
# grant can never land on a world a script still owns and be undone by it.
CONSUMABLE_EFFECTS: dict[str, tuple] = {
    **{cash_item_name(amount): ("cash", amount) for amount in CASH_VALUES},
    PACKAGE_CASH_REWARD: ("cash", 100000),
    "Weapon Pickup": ("weapon",),
    "Health Top-up": ("health",),
    "Armor Top-up": ("armor",),
    "Remove Wanted Level": ("clear_wanted",),
}
