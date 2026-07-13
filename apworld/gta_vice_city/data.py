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

AREA_ITEMS: list[str] = ["Mainland Access"]

FILLER_ITEMS: list[str] = ["Cash Bundle", "Ammo Top-up"]


def progressive_item_name(giver: str) -> str:
    return f"Progressive {giver}"


def progressive_item_count(giver: str) -> int:
    # The sphere-0 giver's first mission is free, so it needs one fewer unlock.
    missions = len(STORY_GIVERS[giver])
    return missions - 1 if giver == SPHERE_ZERO_GIVER else missions


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


# Region model, pinned from the SCM. The vanilla map has one persistent
# island barrier: three bridge roadblocks (NT_ROADBLOCKCI, NT_ROADBLOCKGF,
# WSH_ROADBLOCK) that all delete together, and the flag $847 that all set,
# when Phnom Penh '86 (Diaz's second mission) passes. That single flip opens
# the whole west island (the mainland). The AP item Mainland Access stands in
# for that flip. There is NO second persistent area: the Leaf Links golf gate
# opens inside the Four Iron mission script itself, so Leaf Links is not a
# roamable gated area and Four Iron is a start-island check.
REGION_VICE_CITY = "Vice City"
REGION_MAINLAND = "Mainland"

# Givers whose whole strand sits on the mainland (west island). Which exact
# missions touch the mainland is audited per giver in Phase 3; this is the
# default giver-level assignment behind the one confirmed barrier.
MAINLAND_GIVERS: frozenset[str] = frozenset({
    "Counterfeit", "Big Mitch Baker", "Umberto Robina", "Auntie Poulet",
    "Kaufman Cabs", "Vercetti Finale",
})


def mission_region(giver: str, mission: str) -> str:
    if giver in MAINLAND_GIVERS:
        return REGION_MAINLAND
    return REGION_VICE_CITY
