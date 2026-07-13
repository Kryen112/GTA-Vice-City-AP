"""Region graph and entry rules.

Two regions plus Menu. Menu reaches the start island (east) freely; the
mainland (west island) needs Mainland Access, the AP stand-in for the single
vanilla bridge flip that Phnom Penh '86 performs (see data.py).
"""

from __future__ import annotations

from collections.abc import Callable

from BaseClasses import CollectionState

from . import data

REGION_NAMES: list[str] = [data.REGION_VICE_CITY, data.REGION_MAINLAND]

START_REGION: str = data.REGION_VICE_CITY

RulePredicate = Callable[[CollectionState, int], bool]


def _has(item: str) -> RulePredicate:
    return lambda state, player: state.has(item, player)


# Entry rule for each non-start region. A region absent from this map is
# reached from the start region with no requirement.
REGION_ENTRY_RULES: dict[str, RulePredicate] = {
    data.REGION_MAINLAND: _has("Mainland Access"),
}
