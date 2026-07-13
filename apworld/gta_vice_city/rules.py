"""Access rules: the logic core.

Every story mission location's rule is its giver's progressive-unlock count.
The area requirement is carried by the region the location sits in, so it is
not repeated here. Hidden packages have no rule (free within their region).
The sphere-0 giver's first mission has no rule at all.
"""

from __future__ import annotations

from collections.abc import Callable

from BaseClasses import CollectionState

from . import data, locations

RulePredicate = Callable[[CollectionState, int], bool]


def _has_count(item: str, count: int) -> RulePredicate:
    return lambda state, player: state.has(item, player, count)


def build_location_rules() -> dict[str, RulePredicate]:
    rules: dict[str, RulePredicate] = {}
    for mission, giver in locations.MISSION_GIVER.items():
        index = locations.MISSION_INDEX[mission]
        # Sphere-0 giver: first mission (index 0) is free; mission i needs i.
        # Every other giver: mission i needs its first i+1 unlocks.
        needed = index if giver == data.SPHERE_ZERO_GIVER else index + 1
        if needed <= 0:
            continue
        rules[mission] = _has_count(data.progressive_item_name(giver), needed)
    return rules


LOCATION_RULES: dict[str, RulePredicate] = build_location_rules()
