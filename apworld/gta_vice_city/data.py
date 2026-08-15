"""Content tables for GTA: Vice City, hand-written from the SCM decompile.

This is plain owned data, not a generated format. Mission names and their
per-giver order come from the vanilla main.scm DEFINE MISSION table. Giver
grouping and the region (island) assignment below are provisional first
readings; the cross-giver edges and island barriers are pinned from the SCM
in a dedicated extraction pass and refined in per-giver Phase 3 audits.
Nothing here gates logic on money.
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
# check) and then plays its own mission strand. The purchase price is money,
# which is grindable and never a gate, but a venue mission needs its property
# bought in game and the businesses go on sale only when Shakedown passes, so
# venue missions carry the items to pass Shakedown as a requirement (see
# PROPERTY_UNLOCK_MISSION). Progressive unlocks work the same as story givers.
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
    "Vice Point Purchase", "Skumole Shack Purchase",
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

# The Rosenberg strand opens on a new game with no unlock item (sphere 0).
# Every other giver's first mission needs its first progressive unlock.
SPHERE_ZERO_GIVER = "Rosenberg"

# Strands granted at the start when a seed has too little free sphere-0 room
# (every collectible class off). Each of these sits on the start island, so
# the granted missions are playable immediately. Avery and the early Mr.
# Black payphones also start on the start island but stay in the pool, so
# the fill keeps start-island progression to place.
OPENING_GRANT_GIVERS: list[str] = [
    SPHERE_ZERO_GIVER, "Cortez", "Diaz", "Death Row", "Vercetti Protection",
]

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

def cash_item_name(amount: int) -> str:
    return f"Cash ${amount:,}"


# Generic filler for checks with no vanilla cash reward (properties, robbable
# stores, emergency milestones) and for zero-reward missions: one-shot health and
# armor top-ups, a random weapon pickup, and a wanted-level clear like the
# LEAVEMEALONE cheat. All one-shot, all filler, none gate logic. The cash filler
# items are derived from the reward mirror at the end of this module.
GENERAL_FILLER: list[str] = [
    "Weapon Pickup", "Health Top-up", "Armor Top-up", "Remove Wanted Level",
]

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

# Traps take an equally weighted share of the filler slots, tuned by the
# trap_percentage option. Like consumables they are one-shot effects the ASI
# applies once past the applied-index, so a reconnect never re-fires one. Unlike
# consumables the five chaos traps defer until the player is controllable (the
# one deferral the design allows); stormy weather applies any time. Hostile
# pedestrians, sped-up time, and slowed time last a fixed duration then revert.
# The effect type mirrors the cheat each imitates: wanted level like
# YOUWONTTAKEMEALIVE, exploding cars like BIGBANG, hostile peds like
# NOBODYLIKESME, stormy weather like CATSANDDOGS, speed up like ONSPEED, and
# slow down like BOOOOOORING.
TRAP_DURATION_SECONDS = 30
TRAP_WANTED_STARS = 3

TRAP_EFFECTS: dict[str, tuple] = {
    "Wanted Level Trap": ("trap_wanted", TRAP_WANTED_STARS),
    "Exploding Cars Trap": ("trap_explode_cars",),
    "Hostile Pedestrians Trap": ("trap_hostile_peds", TRAP_DURATION_SECONDS),
    "Stormy Weather Trap": ("trap_weather",),
    "Speed Up Trap": ("trap_speed_up", TRAP_DURATION_SECONDS),
    "Slow Motion Trap": ("trap_slow_down", TRAP_DURATION_SECONDS),
}

# The trap item names, in a stable order.
TRAP_ITEMS: list[str] = list(TRAP_EFFECTS.keys())

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


# Cross-giver prerequisites that gate a whole strand. Every giver's strand
# opens on its own progressive unlocks alone, so the strands play in any
# order: the vanilla phone-call chain (Cortez after Riot, Diaz after All
# Hands On Deck, Death Row after Supply & Demand, the protection strand
# after Rub Out) is deliberately not enforced, and the mod severs the
# vanilla marker reveals and launcher starts that carried it. The one
# strand-level edge kept is the finale, the goal mission, behind the
# protection strand. Asset ownership before the finale is money, which is
# grindable, so it is not encoded as a logic gate.
STRAND_PREREQUISITES: dict[str, list[tuple[str, int]]] = {
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


# Reward mirror. The mod pays no cash on a mission pass (build_scm.py strips it);
# the AP check is the reward. To keep money principled instead of arbitrary, each
# enabled check contributes one filler item mirroring the cash it would have paid
# in vanilla: cash for the checks that paid, generic filler for the ones that did
# not. Money never gates logic, so every mirror item is filler.

# Side events each paid a flat $100 pickup in vanilla.
SIDE_EVENT_CASH = 100

# Hidden packages pay no per-package cash in vanilla; this graded spread is a
# deliberate variance choice for the pool. The counts sum to HIDDEN_PACKAGE_COUNT.
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
    # Vanilla pays $500 for the first rampage and $500 more for each one after it.
    return 500 * index


# Suppressed vanilla mission cash: the amount build_scm.py strips from each
# mission's pass path, zero where a mission pays nothing (it then mirrors to
# generic filler). These amounts are provisional; scripts/dump_mission_rewards.py
# re-derives the authoritative 1.0 values from a clean decompile before release.
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
    "Four Iron": 500, "Two Bit Hit": 2500, "Demolition Man": 1000,
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
    # Sunshine Autos
    "Sunshine Autos Races": 0,
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

# One-shot consumable effects, each applied once by the ASI past the saved
# applied-index. (item name -> (effect type, *params)); cash carries its amount.
# The wanted-level clear is beneficial, so unlike the chaos traps it never
# defers; it applies the moment the player exists, like every other consumable.
CONSUMABLE_EFFECTS: dict[str, tuple] = {
    **{cash_item_name(amount): ("cash", amount) for amount in CASH_VALUES},
    PACKAGE_CASH_REWARD: ("cash", 100000),
    "Weapon Pickup": ("weapon",),
    "Health Top-up": ("health",),
    "Armor Top-up": ("armor",),
    "Remove Wanted Level": ("clear_wanted",),
}
