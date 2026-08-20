"""Region graph and entry rules.

Three regions plus Menu. Menu reaches the start island (east) freely; the
mainland (west island) needs Mainland Access, the AP stand-in for the single
vanilla bridge flip that Phnom Penh '86 performs; Starfish Island needs
Starfish Island Access, the AP stand-in for the island's gates (see data.py).
Neither area item implies the other: the island's east gate opens on Starfish
Island Access alone and its west gate only with both items, so with Mainland
Access alone both island gates stay shut.

A barrier is not the only way in. The audit gives each island a helicopter route
and a boat route, since a roadblock stops a car and nothing else, and those are
groups here alongside the barrier: any one group reaches the region. A route
names the mission that hands the vehicle over, which arrives as an event item.

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
    # Any one group is enough, and a group needs all of its items. One
    # single-item group is a plain has(), which is the mainland with its
    # crossings whole; the island always has its audited routes besides its
    # barrier, and a split mainland has one group per crossing.
    return lambda state, player: any(
        all(state.has(item, player) for item in group) for group in groups
    )


def build_region_entry_rules(
    split_mainland_access: bool = False,
    active_items: frozenset[str] = frozenset(),
) -> dict[str, RulePredicate]:
    """Entry rule per non-start region. A region absent from the result is
    reached from the start region with no requirement.

    active_items is the seed's selected lock items, since a route's vehicle term
    binds only while its key is selected.
    """
    rules: dict[str, RulePredicate] = {}
    for region in REGION_NAMES:
        if region == START_REGION:
            continue
        groups = data.active_route_groups(
            data.region_access_groups(region, split_mainland_access), active_items)
        if groups:
            rules[region] = _has_any_group(groups)
    return rules
