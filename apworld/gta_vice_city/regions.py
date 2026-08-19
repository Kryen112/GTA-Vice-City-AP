"""Region graph and entry rules.

Three regions plus Menu. Menu reaches the start island (east) freely; the
mainland (west island) needs Mainland Access, the AP stand-in for the single
vanilla bridge flip that Phnom Penh '86 performs; Starfish Island needs
Starfish Island Access, the AP stand-in for the island's gates (see data.py).
Neither area item implies the other: the island's east gate opens on Starfish
Island Access alone and its west gate only with both items, so with Mainland
Access alone both island gates stay shut.

With split_mainland_access on, Mainland Access is replaced by one item per
vanilla crossing and the mainland is reached by holding any single crossing, so
which bridge is open decides where the player crosses rather than whether they
can. The causeway crossing carries Starfish Island Access with it, which is the
one crossing needing the island first.
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


def _has_any_group(groups: list[list[str]]) -> RulePredicate:
    # Any one group is enough, and a group needs all of its items. With one
    # single-item group this is a plain has(), which is every region but a
    # mainland whose crossings are split.
    return lambda state, player: any(
        all(state.has(item, player) for item in group) for group in groups
    )


def build_region_entry_rules(
    split_mainland_access: bool = False,
) -> dict[str, RulePredicate]:
    """Entry rule per non-start region. A region absent from the result is
    reached from the start region with no requirement."""
    rules: dict[str, RulePredicate] = {}
    for region in REGION_NAMES:
        if region == START_REGION:
            continue
        groups = data.region_access_groups(region, split_mainland_access)
        if groups:
            rules[region] = _has_any_group(groups)
    return rules
