"""Which district each piece of lockable world content sits in.

Generated from the hand audit of every location, which is the authority: it
corrects the districts the older names guessed from coordinates, and it is the
only source that settles the boundary cases. The game's own zone rectangles were
tested against it and cannot reproduce it, so they are not used here.

Every table is keyed by INDEX, not by location name, because the location rename
that carries these districts into the names is a separate later change and an
index-keyed table survives it untouched. Index i is content i of that class, the
same order the world's own name lists use.

Property districts are derived instead of audited, from the coordinates the
script loads before creating each property icon.
"""

from __future__ import annotations

# Districts in a fixed order: item ids follow it, so it never reorders. Ordered
# the way a player crosses the map, the start island first and then the mainland.
# The Junk Yard is the one district holding nothing lockable: two ambient pickups
# and no package, rampage, jump, store or property. It is here because a pickup
# name says it, and a name has to name a district the tables know.

DISTRICTS: list[str] = [
    "Ocean Beach",
    "Washington Beach",
    "Vice Point",
    "Starfish Island",
    "Prawn Island",
    "Leaf Links",
    "Downtown",
    "Little Haiti",
    "Junk Yard",
    "Little Havana",
    "Viceport",
    "Escobar International",
]

# The 100 hidden packages, in placement order.
PACKAGE_DISTRICTS: list[str] = [
    "Ocean Beach", "Washington Beach", "Ocean Beach",
    "Viceport", "Ocean Beach", "Ocean Beach",
    "Ocean Beach", "Washington Beach", "Washington Beach",
    "Washington Beach", "Washington Beach", "Washington Beach",
    "Vice Point", "Vice Point", "Vice Point",
    "Vice Point", "Vice Point", "Vice Point",
    "Vice Point", "Vice Point", "Washington Beach",
    "Vice Point", "Vice Point", "Vice Point",
    "Vice Point", "Vice Point", "Washington Beach",
    "Washington Beach", "Vice Point", "Vice Point",
    "Ocean Beach", "Ocean Beach", "Washington Beach",
    "Washington Beach", "Vice Point", "Vice Point",
    "Vice Point", "Vice Point", "Vice Point",
    "Vice Point", "Prawn Island", "Prawn Island",
    "Prawn Island", "Prawn Island", "Prawn Island",
    "Leaf Links", "Leaf Links", "Leaf Links",
    "Leaf Links", "Leaf Links", "Starfish Island",
    "Starfish Island", "Starfish Island", "Starfish Island",
    "Starfish Island", "Downtown", "Downtown",
    "Downtown", "Downtown", "Downtown",
    "Downtown", "Downtown", "Downtown",
    "Little Haiti", "Little Haiti", "Little Haiti",
    "Little Haiti", "Little Haiti", "Little Haiti",
    "Little Haiti", "Little Haiti", "Little Havana",
    "Little Havana", "Little Havana", "Little Havana",
    "Little Havana", "Little Havana", "Little Havana",
    "Viceport", "Viceport", "Viceport",
    "Viceport", "Viceport", "Viceport",
    "Escobar International", "Escobar International", "Escobar International",
    "Viceport", "Escobar International", "Escobar International",
    "Escobar International", "Escobar International", "Escobar International",
    "Escobar International", "Escobar International", "Escobar International",
    "Escobar International", "Escobar International", "Viceport",
    "Escobar International",
]

# The 35 rampages, in RAMPAGE_NAMES order.
RAMPAGE_DISTRICTS: list[str] = [
    "Ocean Beach", "Escobar International", "Vice Point",
    "Vice Point", "Vice Point", "Washington Beach",
    "Downtown", "Downtown", "Downtown",
    "Downtown", "Little Haiti", "Ocean Beach",
    "Ocean Beach", "Starfish Island", "Little Havana",
    "Viceport", "Escobar International", "Viceport",
    "Little Havana", "Ocean Beach", "Ocean Beach",
    "Vice Point", "Vice Point", "Vice Point",
    "Viceport", "Downtown", "Downtown",
    "Little Havana", "Vice Point", "Ocean Beach",
    "Vice Point", "Little Havana", "Escobar International",
    "Ocean Beach", "Little Havana",
]

# The 36 unique stunt jumps, by the id the USJ thread writes to $792.
STUNT_JUMP_DISTRICTS: list[str] = [
    "Escobar International", "Escobar International", "Escobar International",
    "Escobar International", "Escobar International", "Escobar International",
    "Escobar International", "Escobar International", "Prawn Island",
    "Vice Point", "Downtown", "Downtown",
    "Downtown", "Downtown", "Little Haiti",
    "Little Haiti", "Little Haiti", "Little Havana",
    "Ocean Beach", "Ocean Beach", "Washington Beach",
    "Ocean Beach", "Ocean Beach", "Ocean Beach",
    "Ocean Beach", "Ocean Beach", "Ocean Beach",
    "Ocean Beach", "Vice Point", "Washington Beach",
    "Washington Beach", "Washington Beach", "Washington Beach",
    "Washington Beach", "Washington Beach", "Starfish Island",
]

# The 15 robbable stores, in add_stores_knocked_off order. The four inside
# North Point Mall are Vice Point: the mall is a building, not a district,
# and it stays in the location name as a hint instead.
STORE_DISTRICTS: list[str] = [
    "Washington Beach", "Vice Point", "Little Havana",
    "Little Havana", "Downtown", "Downtown",
    "Little Haiti", "Vice Point", "Vice Point",
    "Vice Point", "Vice Point", "Vice Point",
    "Vice Point", "Little Havana", "Little Havana",
]

# Places a location name may say instead of its district. A name is written for
# a player looking for the thing, so it can name a landmark inside a district
# where that is the better direction; the district is what an item releases.
# North Point Mall is the only one: four stores sit inside it, and telling a
# player "the mall" beats telling them "Vice Point".
NAME_DISTRICT_FOLDS: dict[str, str] = {
    "North Point Mall": "Vice Point",
}

# The 15 purchasable properties, keyed by the property name rather than by
# index, since that name is what the purchase and ownership items are built
# from and it does not move in the rename.
PROPERTY_DISTRICTS: dict[str, str] = {
    "Printworks": "Little Havana",
    "Sunshine Autos": "Little Havana",
    "Film Studio": "Prawn Island",
    "Cherry Popper": "Little Havana",
    "Kaufman Cabs": "Little Haiti",
    "Malibu Club": "Vice Point",
    "Boatyard": "Viceport",
    "Pole Position": "Ocean Beach",
    "El Swanko Casa": "Vice Point",
    "Links View Apartment": "Vice Point",
    "Hyman Condo": "Downtown",
    "Ocean Heights Apartment": "Ocean Beach",
    "1102 Washington Street": "Washington Beach",
    "3321 Vice Point": "Vice Point",
    "Skumole Shack": "Downtown",
}

# Where each held pickup stands, so the ASI can put a pool entry it found by
# type or model into a district. The district tables above are keyed by index,
# and the pool is not, so these are the join. Hidden packages are absent on
# purpose: package_data.py already owns their hundred positions in the same
# order, and re-emitting them would make two tables to keep in step.
#
# Rampages come from the #KILLFRENZY pickup creations in the RAMPAGE controller,
# in creation order, which is the flag order and so the check order. Properties
# come from the three globals the script loads each icon's position into before
# creating it there.
RAMPAGE_COORDS: list[tuple[float, float, float]] = [
    (218.22, -1613.76, 11.06),
    (-1435.29, -833.645, 30.0599),
    (234.86, 34.22, 9.98),
    (479.69, 1110.1801, 17.33),
    (370.63, 1125.86, 26.5),
    (144.449, -545.234, 14.751),
    (-1100.625, 1453.4301, 8.73),
    (-908.317, 744.149, 11.092),
    (-508.768, 1149.203, 18.172),
    (-789.41, 592.56, 11.1),
    (-1011.37, -170.64, 10.99),
    (68.702, -1119.231, 10.458),
    (85.623, -1259.86, 17.092),
    (-679.66, -419.712, 10.469),
    (-1176.3409, -702.975, 22.662),
    (-626.642, -1354.85, 16.373),
    (-1519.33, -292.236, 14.86),
    (-956.113, -1206.33, 14.86),
    (-890.184, -489.655, 36.2),
    (3.426, -1147.0, 10.45),
    (468.656, -1608.79, 11.03),
    (587.795, 1206.26, 15.64),
    (300.673, 1324.88, 22.919),
    (217.247, 261.372, 8.71),
    (-366.44, -1742.1, 11.426),
    (-448.796, 1249.27, 11.75),
    (-674.22, 1162.7, 28.15),
    (-1143.48, -410.87, 10.95),
    (624.26, -230.158, 23.915),
    (-34.13, -948.707, 21.772),
    (593.315, -352.826, 13.711),
    (-1234.83, -90.378, 11.43),
    (-1483.47, -881.677, 14.87),
    (-194.701, -1085.067, 15.66),
    (-983.373, -353.997, 13.84),
]

PROPERTY_COORDS: dict[str, tuple[float, float, float]] = {
    "Printworks": (-1059.6, -274.5, 11.4),
    "Sunshine Autos": (-1007.3, -869.9, 12.8),
    "Film Studio": (15.2, 962.6, 10.9),
    "Cherry Popper": (-864.3, -576.6, 11.0),
    "Kaufman Cabs": (-1011.7, 203.9, 11.2),
    "Malibu Club": (487.2, -81.5, 11.4),
    "Boatyard": (-685.8, -1495.6, 12.5),
    "Pole Position": (99.5, -1468.5, 9.9),
    "El Swanko Casa": (428.4, 605.9, 12.2),
    "Links View Apartment": (304.5, 376.3, 12.7),
    "Hyman Condo": (-834.8, 1306.9, 11.0),
    "Ocean Heights Apartment": (14.0, -1500.7, 12.7),
    "1102 Washington Street": (88.5, -804.7, 11.2),
    "3321 Vice Point": (531.4, 1273.7, 17.6),
    "Skumole Shack": (-560.1, 703.6, 20.5),
}

# The 116 ambient pickup slots, in pickup_data.PICKUP_SLOTS order.
#
# AUDITED. These were derived once, each slot taking the district of its three
# nearest audited anchors weighted by inverse horizontal distance, which agreed
# with the anchors leave-one-out 90.4 per cent of the time. The hand audit has
# since walked all 110 and named each one, and it moved four, every one of them
# between mainland districts: two into the Junk Yard, which nothing else in the
# world is in. So the derivation missed by four rather than by the eight it
# expected to, and it is gone; this table is the audit's answer and
# pickup_data.PICKUP_NAMES says the same district for each slot.
#
# A test pins every slot to the island of its nearest anchor, so a later
# correction can move a district within a region but not between regions
# without saying so. That test measures nearest in three dimensions, which is a
# deliberately blunt metric: it only has to separate islands, which sit far
# enough apart that the vertical term cannot move a slot across the gap.
PICKUP_DISTRICTS: list[str] = [
    "Vice Point",  # 0
    "Ocean Beach",  # 1
    "Washington Beach",  # 2
    "Vice Point",  # 3
    "Vice Point",  # 4
    "Vice Point",  # 5
    "Prawn Island",  # 6
    "Downtown",  # 7
    "Little Haiti",  # 8
    "Little Haiti",  # 9
    "Little Haiti",  # 10
    "Little Havana",  # 11
    "Little Havana",  # 12
    "Ocean Beach",  # 13
    "Ocean Beach",  # 14
    "Ocean Beach",  # 15
    "Vice Point",  # 16
    "Ocean Beach",  # 17
    "Washington Beach",  # 18
    "Vice Point",  # 19
    "Washington Beach",  # 20
    "Vice Point",  # 21
    "Vice Point",  # 22
    "Vice Point",  # 23
    "Washington Beach",  # 24
    "Ocean Beach",  # 25
    "Ocean Beach",  # 26
    "Washington Beach",  # 27
    "Ocean Beach",  # 28
    "Washington Beach",  # 29
    "Vice Point",  # 30
    "Prawn Island",  # 31
    "Prawn Island",  # 32
    "Leaf Links",  # 33
    "Starfish Island",  # 34
    "Starfish Island",  # 35
    "Starfish Island",  # 36
    "Downtown",  # 37
    "Downtown",  # 38
    "Little Haiti",  # 39
    "Little Havana",  # 40
    "Viceport",  # 41
    "Viceport",  # 42
    "Viceport",  # 43
    "Viceport",  # 44
    "Escobar International",  # 45
    "Escobar International",  # 46
    "Little Havana",  # 47
    "Little Haiti",  # 48
    "Junk Yard",  # 49
    "Little Havana",  # 50
    "Ocean Beach",  # 51
    "Ocean Beach",  # 52
    "Washington Beach",  # 53
    "Vice Point",  # 54
    "Vice Point",  # 55
    "Vice Point",  # 56
    "Vice Point",  # 57
    "Prawn Island",  # 58
    "Leaf Links",  # 59
    "Starfish Island",  # 60
    "Starfish Island",  # 61
    "Starfish Island",  # 62
    "Downtown",  # 63
    "Downtown",  # 64
    "Downtown",  # 65
    "Little Haiti",  # 66
    "Junk Yard",  # 67
    "Little Havana",  # 68
    "Little Havana",  # 69
    "Viceport",  # 70
    "Viceport",  # 71
    "Escobar International",  # 72
    "Downtown",  # 73
    "Little Haiti",  # 74
    "Downtown",  # 75
    "Ocean Beach",  # 76
    "Washington Beach",  # 77
    "Washington Beach",  # 78
    "Vice Point",  # 79
    "Vice Point",  # 80
    "Vice Point",  # 81
    "Vice Point",  # 82
    "Vice Point",  # 83
    "Prawn Island",  # 84
    "Leaf Links",  # 85
    "Escobar International",  # 86
    "Downtown",  # 87
    "Downtown",  # 88
    "Little Haiti",  # 89
    "Downtown",  # 90
    "Viceport",  # 91
    "Escobar International",  # 92
    "Little Havana",  # 93
    "Ocean Beach",  # 94
    "Washington Beach",  # 95
    "Vice Point",  # 96
    "Vice Point",  # 97
    "Vice Point",  # 98
    "Vice Point",  # 99
    "Starfish Island",  # 100
    "Starfish Island",  # 101
    "Downtown",  # 102
    "Downtown",  # 103
    "Little Haiti",  # 104
    "Little Haiti",  # 105
    "Little Havana",  # 106
    "Little Haiti",  # 107
    "Little Haiti",  # 108
    "Downtown",  # 109
    # The six a mission places and never takes away: the four Rub Out
    # leaves in the estate courtyard, the knife The Job leaves outside the
    # Malibu Club, and the minigun Trojan Voodoo leaves on the drugs
    # factory. Each takes the district the audit already gave the
    # locations around it.
    "Starfish Island",  # 110
    "Starfish Island",  # 111
    "Starfish Island",  # 112
    "Starfish Island",  # 113
    "Vice Point",  # 114
    "Little Haiti",  # 115
]
