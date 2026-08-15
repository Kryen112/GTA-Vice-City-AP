"""Access rules: the logic core.

Every mission location (story giver or venue strand) has a rule that is the
conjunction of: its strand's progressive-unlock count, any cross-giver
prerequisite gating the whole strand (only the finale has one), and any
mission-specific cross-giver edge. A venue mission additionally requires its
property's ownership item (the building arrives as an item, not with the
purchase) and the items to pass Shakedown: the property must also be bought in
game, and the businesses go on sale only when Shakedown passes. The same sale
requirement gates each business purchase; the price itself is money, which is
grindable and never a gate. The two finale missions carry the vanilla asset
prerequisite when the properties class is on: Hit the Courier completable plus
enough of the optional income assets completable, each through its ownership
item and progressives. A location's own area requirement is carried by the
region it sits in; a rule names an area item only when the requirement crosses
regions (the finale's Mainland Access, and the Starfish Island Access inside
the property-sale requirements, since Shakedown gives from the mansion).
Collectibles, activities, safehouse purchases, and stores have no rule (free
within their region). The sphere-0 giver's first mission has no requirement
at all.
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


def _requires_with_asset_threshold(
    requirements: list[Requirement],
    optional_assets: list[list[Requirement]],
    needed: int,
) -> RulePredicate:
    # The conjunction of `requirements` plus a threshold: at least `needed` of
    # the optional asset requirement sets fully satisfiable. Mirrors the FIN1
    # gate's owned-asset count, which any large enough subset satisfies.
    return lambda state, player: (
        all(state.has(item, player, count) for item, count in requirements)
        and sum(
            1 for asset_requirements in optional_assets
            if all(state.has(item, player, count) for item, count in asset_requirements)
        ) >= needed
    )


def _mission_requirements(mission: str, giver: str) -> list[Requirement]:
    # The launcher-gate view: progressive unlocks, plus any area item the
    # mission needs beyond its own region (the finale's Mainland Access). The
    # SCM mission gates mirror the unlock counts; a venue's ownership and
    # purchase requirements are added on top in build_location_rules (in game
    # the gate reads the ownership global and the purchase's completion
    # global).
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
    requirements.extend(
        (area_item, 1) for area_item in data.MISSION_AREA_REQUIREMENTS.get(mission, [])
    )
    return requirements


def _property_sale_requirements() -> list[Requirement]:
    # A business is for sale only once Shakedown passes, so anything behind
    # buying one requires everything logic needs to pass Shakedown: its items
    # and the area item of the region its marker sits in (the mansion on
    # Starfish Island). The purchase price is money, which is grindable and
    # never gates logic.
    mission = data.PROPERTY_UNLOCK_MISSION
    requirements = _mission_requirements(mission, locations.MISSION_GIVER[mission])
    region = locations.LOCATION_REGIONS[mission]
    area_item = data.AREA_ITEM_BY_REGION.get(region)
    if area_item is not None:
        requirements = [*requirements, (area_item, 1)]
    return requirements


def _asset_completion_requirements(asset: str, progressive_count: int) -> list[Requirement]:
    # The items to complete an income asset: its ownership item (buying the
    # property is covered by the property-sale requirements the finale rule
    # carries once) and, where the asset completes through its venue strand,
    # the progressives to reach the strand's last mission.
    requirements: list[Requirement] = [(data.ownership_item_name(asset), 1)]
    if progressive_count > 0:
        requirements.append((data.progressive_item_name(asset), progressive_count))
    return requirements


def _finale_asset_terms() -> tuple[list[Requirement], list[list[Requirement]]]:
    # The finale's vanilla asset prerequisite as items. Hit the Courier
    # (Printworks' last mission) is individually mandatory, Cop Land arrives
    # through the protection progressives already in the finale's own
    # requirements, and the remaining threshold picks from the optional
    # assets. The sale requirements ride along once, covering every purchase.
    mandatory = (
        _asset_completion_requirements("Printworks", len(data.VENUE_STRANDS["Printworks"]))
        + _property_sale_requirements()
    )
    optional = [
        _asset_completion_requirements(asset, progressive_count)
        for asset, progressive_count in data.FINALE_OPTIONAL_ASSETS.items()
    ]
    return mandatory, optional


def build_location_rules(properties_enabled: bool = True) -> dict[str, RulePredicate]:
    rules: dict[str, RulePredicate] = {}
    sale_requirements = _property_sale_requirements()
    finale_mandatory, finale_optional = _finale_asset_terms()
    for mission, giver in locations.MISSION_GIVER.items():
        requirements = _mission_requirements(mission, giver)
        if giver in data.VENUE_STRANDS:
            requirements = [
                *requirements,
                (data.ownership_item_name(giver), 1),
                *sale_requirements,
            ]
        if giver == "Vercetti Finale":
            if properties_enabled:
                rules[mission] = _requires_with_asset_threshold(
                    requirements + finale_mandatory,
                    finale_optional,
                    data.FINALE_OPTIONAL_ASSETS_REQUIRED,
                )
            else:
                # With the properties class off the asset items leave the pool
                # and assets complete vanilla-style with grindable money, but
                # the FIN1 gate still reads the vanilla flags, and Shakedown
                # and Cop Land are given from the mansion: the finale keeps
                # the property-sale requirements (Starfish Island Access
                # included) so the fill cannot strand that item behind it.
                rules[mission] = _requires(requirements + sale_requirements)
            continue
        if requirements:
            rules[mission] = _requires(requirements)
    for purchase in data.BUSINESS_PURCHASES:
        rules[purchase] = _requires(sale_requirements)
    return rules


LOCATION_RULES: dict[str, RulePredicate] = build_location_rules()
