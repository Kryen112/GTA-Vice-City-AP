"""Minimap positions for non-mission checks.

Store, side-event and jump coordinates come from the project's PopTracker
coordinate table: https://github.com/Kryen112/GTAVC_AP_Poptracker/blob/main/data/check_coords.py
The other positions use the world's existing placement tables.
"""

from . import data, district_data, locations, scm, shop_data

STORE_COORDS: list[tuple[float, float, float]] = [
    (202.7, -474.1, 10.1),
    (384.04999999999995, 1063.5, 23.05),
    (-967.5, -693.2, 10.3),
    (-859.2, -632.7, 10.6),
    (-854.3, 850.0, 10.6),
    (-830.4, 741.9, 10.6),
    (-846.6, -72.6, 10.8),
    (379.9, 210.2, 10.6),
    (383.2, 759.7, 11.0),
    (449.7, 781.5, 12.2),
    (352.7, 1111.3, 24.5),
    (423.5, 1039.4, 18.1),
    (468.7, 1206.6, 18.2),
    (-1167.5, -613.5, 11.0),
    (-1192.2, -323.7, 11.1),
]

SIDE_EVENT_COORDS: dict[str, tuple[float, float, float]] = {
    "Bloodring": (-1110.3314, 1331.0956, 20.1119),
    "Cone Crazy": (127.5, -1157.5, 30.0),
    "Dirtring": (-1110.3314, 1331.0956, 20.1119),
    "Downtown Chopper Checkpoint": (-569.1451, 851.0923, 22.8402),
    "Hotring": (-1110.3314, 1331.0956, 20.1119),
    "Little Haiti Chopper Checkpoint": (-886.5938, 236.5693, 13.9773),
    "Ocean Beach Chopper Checkpoint": (28.4463, -1311.7614, 16.4712),
    "PCJ Playground": (507.4, -308.8, 13.0),
    "RC Bandit Race": (718.465, 701.3998, 0.0),
    "RC Baron Race": (307.917, 1254.6219, 27.595),
    "RC Raider Pickup": (-1235.1, -1235.7, 0.0),
    "Test Track": (-425.0, 1410.0, 10.5),
    "Trial by Dirt": (-425.0, 1410.0, 10.5),
    "Vice Point Chopper Checkpoint": (375.845, 332.9194, 11.5155),
}

STUNT_JUMP_COORDS: list[tuple[float, float, float]] = [
    (-1492.2, -1011.7, 0.0),
    (-1332.0, -738.3, 0.0),
    (-1210.9, -910.2, 0.0),
    (-1238.3, -1039.1, 0.0),
    (-1550.8, -1035.2, 0.0),
    (-1597.7, -1269.5, 0.0),
    (-1543.0, -1218.8, 0.0),
    (-1335.9, -972.7, 0.0),
    (46.9, 910.2, 0.0),
    (296.9, -238.3, 0.0),
    (-668.0, 1156.2, 0.0),
    (-523.4, 847.7, 0.0),
    (-300.8, 1113.3, 0.0),
    (-832.0, 1148.4, 0.0),
    (-1007.8, -35.2, 0.0),
    (-945.3, -117.2, 0.0),
    (-896.5, 293.0, 0.0),
    (-1027.3, -562.5, 0.0),
    (195.3, -972.7, 0.0),
    (31.2, -957.0, 0.0),
    (421.9, -320.3, 0.0),
    (105.5, -1226.6, 0.0),
    (15.6, -1234.4, 0.0),
    (15.6, -1320.3, 0.0),
    (-318.4, -1371.1, 0.0),
    (-318.4, -1265.6, 0.0),
    (214.8, -1156.2, 0.0),
    (250.0, -945.3, 0.0),
    (441.4, -128.9, 0.0),
    (285.2, -503.9, 0.0),
    (367.2, -714.8, 0.0),
    (453.1, -511.7, 0.0),
    (464.8, -527.3, 0.0),
    (460.9, -382.8, 0.0),
    (250.0, -488.3, 0.0),
    (-355.5, -293.0, 0.0),
]


CATEGORY_COLORS = {
    "hidden_packages": 1, "robbable_stores": 2, "rampages": 3, "pickups": 4,
    "stunt_jumps": 5, "properties": 6, "side_events": 7, "shops": 8,
}


def check_markers(enabled_options: dict) -> dict[str, list[float]]:
    """Completion global -> [x, y, category, optional content gate], for enabled classes."""
    coordinates = {}
    for class_key, positions in (
        ("hidden_packages", data.PACKAGE_COORDS),
        ("rampages", district_data.RAMPAGE_COORDS),
        ("stunt_jumps", STUNT_JUMP_COORDS),
        ("robbable_stores", STORE_COORDS),
        ("pickups", data.PICKUP_SLOTS),
    ):
        names = locations.OPTIONAL_CLASSES[class_key][1]
        coordinates.update(zip(names, positions, strict=True))
    coordinates.update(SIDE_EVENT_COORDS)
    coordinates.update({f"{name} Purchase": position
                        for name, position in district_data.PROPERTY_COORDS.items()})
    coordinates.update({shop_data.shop_item_name(item): (item.x, item.y)
                        for item in shop_data.SHOP_ITEMS})
    return {
        str(scm.completion_global(name)): [*position[:2], CATEGORY_COLORS[locations.LOCATION_CLASS[name]]]
        + ([scm.district_unlock_global(data.LOCATION_CONTENT_CLASS[name], data.location_district(name))]
           if name in data.LOCATION_CONTENT_CLASS else [])
        for name, position in coordinates.items()
        if enabled_options.get(locations.LOCATION_TOGGLE[name], False)
    }
