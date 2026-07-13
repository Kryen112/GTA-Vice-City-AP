"""Content tables for GTA: Vice City, hand-written from the SCM decompile.

This is plain owned data, not a generated format. Mission names and their
per-giver order come from the vanilla main.scm DEFINE MISSION table. Giver
grouping and the region (island) assignment below are provisional first
readings; the exact cross-giver spine edges and island barriers are pinned
from the SCM in a dedicated extraction pass and refined in per-giver Phase 3
audits. Nothing here gates logic on money.
"""

from __future__ import annotations

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
    "Cam": [
        "No Escape?", "The Shootist", "The Driver", "The Job",
    ],
    "Phil Cassidy": [
        "Gun Runner", "Boomshine Saigon",
    ],
    "Film Studio": [
        "Recruitment Drive", "Dildo Dodo", "Martha's Mug Shot", "G-spotlight",
    ],
    "Vercetti Protection": [
        "Shakedown", "Bar Brawl", "Cop Land",
    ],
    "Counterfeit": [
        "Spilling the Beans", "Hit the Courier",
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
    "Kaufman Cabs": [
        "V.I.P.", "Friendly Rivalry", "Cabmaggedon",
    ],
    "Vercetti Finale": [
        "Cap the Collector", "Keep Your Friends Close...",
    ],
}

# The Rosenberg strand opens on a new game with no unlock item (sphere 0).
# Every other giver's first mission needs its first progressive unlock.
SPHERE_ZERO_GIVER = "Rosenberg"

# The default goal mission.
FINAL_MISSION = "Keep Your Friends Close..."

HIDDEN_PACKAGE_COUNT = 100


def hidden_package_name(index: int) -> str:
    return f"Hidden Package {index:03d}"


# Rewards that leave the vanilla hidden-package threshold and enter the pool
# when the hidden-packages class is on. Useful items, never progression.
PACKAGE_REWARD_ITEMS: list[str] = [
    "Body Armor", "Chainsaw", ".357", "Flamethrower", ".308 Sniper",
    "Minigun", "Rocket Launcher", "Sea Sparrow Spawn", "Rhino Spawn",
    "Hunter Spawn", "$100,000",
]

AREA_ITEMS: list[str] = ["Leaf Links Access", "Mainland Access"]

FILLER_ITEMS: list[str] = ["Cash Bundle", "Ammo Top-up"]


def progressive_item_name(giver: str) -> str:
    return f"Progressive {giver}"


def progressive_item_count(giver: str) -> int:
    # The sphere-0 giver's first mission is free, so it needs one fewer unlock.
    missions = len(STORY_GIVERS[giver])
    return missions - 1 if giver == SPHERE_ZERO_GIVER else missions


# Region model. Provisional island assignment: only clearly off-start givers
# sit behind an area barrier. Pinned precisely from the SCM barrier globals
# later.
REGION_VICE_CITY = "Vice City"
REGION_LEAF_LINKS = "Leaf Links"
REGION_MAINLAND = "Mainland"

# Givers whose whole strand sits on the mainland (west island).
MAINLAND_GIVERS: frozenset[str] = frozenset({
    "Counterfeit", "Big Mitch Baker", "Umberto Robina", "Auntie Poulet",
    "Kaufman Cabs", "Vercetti Finale",
})
# Individual missions that sit on their own island regardless of giver.
LEAF_LINKS_MISSIONS: frozenset[str] = frozenset({"Four Iron"})


def mission_region(giver: str, mission: str) -> str:
    if mission in LEAF_LINKS_MISSIONS:
        return REGION_LEAF_LINKS
    if giver in MAINLAND_GIVERS:
        return REGION_MAINLAND
    return REGION_VICE_CITY
