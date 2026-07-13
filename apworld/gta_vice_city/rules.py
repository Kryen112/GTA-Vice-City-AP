"""Access rules: the logic core.

Every mission location (story giver or venue strand) has a rule that is the
conjunction of: its strand's progressive-unlock count, the cross-giver spine
prerequisites for that strand (story spine only; venues have none), and any
mission-specific cross-giver edge. The area requirement is carried by the
region the location sits in, so it is not repeated here. Collectibles,
activities, purchases, and stores have no rule (free within their region). The
sphere-0 giver's first mission has no requirement at all.
"""

from __future__ import annotations

from collections.abc import Callable

from BaseClasses import CollectionState

from . import data, locations

RulePredicate = Callable[[CollectionState, int], bool]

# A requirement is (progressive-item name, count). A mission is reachable when
# the state has at least `count` of each listed item.
Requirement = tuple[str, int]


def _requires(requirements: list[Requirement]) -> RulePredicate:
    return lambda state, player: all(
        state.has(item, player, count) for item, count in requirements
    )


def _mission_requirements(mission: str, giver: str) -> list[Requirement]:
    requirements: list[Requirement] = []
    index = locations.MISSION_INDEX[mission]
    # Sphere-0 giver: first mission (index 0) is free; mission i needs i.
    # Every other giver: mission i needs its first i+1 unlocks.
    own_count = index if giver == data.SPHERE_ZERO_GIVER else index + 1
    if own_count > 0:
        requirements.append((data.progressive_item_name(giver), own_count))
    for prerequisite_giver, count in data.SPINE_PREREQUISITES.get(giver, []):
        requirements.append((data.progressive_item_name(prerequisite_giver), count))
    for prerequisite_giver, count in data.MISSION_PREREQUISITES.get(mission, []):
        requirements.append((data.progressive_item_name(prerequisite_giver), count))
    return requirements


def build_location_rules() -> dict[str, RulePredicate]:
    rules: dict[str, RulePredicate] = {}
    for mission, giver in locations.MISSION_GIVER.items():
        requirements = _mission_requirements(mission, giver)
        if requirements:
            rules[mission] = _requires(requirements)
    return rules


LOCATION_RULES: dict[str, RulePredicate] = build_location_rules()
