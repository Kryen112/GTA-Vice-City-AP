"""Region graph and entry rules.

Three regions plus Menu. Menu reaches the start island (east) freely; the
mainland (west island) needs Mainland Access, the AP stand-in for the single
vanilla bridge flip that Phnom Penh '86 performs; Starfish Island needs
Starfish Island Access, the AP stand-in for the island's gates (see data.py).
Neither area item implies the other: the island's east gate opens on Starfish
Island Access alone and its west gate only with both items, so with Mainland
Access alone both island gates stay shut.
"""

from __future__ import annotations

from collections.abc import Callable

from BaseClasses import CollectionState

from . import data

REGION_NAMES: list[str] = [
    data.REGION_VICE_CITY, data.REGION_MAINLAND, data.REGION_STARFISH,
]

START_REGION: str = data.REGION_VICE_CITY

RulePredicate = Callable[[CollectionState, int], bool]


def _has(item: str) -> RulePredicate:
    return lambda state, player: state.has(item, player)


# Entry rule for each non-start region. A region absent from this map is
# reached from the start region with no requirement.
REGION_ENTRY_RULES: dict[str, RulePredicate] = {
    data.REGION_MAINLAND: _has(data.AREA_ITEM_BY_REGION[data.REGION_MAINLAND]),
    data.REGION_STARFISH: _has(data.AREA_ITEM_BY_REGION[data.REGION_STARFISH]),
}
