"""Weapon shop stock, read out of the stock main.scm decompile.

Six threads sell weapons: three Ammu-Nations (AMMU1, AMMU2, AMMU3) and three
tool stores (HARD1, HARD2, HARD3). Each creates its stock as world OBJECTS with
`create_object`, holds them in its own script globals, and sells each one with
the same four steps: a stand-near test, an affordability test, a grant, and a
charge. None of it is pickups, so none of it is in pickup_data.py.

Every number here is the script's own. The prices are hard coded per site and
are NOT the engine's CostOfWeapon table, which prices pickups: the table charges
250 for weapon type 17 where AMMU1 and AMMU2 charge 100. The model names come
from the game's IDE files and the districts from the nearest hand-audited
location, since a district is never derived from coordinates.

Each row is one thing a player can buy:
(thread, script global, model, model name, display name, weapon type, ammo,
price, x, y, z). A weapon type of -1 is the body armour every Ammu-Nation
sells, which grants through add_armour_to_player rather than a weapon and so
has no weapon type of its own.
"""

from __future__ import annotations

from typing import NamedTuple


class ShopItem(NamedTuple):
    thread: str
    script_global: int
    model: int
    model_name: str
    display_name: str
    weapon_type: int
    ammo: int
    price: int
    x: float
    y: float
    z: float


# The district each thread stands in, and what the shop is called. Two shops
# share Vice Point, one of each kind, so the shop name is what separates them.
# The tool stores carry their own signs rather than a class name: the game calls
# them Bunch of Tools, Tooled Up and Screw This, and the store-robbery table
# already names the last two.
SHOP_DISTRICTS: dict[str, str] = {
    "AMMU1": "Ocean Beach",
    "AMMU2": "Vice Point",
    "AMMU3": "Downtown",
    "HARD1": "Washington Beach",
    "HARD2": "Vice Point",
    "HARD3": "Little Havana",
}

SHOP_NAMES: dict[str, str] = {
    "AMMU1": "Ammu-Nation",
    "AMMU2": "Ammu-Nation",
    "AMMU3": "Ammu-Nation",
    "HARD1": "Bunch of Tools",
    "HARD2": "Tooled Up",
    "HARD3": "Screw This",
}

# The armour rows carry this instead of a weapon type, since they grant armour.
ARMOUR_WEAPON_TYPE = -1

# The one item whose shop stands on the starting island but whose STOCK does not
# arrive with it. Vanilla stocks the Vice Point sniper off flag $847, the same
# flag the mainland crossing sets, so under this mod it cannot be bought until
# the mainland opens. Keyed by thread and object handle, the way every other
# shop table is.
CROSSING_STOCKED_ITEMS = frozenset({("AMMU2", 892)})

# What a shop racks only once a mission has passed, keyed the same way. Each
# shop thread guards the item's price with a vanilla flag and prints the
# out-of-stock line instead while the flag is zero, so the item stands on the
# wall and cannot be bought; the mission that sets the flag is the gate. Read
# out of the stock decompile rather than off a wiki, which is what settles the
# three the hand audit adds and the script does not have: the Downtown body
# armour and both Little Havana items are ungated there, so they are absent
# here.
#
# The Vice Point sniper is NOT here. Its flag is $847, the one the mainland
# crossing sets, so under this mod its stock arrives with the crossing and not
# with the mission that flips $847 in vanilla; CROSSING_STOCKED_ITEMS above is
# what carries it.
SHOP_STOCK_MISSIONS: dict[tuple[str, int], str] = {
    ("AMMU1", 891): "Mall Shootout",       # $902
    ("AMMU1", 892): "Guardian Angels",     # $903
    ("AMMU1", 893): "Jury Fury",           # $867
    ("AMMU2", 891): "The Chase",           # $868
    ("AMMU2", 895): "Jury Fury",           # $867
    ("AMMU3", 889): "Rub Out",             # $907
    ("AMMU3", 890): "Rub Out",             # $906
    ("AMMU3", 891): "Bar Brawl",           # $848
    ("AMMU3", 892): "Rub Out",             # $855
    ("AMMU3", 893): "Shakedown",           # $856
    ("HARD1", 878): "Riot",                # $904
    ("HARD1", 879): "Treacherous Swine",   # $905
    ("HARD2", 879): "The Chase",           # $874
}

SHOP_ITEMS: list[ShopItem] = [
    # Ocean Beach Ammu-Nation.
    ShopItem("AMMU1", 889, 274, "colt45", "Pistol", 17, 9999, 100, -60.8, -1488.1, 12.2),
    ShopItem("AMMU1", 890, 283, "ingramsl", "Mac 10", 24, 9999, 300, -62.3, -1488.2, 12.2),
    ShopItem("AMMU1", 891, 277, "chromegun", "Shotgun", 19, 9999, 500, -64.0, -1488.2, 12.2),
    ShopItem("AMMU1", 892, 276, "ruger", "Kruger", 27, 9999, 1000, -65.4, -1488.2, 12.2),
    ShopItem("AMMU1", 893, 368, "bodyarmour", "Body Armour",
             ARMOUR_WEAPON_TYPE, 200, 200, -66.6, -1488.0, 12.1),
    # Vice Point Ammu-Nation, inside North Point Mall.
    ShopItem("AMMU2", 889, 274, "colt45", "Pistol", 17, 9999, 100, 367.0, 1049.5, 21.1),
    ShopItem("AMMU2", 890, 282, "uzi", "Uzi", 23, 9999, 400, 366.0, 1049.5, 21.1),
    ShopItem("AMMU2", 891, 279, "buddyshot", "Stubby Shotgun", 21, 9999, 600, 364.9, 1049.5, 21.1),
    ShopItem("AMMU2", 892, 285, "sniper", "Sniper Rifle", 28, 9999, 1500, 363.9, 1049.5, 21.1),
    ShopItem("AMMU2", 893, 270, "grenade", "Grenades", 12, 9999, 300, 363.1, 1049.5, 20.8),
    ShopItem("AMMU2", 895, 368, "bodyarmour", "Body Armour",
             ARMOUR_WEAPON_TYPE, 200, 200, 362.1, 1049.5, 20.9),
    # Downtown Ammu-Nation, the expensive one.
    ShopItem("AMMU3", 889, 275, "python", ".357", 18, 9999, 2000, -683.6, 1200.5, 12.9),
    ShopItem("AMMU3", 890, 284, "mp5lng", "MP", 25, 9999, 3000, -683.6, 1202.0, 12.9),
    ShopItem("AMMU3", 891, 278, "shotgspa", "S.P.A.S. 12", 20, 9999, 4000, -683.6, 1203.4, 12.9),
    ShopItem("AMMU3", 892, 280, "m4", "M4", 26, 9999, 5000, -683.6, 1205.0, 12.9),
    ShopItem("AMMU3", 893, 286, "laser", ".308 Sniper", 29, 9999, 6000, -683.6, 1206.5, 12.8),
    ShopItem("AMMU3", 894, 368, "bodyarmour", "Body Armour",
             ARMOUR_WEAPON_TYPE, 200, 200, -683.5, 1208.2, 12.8),
    # Washington Beach tool store.
    ShopItem("HARD1", 875, 260, "screwdriver", "Screwdriver", 2, 0, 10, 201.5, -469.3, 13.8),
    ShopItem("HARD1", 876, 265, "hammer", "Hammer", 7, 0, 20, 202.5, -469.3, 13.7),
    ShopItem("HARD1", 877, 266, "cleaver", "Meat Cleaver", 8, 0, 50, 203.5, -469.3, 13.8),
    ShopItem("HARD1", 878, 264, "bat", "Baseball Bat", 6, 0, 80, 204.6, -469.3, 13.9),
    ShopItem("HARD1", 879, 267, "machete", "Machete", 9, 0, 100, 205.9, -469.3, 14.0),
    # Vice Point tool store, in the same mall as the Ammu-Nation.
    ShopItem("HARD2", 875, 260, "screwdriver", "Screwdriver", 2, 0, 10, 366.0, 1072.8, 20.7),
    ShopItem("HARD2", 876, 265, "hammer", "Hammer", 7, 0, 20, 365.0, 1072.8, 20.7),
    ShopItem("HARD2", 877, 266, "cleaver", "Meat Cleaver", 8, 0, 50, 364.0, 1072.8, 20.7),
    ShopItem("HARD2", 878, 263, "knifecur", "Knife", 5, 0, 90, 362.9, 1072.8, 20.6),
    ShopItem("HARD2", 879, 268, "katana", "Katana", 10, 0, 300, 362.0, 1072.8, 20.8),
    # Little Havana tool store.
    ShopItem("HARD3", 875, 260, "screwdriver", "Screwdriver", 2, 0, 10, -961.0, -689.9, 14.1),
    ShopItem("HARD3", 876, 265, "hammer", "Hammer", 7, 0, 20, -961.0, -690.9, 14.0),
    ShopItem("HARD3", 877, 266, "cleaver", "Meat Cleaver", 8, 0, 50, -961.0, -691.9, 14.1),
    ShopItem("HARD3", 878, 267, "machete", "Machete", 9, 0, 100, -960.8, -693.0, 14.1),
    ShopItem("HARD3", 879, 269, "chnsaw", "Chainsaw", 11, 0, 500, -960.8, -694.0, 14.2),
]


def shop_item_name(item: ShopItem) -> str:
    """The AP location name for one thing a shop sells."""
    return (f"Shop - {SHOP_DISTRICTS[item.thread]} - {SHOP_NAMES[item.thread]} - "
            f"{item.display_name}")


SHOP_ITEM_NAMES: list[str] = [shop_item_name(item) for item in SHOP_ITEMS]
