"""Access rules: the logic core.

Every mission location (story giver or venue strand) has a rule that is the
conjunction of: its strand's progressive-unlock count, any cross-giver
prerequisite gating the whole strand (only the finale has one), any
mission-specific cross-giver edge, and everything the earlier missions of its
own strand require, since a strand runs in order and a mission cannot start
until its predecessors have passed. A venue mission additionally requires its
property's ownership item (the building arrives as an item, not with the
purchase) and the items to pass Shakedown: the property must also be bought in
game, and the businesses go on sale only when Shakedown passes. The same sale
requirement gates each business purchase; the price itself is money, which is
grindable and never a gate by amount. The two finale missions carry the vanilla
asset prerequisite when the properties class is on: Hit the Courier completable
plus enough of the optional income assets completable, each through its
ownership item and progressives. A location's own area requirement is carried
by the region it sits in; a rule names an area item only when the requirement
crosses regions (the finale's Mainland Access, and the Starfish Island Access
inside the property-sale requirements, since Shakedown gives from the mansion).

Two families of lock add terms, each only while its own key is selected (with
the key off the item is not in the pool, so no rule may name it). Ability locks
gate on what Tommy can do and content locks on what is in the world; they
compose by union, since either lock alone still stops the check. The wallet and
the property content item both ride the property-sale requirements, covering
business purchases, venue missions, and the finale's assets in one place;
safehouse purchases and the collectible classes carry their items directly from
data.LOCATION_ABILITY_REQUIREMENTS and data.LOCATION_CONTENT_REQUIREMENTS. The
ability terms are the minimal day-one set and the pre-release manual runthrough
adds the rest; a content term is uniform across its whole class, so it needs no
audit. Both families propagate forward through a strand along with everything
else, so a mission behind an ability-locked mission carries that lock too: Two
Bit Hit needs the land vehicle Demolition Man needs, and within a strand no fill
can strand a lock item behind the mission its own lock holds. Propagation stops
at the strand boundary, where the in-game ordering constraint stops: a
cross-giver edge names the target strand's progressive count alone, which holds
only while the missions that count implies carry no lock terms of their own, and
a test pins that.

With neither family selected, collectibles, activities, safehouse purchases,
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


def _ability_terms(location_name: str, active_items: frozenset[str]) -> list[Requirement]:
    # The location's ability items, kept only while their ability_locks key is
    # selected (active): an unselected key leaves the item out of the pool, so
    # naming it would make the location unreachable, not vanilla.
    return [
        (item, 1)
        for item in data.LOCATION_ABILITY_REQUIREMENTS.get(location_name, [])
        if item in active_items
    ]


def _content_terms(location_name: str, active_items: frozenset[str]) -> list[Requirement]:
    # The location's content-lock item, on the same terms as an ability item.
    # A content lock is uniform across its class, so this is one item or none.
    return [
        (item, 1)
        for item in data.LOCATION_CONTENT_REQUIREMENTS.get(location_name, [])
        if item in active_items
    ]


def _lock_terms(location_name: str, active_items: frozenset[str]) -> list[Requirement]:
    # Every lock term a location carries. The two families compose by union: a
    # store behind both the weapon_equip ability key and the robbable_stores
    # content key needs both items, since either lock alone still stops it.
    return (_ability_terms(location_name, active_items)
            + _content_terms(location_name, active_items))


def _deduplicated(requirements: list[Requirement]) -> list[Requirement]:
    # Same item twice is the same requirement; keep the higher count and the
    # first position, so a gathered list stays one entry per item.
    highest: dict[str, int] = {}
    for item, count in requirements:
        highest[item] = max(highest.get(item, 0), count)
    seen: set[str] = set()
    ordered: list[Requirement] = []
    for item, _count in requirements:
        if item in seen:
            continue
        seen.add(item)
        ordered.append((item, highest[item]))
    return ordered


def _predecessor_requirements(giver: str, index: int,
                              active_items: frozenset[str]) -> list[Requirement]:
    # What the earlier missions of this strand demand. A strand runs in order:
    # APMARK reveals only the strand's first unpassed mission and the vanilla
    # launcher starts are severed, so a mission cannot start until every earlier
    # mission of its strand has PASSED. Whatever passing those takes is
    # therefore part of reaching this one, which is the same reasoning
    # _asset_completion_requirements applies to the slice of a venue strand an
    # asset completes through. The progressive counts need no propagation, since
    # this mission's own count is already the highest in the strand.
    requirements: list[Requirement] = []
    for earlier in locations.STRAND_MISSIONS[giver][:index]:
        for prerequisite_giver, count in data.MISSION_PREREQUISITES.get(earlier, []):
            requirements.append((data.progressive_item_name(prerequisite_giver), count))
        requirements.extend(
            (area_item, 1)
            for area_item in data.MISSION_AREA_REQUIREMENTS.get(earlier, [])
        )
        requirements.extend(_lock_terms(earlier, active_items))
    return requirements


def _mission_requirements(mission: str, giver: str,
                          active_items: frozenset[str]) -> list[Requirement]:
    # The launcher-gate view: progressive unlocks, plus any area item the
    # mission needs beyond its own region (the finale's Mainland Access), plus
    # the mission's ability terms and those of the earlier missions of its
    # strand. The SCM mission gates mirror the unlock counts; a venue's
    # ownership and purchase requirements are added on top in
    # build_location_rules (in game the gate reads the ownership global and the
    # purchase's completion global), and an ability lock is ASI-enforced, not
    # gated in the SCM.
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
    requirements.extend(_lock_terms(mission, active_items))
    requirements.extend(_predecessor_requirements(giver, index, active_items))
    return _deduplicated(requirements)


def _property_sale_requirements(active_items: frozenset[str]) -> list[Requirement]:
    # A business is for sale only once Shakedown passes, so anything behind
    # buying one requires everything logic needs to pass Shakedown: its items
    # and the area item of the region its marker sits in (the mansion on
    # Starfish Island). The purchase price is money: grindable by amount, but
    # holdable only with the Wallet item while the wallet lock is selected, so
    # the wallet term rides here, covering business purchases, venue missions,
    # and the finale's assets in one place.
    mission = data.PROPERTY_UNLOCK_MISSION
    requirements = _mission_requirements(
        mission, locations.MISSION_GIVER[mission], active_items)
    region = locations.LOCATION_REGIONS[mission]
    area_item = data.AREA_ITEM_BY_REGION.get(region)
    if area_item is not None:
        requirements = [*requirements, (area_item, 1)]
    if data.WALLET_ITEM in active_items:
        requirements = [*requirements, (data.WALLET_ITEM, 1)]
    # The property content lock rides here for the same reason the wallet does:
    # with the icons held, nothing can be bought, so everything behind buying a
    # property needs the item. This is what carries it onto the finale when the
    # properties class is off and no purchase location exists to carry it.
    if data.PROPERTY_PURCHASES_ITEM in active_items:
        requirements = [*requirements, (data.PROPERTY_PURCHASES_ITEM, 1)]
    return requirements


def _asset_completion_requirements(asset: str, progressive_count: int,
                                   active_items: frozenset[str]) -> list[Requirement]:
    # The items to complete an income asset: its ownership item (buying the
    # property is covered by the property-sale requirements the finale rule
    # carries once), where the asset completes through its venue strand the
    # progressives to reach the strand's last mission, and the ability terms
    # of the missions that completion actually reaches plus the asset's own
    # (the Sunshine Autos import lists take delivering vehicles). The strand
    # is sliced to the progressives the asset needs: Sunshine Autos completes
    # through the import lists, not its race, so the race's terms are none of
    # the threshold's business. The count doubles as a mission count because a
    # venue strand's nth mission is exactly what its nth progressive opens.
    requirements: list[Requirement] = [(data.ownership_item_name(asset), 1)]
    if progressive_count > 0:
        requirements.append((data.progressive_item_name(asset), progressive_count))
    for mission in data.VENUE_STRANDS.get(asset, [])[:progressive_count]:
        requirements.extend(_lock_terms(mission, active_items))
    requirements.extend(
        (item, 1)
        for item in data.ASSET_ABILITY_REQUIREMENTS.get(asset, [])
        if item in active_items
    )
    return _deduplicated(requirements)


def _finale_asset_terms(
    active_items: frozenset[str],
) -> tuple[list[Requirement], list[list[Requirement]]]:
    # The finale's vanilla asset prerequisite as items. Hit the Courier
    # (Printworks' last mission) is individually mandatory, Cop Land arrives
    # through the protection progressives already in the finale's own
    # requirements, and the remaining threshold picks from the optional
    # assets. The sale requirements ride along once, covering every purchase.
    mandatory = (
        _asset_completion_requirements(
            "Printworks", len(data.VENUE_STRANDS["Printworks"]), active_items)
        + _property_sale_requirements(active_items)
    )
    optional = [
        _asset_completion_requirements(asset, progressive_count, active_items)
        for asset, progressive_count in data.FINALE_OPTIONAL_ASSETS.items()
    ]
    return mandatory, optional


def build_location_rules(
    properties_enabled: bool = True,
    ability_locks: frozenset[str] = frozenset(),
    content_locks: frozenset[str] = frozenset(),
) -> dict[str, RulePredicate]:
    # One active set for both lock families: a term binds when its own key is
    # selected, and every predicate below filters against this.
    active_items = frozenset(
        [item for key in ability_locks for item in data.ABILITY_LOCK_ITEMS[key]]
        + [data.CONTENT_LOCK_ITEMS[key] for key in content_locks]
    )
    rules: dict[str, RulePredicate] = {}
    sale_requirements = _property_sale_requirements(active_items)
    finale_mandatory, finale_optional = _finale_asset_terms(active_items)
    for mission, giver in locations.MISSION_GIVER.items():
        requirements = _mission_requirements(mission, giver, active_items)
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
                # included, and the wallet term while its lock is selected,
                # since vanilla asset completion still spends money) so the
                # fill cannot strand those items behind it.
                rules[mission] = _requires(requirements + sale_requirements)
            continue
        if requirements:
            rules[mission] = _requires(requirements)
    for purchase in data.BUSINESS_PURCHASES:
        rules[purchase] = _requires(sale_requirements)
    # A venue's own activities carry no progressive unlock: vanilla opens them
    # all the moment the venue is bought, so they need the venue bought and
    # owned and nothing more, plus their own lock terms.
    venue_activities: set[str] = set()
    for venue, activities in data.VENUE_ACTIVITIES.items():
        for activity in activities:
            venue_activities.add(activity)
            rules[activity] = _requires([
                (data.ownership_item_name(venue), 1),
                *sale_requirements,
                *_lock_terms(activity, active_items),
            ])
    # Every remaining location with a lock term: the collectible and activity
    # classes and the safehouse purchases, which carry no other rule. A
    # business purchase and a venue activity are already ruled above, and a
    # business purchase's content term rides the sale requirements, so both are
    # skipped here rather than ruled twice.
    handled = (
        set(locations.MISSION_GIVER) | set(data.BUSINESS_PURCHASES) | venue_activities
    )
    locked_locations = (
        dict.fromkeys(data.LOCATION_ABILITY_REQUIREMENTS)
        | dict.fromkeys(data.LOCATION_CONTENT_REQUIREMENTS)
    )
    for location_name in locked_locations:
        if location_name in handled:
            continue
        lock_terms = _lock_terms(location_name, active_items)
        if lock_terms:
            rules[location_name] = _requires(lock_terms)
    return rules
