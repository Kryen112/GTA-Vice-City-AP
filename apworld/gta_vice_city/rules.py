"""Access rules: the logic core.

Every mission location (story giver or venue strand) has a rule that is the
conjunction of: its strand's progressive-unlock count, any cross-giver
prerequisite gating the whole strand (only the finale has one), and any
mission-specific cross-giver edge. A venue mission additionally requires the
items to pass Shakedown: its property must be bought in game, and the
businesses go on sale only when Shakedown passes. The same requirement gates
each business purchase; the price itself is money, which is grindable and
never a gate. The area requirement is carried by the region the location sits
in, so it is not repeated here. Collectibles, activities, safehouse purchases,
and stores have no rule (free within their region). The sphere-0 giver's first
mission has no requirement at all.
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
    # The launcher-gate view: progressive unlocks only. The SCM mission gates
    # mirror exactly this; a venue's ownership requirement is added on top in
    # build_location_rules (in game the gate reads the purchase's completion
    # global instead of items).
    requirements: list[Requirement] = []
    index = locations.MISSION_INDEX[mission]
    # Sphere-0 giver: first mission (index 0) is free; mission i needs i.
    # Every other giver: mission i needs its first i+1 unlocks.
    own_count = index if giver == data.SPHERE_ZERO_GIVER else index + 1
    if own_count > 0:
        requirements.append((data.progressive_item_name(giver), own_count))
    for prerequisite_giver, count in data.STRAND_PREREQUISITES.get(giver, []):
        requirements.append((data.progressive_item_name(prerequisite_giver), count))
    for prerequisite_giver, count in data.MISSION_PREREQUISITES.get(mission, []):
        requirements.append((data.progressive_item_name(prerequisite_giver), count))
    return requirements


def _property_sale_requirements() -> list[Requirement]:
    # A business is for sale only once Shakedown passes, so anything behind
    # buying one requires the items to pass Shakedown. The purchase price is
    # money, which is grindable and never gates logic.
    mission = data.PROPERTY_UNLOCK_MISSION
    return _mission_requirements(mission, locations.MISSION_GIVER[mission])


def build_location_rules() -> dict[str, RulePredicate]:
    rules: dict[str, RulePredicate] = {}
    sale_requirements = _property_sale_requirements()
    for mission, giver in locations.MISSION_GIVER.items():
        requirements = _mission_requirements(mission, giver)
        if giver in data.VENUE_STRANDS:
            requirements = requirements + sale_requirements
        if requirements:
            rules[mission] = _requires(requirements)
    for purchase in data.BUSINESS_PURCHASES:
        rules[purchase] = _requires(sale_requirements)
    return rules


LOCATION_RULES: dict[str, RulePredicate] = build_location_rules()
