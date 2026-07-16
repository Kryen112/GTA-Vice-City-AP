"""Content tables for GTA: Vice City, hand-written from the SCM decompile.

This is plain owned data, not a generated format. Mission names and their
per-giver order come from the vanilla main.scm DEFINE MISSION table. Giver
grouping and the region (island) assignment below are provisional first
readings; the exact cross-giver spine edges and island barriers are pinned
from the SCM in a dedicated extraction pass and refined in per-giver Phase 3
audits. Nothing here gates logic on money.
"""

from __future__ import annotations

from . import package_data

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
        "Four Iron", "Two Bit Hit", "Demolition Man",
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
# check) and then plays its own mission strand; buying is money, which is
# grindable, so ownership is not a logic gate. Progressive unlocks work the
# same as story givers. These are independent of the story spine.
VENUE_STRANDS: dict[str, list[str]] = {
    "Malibu Club": ["No Escape?", "The Shootist", "The Driver", "The Job"],
    "Film Studio": [
        "Recruitment Drive", "Dildo Dodo", "Martha's Mug Shot", "G-spotlight",
    ],
    "Printworks": ["Spilling the Beans", "Hit the Courier"],
    "Kaufman Cabs": ["V.I.P.", "Friendly Rivalry", "Cabmaggedon"],
    "Cherry Popper": ["Distribution"],
    "Boatyard": ["Checkpoint Charlie"],
    "Sunshine Autos": ["Sunshine Autos Races"],
}

# Property purchase checks. Buying a property is reachable once its area is
# (money is grindable), so these carry no access rule beyond their region.
# The businesses front the venue strands above; the rest are safehouses.
PROPERTY_PURCHASES: list[str] = [
    "Printworks Purchase", "Sunshine Autos Purchase", "Film Studio Purchase",
    "Cherry Popper Purchase", "Kaufman Cabs Purchase", "Malibu Club Purchase",
    "Boatyard Purchase", "Pole Position Purchase", "El Swanko Casa Purchase",
    "Links View Apartment Purchase", "Hyman Condo Purchase",
    "Ocean Heights Apartment Purchase", "1102 Washington Street Purchase",
    "Vice Point Purchase", "Skumole Shack Purchase",
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
# no in-game effect, so it maps to no SCM global.
HIDDEN_PACKAGE_ITEM = "Hidden Package"


def hidden_package_name(index: int) -> str:
    # Per physical package, in the SCM create_collectable1 placement order (index
    # i is the ith placed package). Names carry the district; the ASI detects each
    # one individually by coordinate.
    return package_data.PACKAGE_NAMES[index - 1]


# Rewards that leave the vanilla hidden-package threshold and enter the pool
# when the hidden-packages class is on. Useful items, never progression.
PACKAGE_REWARD_ITEMS: list[str] = [
    "Body Armor", "Chainsaw", ".357", "Flamethrower", ".308 Sniper",
    "Minigun", "Rocket Launcher", "Sea Sparrow Spawn", "Rhino Spawn",
    "Hunter Spawn", "$100,000",
]

AREA_ITEMS: list[str] = ["Mainland Access"]

# The five emergency-vehicle completion rewards. When the shuffle option is on
# they enter the pool as useful items and the vanilla full-completion grant is
# suppressed; when off they grant vanilla and stay out of the pool.
EMERGENCY_REWARD_ITEMS: list[str] = [
    "Infinite Sprint", "Fireproof", "Max Armor Upgrade", "Taxi Nitro", "Max Health Upgrade",
]

# Which reward item each activity's full completion grants.
EMERGENCY_REWARD_BY_ACTIVITY: dict[str, str] = {
    "Paramedic": "Infinite Sprint",
    "Firefighter": "Fireproof",
    "Vigilante": "Max Armor Upgrade",
    "Taxi": "Taxi Nitro",
    "Pizza": "Max Health Upgrade",
}

# Cash filler comes in fixed denominations mirroring the suppressed mission
# rewards; each grants its face value once. Money never gates logic.
CASH_DENOMINATIONS: list[int] = [500, 1000, 2000, 5000, 10000, 25000, 50000]


def cash_item_name(amount: int) -> str:
    return f"Cash ${amount:,}"


# Consumable filler: the cash denominations plus one-shot health and armor top-
# ups and a random weapon pickup. All one-shot, all filler, none gate logic.
FILLER_ITEMS: list[str] = (
    [cash_item_name(amount) for amount in CASH_DENOMINATIONS]
    + ["Weapon Pickup", "Health Top-up", "Armor Top-up"]
)

# The package cash reward has no vanilla package grant (the VC package system
# gives no money), so it is a one-shot cash item like the filler denominations,
# not a re-gated pickup.
PACKAGE_CASH_REWARD = "$100,000"

# Persistent rewards re-gate a vanilla respawning grant (safehouse weapon pickup,
# car generator, or completion ability) onto an AP reward global instead of the
# vanilla trigger. The ten package weapon/vehicle rewards plus the five
# emergency abilities. Order is stable: it drives the reward-global indices.
PERSISTENT_REWARD_ITEMS: list[str] = (
    [item for item in PACKAGE_REWARD_ITEMS if item != PACKAGE_CASH_REWARD]
    + EMERGENCY_REWARD_ITEMS
)

# One-shot consumable effects, each applied once by the ASI past the saved
# applied-index. (item name -> (effect type, *params)); cash carries its amount.
CONSUMABLE_EFFECTS: dict[str, tuple] = {
    **{cash_item_name(amount): ("cash", amount) for amount in CASH_DENOMINATIONS},
    PACKAGE_CASH_REWARD: ("cash", 100000),
    "Weapon Pickup": ("weapon",),
    "Health Top-up": ("health",),
    "Armor Top-up": ("armor",),
}

# Other check classes beyond story missions and hidden packages. Counts come
# from the game design in PLAN and the decompiled mission table. These are
# free-roam collectibles and activities; their locations carry no access rule
# beyond the region they sit in.
RAMPAGE_COUNT = 35
STUNT_JUMP_COUNT = 36


# Rampage names: the weapon the RAMPAGE controller hands the player (its $1518
# model id, read from the SCM) plus the district. Rampages 14 and 21 hand no fixed
# weapon. The MP5 pair at Vice Point is disambiguated 1/2. Districts are
# provisional, auto-derived from the kill-frenzy pickup coordinates, pending an
# in-game audit. Order is fixed: index i is rampage i, so location ids and
# completion globals stay stable across the rename.
RAMPAGE_NAMES: list[str] = [
    "Tear Gas Rampage - Ocean Beach",
    "Rocket Launcher Rampage - Escobar International",
    "MP5 Rampage - Vice Point 1",
    "Tec-9 Rampage - Vice Point",
    "Rocket Launcher Rampage - Vice Point",
    "Ruger Rampage - Vice Point",
    "Flamethrower Rampage - Downtown",
    "MP5 Rampage - Downtown",
    "Tear Gas Rampage - Downtown",
    "M60 Rampage - Little Haiti",
    "Mac-10 Rampage - Little Havana",
    "Chainsaw Rampage - Washington Beach",
    ".308 Sniper Rampage - Ocean Beach",
    "Rampage - Little Havana",
    ".357 Rampage - Escobar International",
    "Rocket Launcher Rampage - Viceport",
    "Minigun Rampage - Little Havana",
    "Grenade Rampage - Escobar International",
    "Sniper Rifle Rampage - Little Havana",
    "Katana Rampage - Washington Beach",
    "Rampage - Ocean Beach",
    "Pistol Rampage - Vice Point",
    "MP5 Rampage - Vice Point 2",
    "Chainsaw Rampage - Vice Point",
    "Rocket Launcher Rampage - Ocean Beach",
    "Minigun Rampage - Vice Point",
    "Pistol Rampage - Downtown",
    "Shotgun Rampage - Escobar International",
    ".308 Sniper Rampage - Vice Point",
    "Shotgun Rampage - Washington Beach",
    "S.P.A.S. 12 Rampage - Vice Point",
    "S.P.A.S. 12 Rampage - Little Havana",
    "S.P.A.S. 12 Rampage - Escobar International",
    "Tec-9 Rampage - Washington Beach",
    "Katana Rampage - Escobar International",
]


def rampage_name(index: int) -> str:
    return RAMPAGE_NAMES[index - 1]


def stunt_jump_name(index: int) -> str:
    return f"Unique Stunt Jump {index:02d}"


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


def robbable_store_name(index: int) -> str:
    return f"Robbable Store {index:02d}"


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
            + [mission for missions in VENUE_STRANDS.values() for mission in missions],
        ),
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


# Cross-giver story spine, the hard chain, pinned from the SCM CELL controller
# (Kent Paul's phone thread). Each entry gates a giver's whole strand behind
# owning the unlocks to complete a prerequisite giver's strand up to the named
# point; the count is that prerequisite giver's progressive-unlock count. Side
# givers (Avery, Phil Cassidy, Big Mitch Baker, Umberto Robina, Auntie Poulet,
# Love Fist, Mr. Black, and the venue strands) are deliberately independent and
# are not listed; area access still gates the ones on the mainland.
# The chain in vanilla: Cortez opens after Riot (Rosenberg's last); Diaz after
# All Hands On Deck (Cortez's last); Death Row after Supply & Demand (Diaz's
# fourth) and Sir, Yes Sir! (Cortez's fourth); Vercetti protection at the
# mansion after Rub Out; the finale after the protection strand plus asset
# ownership. Asset ownership is money, which is grindable, so it is not
# encoded as a logic gate.
SPINE_PREREQUISITES: dict[str, list[tuple[str, int]]] = {
    "Cortez": [("Rosenberg", 4)],
    "Diaz": [("Cortez", 5)],
    "Death Row": [("Diaz", 4)],
    "Vercetti Protection": [("Diaz", 5), ("Death Row", 1)],
    "Vercetti Finale": [("Vercetti Protection", 3)],
}

# Cross-giver edges that gate a single mission rather than a whole strand. Rub
# Out (Diaz's last) needs Lance rescued in Death Row first.
MISSION_PREREQUISITES: dict[str, list[tuple[str, int]]] = {
    "Rub Out": [("Death Row", 1)],
}


# Region model, pinned from the SCM. The vanilla map has one persistent island
# barrier: three bridge roadblocks that all delete together, and the flag $847
# that all set, when Phnom Penh '86 (Diaz's second mission) passes, opening the
# whole west island (the mainland). The AP item Mainland Access stands in for
# that flip. Leaf Links is not a roamable gated area (its gate opens inside Four
# Iron), so the start island is the east beaches plus Starfish, Prawn, and Leaf
# Links; the mainland is everything west of the bridge channel. Island membership
# below is read from each check's world coordinates in the decompile: giver
# marker positions, rampage pickup positions, and payphone positions, split at
# the channel (start-island givers reach X = -379, mainland givers begin at
# X = -597).
REGION_VICE_CITY = "Vice City"
REGION_MAINLAND = "Mainland"

# Story givers whose whole strand sits on the mainland (marker west of the
# channel). Mr. Black is absent because his payphones span both islands (his
# mainland ones are in MAINLAND_MISSIONS). The finale spans both islands but
# stays mainland since it is end-game, past Mainland Access anyway.
MAINLAND_GIVERS: frozenset[str] = frozenset({
    "Big Mitch Baker", "Umberto Robina", "Auntie Poulet",
    "Phil Cassidy", "Love Fist", "Vercetti Finale",
})

# Venue strands whose business sits on the mainland.
MAINLAND_VENUES: frozenset[str] = frozenset({
    "Kaufman Cabs", "Printworks", "Cherry Popper", "Boatyard", "Sunshine Autos",
})

# Individual mainland missions whose giver is not a whole-mainland giver. Mr.
# Black's last two payphones (Check Out at the Check In at X = -1482, Loose Ends
# at X = -978) are on the mainland; his first three are on the start island.
MAINLAND_MISSIONS: frozenset[str] = frozenset({
    "Check Out at the Check In", "Loose Ends",
})


def mission_region(giver: str, mission: str) -> str:
    if mission in MAINLAND_MISSIONS:
        return REGION_MAINLAND
    if giver in MAINLAND_GIVERS or giver in MAINLAND_VENUES:
        return REGION_MAINLAND
    return REGION_VICE_CITY


# Rampages on the mainland, from the kill-frenzy pickup coordinates in the RAMPAGE
# controller (pickup order equals flag order equals check order). Indices with
# pickup X below the bridge channel (about -480) are mainland; rampages 25
# (X = -366, far south) and 26 (X = -449, far north) sit in the band west of the
# beaches and count as mainland too.
MAINLAND_RAMPAGES: frozenset[str] = frozenset(
    rampage_name(index)
    for index in (2, 7, 8, 9, 10, 11, 14, 15, 16, 17, 18, 19, 25, 26, 27, 28, 32, 33, 35)
)

# Hidden packages are per package, each detected individually by the ASI (by
# coordinate) rather than by a running count. Island membership and coordinates
# come from package_data, in the SCM placement order. PACKAGE_COORDS is sent to
# the ASI via slot_data so it can match a collected pickup to its package.
MAINLAND_PACKAGES: frozenset[str] = package_data.MAINLAND_PACKAGES
PACKAGE_COORDS: list[tuple[float, float, float]] = package_data.PACKAGE_COORDS

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

# Robbable stores on the mainland, from each store's locate/area coordinates in
# the store controller (source order equals check order).
MAINLAND_STORES: frozenset[str] = frozenset(
    robbable_store_name(index) for index in (3, 4, 5, 6, 7, 14, 15)
)

# Side events on the mainland. The three stadium events (Hyman Stadium, Downtown)
# and the Downtown and Little Haiti chopper checkpoints are confirmed mainland. RC
# Raider, Trial by Dirt, and Test Track are not coordinate-pinned, so they count
# as mainland for safety (over-gating never softlocks); refine to the start island
# once confirmed. RC Bandit, RC Baron, PCJ Playground, Cone Crazy, and the Ocean
# Beach and Vice Point chopper checkpoints are on the start island.
MAINLAND_SIDE_EVENTS: frozenset[str] = frozenset({
    "Hotring", "Bloodring", "Dirtring",
    "Downtown Chopper Checkpoint", "Little Haiti Chopper Checkpoint",
    "RC Raider Pickup", "Trial by Dirt", "Test Track",
})

# Stunt jumps are exe-native: the SCM only registers a found jump by its engine
# id, so their per-jump islands are not readable from the decompile. All 36 count
# as mainland provisionally (safe over-gating) until an in-game audit places each.
MAINLAND_STUNT_JUMPS: frozenset[str] = frozenset(
    stunt_jump_name(index) for index in range(1, STUNT_JUMP_COUNT + 1)
)
