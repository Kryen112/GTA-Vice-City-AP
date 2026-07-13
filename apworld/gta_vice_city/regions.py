"""Region graph and entry rules.

Three regions plus Menu. Menu reaches the start island freely; the other two
islands need their area-access item. Which vanilla globals stage the bridge
openings is pinned from the SCM barrier extraction later; the shape here is
stable.
"""

from __future__ import annotations

from collections.abc import Callable

from BaseClasses import CollectionState

from . import data

REGION_NAMES: list[str] = [
    data.REGION_VICE_CITY, data.REGION_LEAF_LINKS, data.REGION_MAINLAND,
]

START_REGION: str = data.REGION_VICE_CITY

RulePredicate = Callable[[CollectionState, int], bool]


def _has(item: str) -> RulePredicate:
    return lambda state, player: state.has(item, player)


# Entry rule for each non-start region. A region absent from this map is
# reached from the start region with no requirement.
REGION_ENTRY_RULES: dict[str, RulePredicate] = {
    data.REGION_LEAF_LINKS: _has("Leaf Links Access"),
    data.REGION_MAINLAND: _has("Mainland Access"),
}
