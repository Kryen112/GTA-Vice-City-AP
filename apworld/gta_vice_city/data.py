"""Content tables for GTA: Vice City, hand-written from the SCM decompile.

This is plain owned data, not a generated format. Mission names and their
per-giver order come from the vanilla main.scm DEFINE MISSION table. Giver
grouping and the region (island) assignment below are provisional first
readings; the cross-giver edges and island barriers are pinned from the SCM
in a dedicated extraction pass and refined in per-giver Phase 3 audits.
Nothing here gates logic on money.
"""

from __future__ import annotations

from . import package_data, pickup_data

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

# Ability requirements per mission, the minimal day-one set: only missions
# whose script demonstrably forces the vehicle (a race or delivery in a
# specific vehicle the player enters). Everything subtler is deliberately
# absent and comes from the pre-release manual runthrough; a term only takes
# effect while its ability_locks key is selected.
MISSION_ABILITY_REQUIREMENTS: dict[str, list[str]] = {
    "The Driver": [LAND_VEHICLES_ITEM],
    "Demolition Man": [LAND_VEHICLES_ITEM],
    "G-spotlight": [LAND_VEHICLES_ITEM],
    "Sunshine Autos Import List 1": [LAND_VEHICLES_ITEM],
    "Sunshine Autos Import List 2": [LAND_VEHICLES_ITEM],
    "Sunshine Autos Import List 3": [LAND_VEHICLES_ITEM],
    "Sunshine Autos Import List 4": [LAND_VEHICLES_ITEM],
    "The Fastest Boat": [SEA_VEHICLES_ITEM],
    "Supply & Demand": [SEA_VEHICLES_ITEM],
    "Stunt Boat Challenge": [SEA_VEHICLES_ITEM],
    "Checkpoint Charlie": [SEA_VEHICLES_ITEM],
    "Dildo Dodo": [AIR_VEHICLES_ITEM],
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

# Side events that need no vehicle of the player's own: the launcher takes
# the player on foot and the mission warps them into the event vehicle
# (warp_player_into_car), which no lock constrains. Dirtring is absent
# because its script sets the player down beside a created Sanchez and the
# player mounts it, a real entry. Every other side event's launcher requires
# the player to already be in a specific vehicle: the RC trio in a Top Fun
# van and the four trials in their own model.
SEATED_SIDE_EVENTS: frozenset[str] = frozenset({"Hotring", "Bloodring"})


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
# types mirror the cheat each imitates: wanted level
# like YOUWONTTAKEMEALIVE, exploding cars like BIGBANG, hostile peds like
# NOBODYLIKESME, stormy weather like CATSANDDOGS, foggy weather like
# CANTSEEATHING, speed up like ONSPEED, and slow down like BOOOOOORING. Drunk
# vision has no cheat: it imitates the Boomshine Saigon drunk drive. Unlike the
# cheats, which pin the forced weather until a script changes it, a weather trap
# releases immediately after forcing, so the game's own hourly weather cycle
# resumes and blends the trap weather away naturally.
TRAP_DURATION_SECONDS = 30
TRAP_WANTED_STARS = 3

# Engine weather ids (eWeather) the weather traps carry as their param.
WEATHER_RAINY = 2
WEATHER_FOGGY = 3

TRAP_EFFECTS: dict[str, tuple] = {
    "Wanted Level Trap": ("trap_wanted", TRAP_WANTED_STARS),
    "Exploding Cars Trap": ("trap_explode_cars",),
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
            + [mission for missions in VENUE_STRANDS.values() for mission in missions]
            + [
                activity
                for activities in VENUE_ACTIVITIES.values()
                for activity in activities
            ],
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
# protection strand. The finale's vanilla asset prerequisite has its own
# encoding, the FINALE tables below.
STRAND_PREREQUISITES: dict[str, list[tuple[str, int]]] = {
    "Vercetti Finale": [("Vercetti Protection", 3)],
}

# Cross-giver edges that gate a single mission rather than a whole strand. Rub
# Out (Diaz's last) needs Lance rescued in Death Row first.
MISSION_PREREQUISITES: dict[str, list[tuple[str, int]]] = {
    "Rub Out": [("Death Row", 1)],
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

# Regions a mission needs beyond its own. Keep Your Friends Close... sits on
# Starfish, but its launcher only activates once Cap the Collector passes, and
# that mission is on the mainland, so the finale also needs the mainland. Named
# by region rather than by item, so the crossing split reaches it too.
MISSION_REGION_REQUIREMENTS: dict[str, list[str]] = {
    "Keep Your Friends Close...": [REGION_MAINLAND],
}


def region_access_groups(region: str,
                         split_mainland_access: bool) -> list[list[str]]:
    """The alternative item sets that reach a region, any one of them enough.

    Every region but the mainland has one way in, so its area item is the only
    group. With the crossings split, the mainland has one group per crossing
    instead of the single Mainland Access group. A region needing nothing (the
    start island) has no groups at all.
    """
    if region == REGION_MAINLAND and split_mainland_access:
        return [[crossing, *also] for crossing, also in MAINLAND_CROSSINGS.items()]
    area_item = AREA_ITEM_BY_REGION.get(region)
    return [] if area_item is None else [[area_item]]


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


# Rampages on the mainland, from the kill-frenzy pickup coordinates in the RAMPAGE
# controller (pickup order equals flag order equals check order). Indices with
# pickup X below the bridge channel (about -480) are mainland; rampages 25
# (X = -366, far south) and 26 (X = -449, far north) sit in the band west of the
# beaches and count as mainland too.
MAINLAND_RAMPAGES: frozenset[str] = frozenset(
    rampage_name(index)
    for index in (2, 7, 8, 9, 10, 11, 15, 16, 17, 18, 19, 25, 26, 27, 28, 32, 33, 35)
)

# Rampages on Starfish Island. Rampage 14's pickup at (-679.7, -419.7) sits on
# the island's west tip, verified against the starisl.ipl map instances; its
# provisional Little Havana district name is wrong and the naming pass renames
# it.
STARFISH_RAMPAGES: frozenset[str] = frozenset({rampage_name(14)})

# Hidden packages are per package, each detected individually by the ASI (by
# coordinate) rather than by a running count. Island membership and coordinates
# come from package_data, in the SCM placement order. PACKAGE_COORDS is sent to
# the ASI via slot_data so it can match a collected pickup to its package.
MAINLAND_PACKAGES: frozenset[str] = package_data.MAINLAND_PACKAGES
STARFISH_PACKAGES: frozenset[str] = package_data.STARFISH_PACKAGES
PACKAGE_COORDS: list[tuple[float, float, float]] = package_data.PACKAGE_COORDS

# Ambient pickup slots for the randomize_pickups permutation, extracted from
# the decompile by scripts/dump_pickups.py: the MAIN-section bribes plus the
# Mission 0 street weapons, hearts, armors, and adrenalines. Each slot keeps
# its position and pickup type; the permutation moves the model and ammo. The
# bribe model breaks the in-shop cost lookup, so bribes never land on
# shop-type slots.
PICKUP_SLOTS: list[tuple[float, float, float, int, int, int]] = pickup_data.PICKUP_SLOTS
PICKUP_MODEL_NAMES: dict[int, str] = pickup_data.PICKUP_MODEL_NAMES
PICKUP_BRIBE_MODEL: int = pickup_data.BRIBE_MODEL
PICKUP_SHOP_TYPE: int = pickup_data.SHOP_PICKUP_TYPE

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

# Stunt jumps are exe-native: the SCM only registers a found jump by its engine
# id, so their per-jump islands are not readable from the decompile. All 36 count
# as mainland provisionally until an in-game audit places each; the audit must
# also confirm none sits on Starfish Island, since mainland gating no longer
# covers the island (with Mainland Access alone both island gates stay shut).
MAINLAND_STUNT_JUMPS: frozenset[str] = frozenset(
    stunt_jump_name(index) for index in range(1, STUNT_JUMP_COUNT + 1)
)


def location_ability_requirements() -> dict[str, list[str]]:
    """Every location's ability items, the minimal day-one set. A term binds
    only while its ability_locks key is selected (rules.py filters); with the
    key off the item is not in the pool and the location plays vanilla.

    Class-wide entries: every unique stunt jump and every emergency level
    takes a land vehicle; a chopper checkpoint takes a helicopter, the two
    warp-seated stadium events take nothing, and every other side event
    starts by entering a land vehicle; robbing a store takes aiming a weapon
    (bare fists cannot); a weapon rampage wields its handed weapon while the
    two run-them-down rampages take a land vehicle; a safehouse purchase
    takes holdable money (a business purchase carries the wallet through the
    property-sale requirements instead); and each Sunshine Autos race is driven
    in the player's own car, since the launcher takes them on foot and the
    mission creates only the opponents.
    """
    requirements: dict[str, list[str]] = {}
    for mission, items in MISSION_ABILITY_REQUIREMENTS.items():
        requirements[mission] = list(items)
    for index in range(1, STUNT_JUMP_COUNT + 1):
        requirements[stunt_jump_name(index)] = [LAND_VEHICLES_ITEM]
    for name in emergency_names():
        requirements[name] = [LAND_VEHICLES_ITEM]
    for name in SIDE_EVENTS:
        if name in SEATED_SIDE_EVENTS:
            continue
        requirements[name] = (
            [AIR_VEHICLES_ITEM] if name in AIR_SIDE_EVENTS else [LAND_VEHICLES_ITEM]
        )
    for index in range(1, ROBBABLE_STORE_COUNT + 1):
        requirements[robbable_store_name(index)] = [WEAPON_EQUIP_ITEM]
    for index in range(1, RAMPAGE_COUNT + 1):
        requirements[rampage_name(index)] = (
            [LAND_VEHICLES_ITEM] if index in VEHICLE_RAMPAGE_INDICES
            else [WEAPON_EQUIP_ITEM]
        )
    for purchase in PROPERTY_PURCHASES:
        if purchase not in BUSINESS_PURCHASES:
            requirements[purchase] = [WALLET_ITEM]
    for name in SUNSHINE_RACES:
        requirements[name] = [LAND_VEHICLES_ITEM]
    return requirements


LOCATION_ABILITY_REQUIREMENTS: dict[str, list[str]] = location_ability_requirements()


def location_content_requirements() -> dict[str, list[str]]:
    """Every location's content-lock item. Unlike an ability term these are
    uniform across a class, since a key holds its whole class: every location
    in the class carries the one item. A term binds only while its
    content_locks key is selected (rules.py filters); with the key off the item
    is not in the pool and the class plays vanilla.

    Every property purchase is listed, but a business purchase never reads its
    entry: rules.py already rules those through the property-sale requirements,
    which the term rides so it reaches venue missions and the finale as well.
    The entry is what carries a safehouse purchase, which has no other rule.
    """
    requirements: dict[str, list[str]] = {}
    for index in range(1, HIDDEN_PACKAGE_COUNT + 1):
        requirements[hidden_package_name(index)] = [HIDDEN_PACKAGES_ITEM]
    for index in range(1, RAMPAGE_COUNT + 1):
        requirements[rampage_name(index)] = [RAMPAGES_ITEM]
    for index in range(1, STUNT_JUMP_COUNT + 1):
        requirements[stunt_jump_name(index)] = [STUNT_JUMPS_ITEM]
    for index in range(1, ROBBABLE_STORE_COUNT + 1):
        requirements[robbable_store_name(index)] = [ROBBABLE_STORES_ITEM]
    for purchase in PROPERTY_PURCHASES:
        requirements[purchase] = [PROPERTY_PURCHASES_ITEM]
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
