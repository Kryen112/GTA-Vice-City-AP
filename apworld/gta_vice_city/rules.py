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
by the region it sits in; a rule names a region requirement only when it needs a
region its own does not give it, which is the eight missions in
data.MISSION_REGION_REQUIREMENTS, the one mission whose predecessors are played
on another island (Cap the Collector, behind the three mansion missions), and the
Starfish Island Access inside the property-sale requirements, since Shakedown
gives from the mansion. A region with one way in
contributes flat terms, so an unsplit seed's rules keep the shape they always
had; the mainland with split_mainland_access on contributes a one-of threshold
over its crossings instead, and the finale's last mission is the one rule
carrying two thresholds at once.

Two families of lock add terms, each only while its own key is selected (with
the key off the item is not in the pool, so no rule may name it). Ability locks
gate on what Tommy can do and content locks on what is in the world; they
compose by union, since either lock alone still stops the check. The wallet
rides the property-sale requirements, covering business purchases, venue
missions, and the finale's assets in one place; the item releasing a particular
property's icon does not, since split locks make that item the district's rather
than the class's, so each caller that names a property adds its own. Safehouse
purchases and the collectible classes carry their items directly, through
data.LOCATION_ABILITY_REQUIREMENTS and data.content_item_for. The ability terms
are the minimal day-one set and the pre-release manual runthrough adds the rest;
a content term covers a whole class or one district of one, which
data.content_item_for decides from the seed's granularity. Both families
propagate forward through a strand along with everything else, so a mission
behind an ability-locked mission carries that lock too: Two Bit Hit needs the
land vehicle Demolition Man needs, and no fill can strand a lock item behind the
mission its own lock holds. Propagation crosses the strand boundary as well,
since holding an edge's progressives stands in for having passed the missions
they open; _inherited_missions is the one traversal deciding what a mission
inherits, and every kind of requirement is read off its answer.

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
# One counted threshold: the alternative requirement sets and how many of them
# must hold.
Threshold = tuple[list[list[Requirement]], int]


def _requires(requirements: list[Requirement]) -> RulePredicate:
    return lambda state, player: all(
        state.has(item, player, count) for item, count in requirements
    )


def _satisfied(state: CollectionState, player: int,
               requirements: list[Requirement]) -> bool:
    return all(state.has(item, player, count) for item, count in requirements)


def _requires_with_thresholds(
    requirements: list[Requirement],
    thresholds: list[Threshold],
) -> RulePredicate:
    # The conjunction of `requirements` plus one count per threshold: at least
    # `needed` of that threshold's alternatives fully satisfiable. Two are in
    # use. The finale's mirrors the FIN1 gate's owned-asset count, which any
    # large enough subset satisfies. A region's counts the ways in, which is one
    # group unless the mainland crossings are split, and the finale's last
    # mission carries both at once.
    return lambda state, player: (
        _satisfied(state, player, requirements)
        and all(
            sum(1 for group in alternatives if _satisfied(state, player, group)) >= needed
            for alternatives, needed in thresholds
        )
    )


def _region_terms(regions_needed: list[str],
                  split_mainland_access: bool) -> tuple[list[Requirement],
                                                        list[Threshold]]:
    # What reaching these regions demands. A region with one way in contributes
    # flat terms, so nothing about a rule's shape changes while the crossings are
    # whole; a region with several contributes a one-of threshold.
    flat: list[Requirement] = []
    thresholds: list[Threshold] = []
    for region in regions_needed:
        groups = data.region_access_groups(region, split_mainland_access)
        if len(groups) == 1:
            flat.extend((item, 1) for item in groups[0])
        elif groups:
            thresholds.append(([[(item, 1) for item in group] for group in groups], 1))
    return flat, thresholds


def _ability_terms(location_name: str, active_items: frozenset[str]) -> list[Requirement]:
    # The location's ability items, kept only while their ability_locks key is
    # selected (active): an unselected key leaves the item out of the pool, so
    # naming it would make the location unreachable, not vanilla.
    return [
        (item, 1)
        for item in data.LOCATION_ABILITY_REQUIREMENTS.get(location_name, [])
        if item in active_items
    ]


def _content_terms(location_name: str, active_items: frozenset[str],
                   split_content_locks: int) -> list[Requirement]:
    # The location's content-lock item, on the same terms as an ability item.
    # One item or none either way. Whether a location is locked at all is a
    # question about its class, which active_items answers by class item; the
    # granularity then decides which item covers it, the class or its district.
    class_item = data.LOCATION_CONTENT_CLASS.get(location_name)
    if class_item is None or class_item not in active_items:
        return []
    covering = data.content_item_for(location_name, split_content_locks)
    return [] if covering is None else [(covering, 1)]


def _property_content_terms(purchase: str, active_items: frozenset[str],
                            split_content_locks: int) -> list[Requirement]:
    # What has to arrive before this one property can be bought: whole, the one
    # class item covering all fifteen icons; split, the item covering the
    # district this property stands in.
    if data.PROPERTY_PURCHASES_ITEM not in active_items:
        return []
    covering = data.content_item_for(purchase, split_content_locks)
    return [] if covering is None else [(covering, 1)]


def _any_property_content_terms(active_items: frozenset[str],
                                split_content_locks: int) -> list[Requirement]:
    # What has to arrive before ANY property can be bought, for the one caller
    # that cannot name one: the finale with the properties class off, where no
    # purchase location exists to carry a term and vanilla asset completion
    # still spends money at the icons. Whole that is the class item; split it is
    # every district holding a property, which over-requires on purpose rather
    # than risk a finale reachable while the icons it needs are still held.
    if data.PROPERTY_PURCHASES_ITEM not in active_items:
        return []
    return [(item, 1) for item in data.property_content_items(split_content_locks)]


def _lock_terms(location_name: str, active_items: frozenset[str],
                split_content_locks: int) -> list[Requirement]:
    # Every lock term a location carries. The two families compose by union: a
    # store behind both the weapon_equip ability key and the robbable_stores
    # content key needs both items, since either lock alone still stops it.
    return (_ability_terms(location_name, active_items)
            + _content_terms(location_name, active_items, split_content_locks))


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


def _inherited_missions(mission: str, giver: str) -> list[str]:
    """Every mission whose rules this one inherits, transitively.

    A mission cannot start until its strand's earlier missions have passed, and
    holding a cross-strand edge's progressives is the stand-in for having passed
    that strand's first few, so both kinds of predecessor count. Whatever passing
    any of them takes is part of reaching this mission.

    Without this the fill can put an item behind the very mission that needs it:
    Rub Out is reachable on one Progressive Death Row, but passing Death Row
    needs a weapon, so a seed could hide Weapon Equip behind Rub Out.

    Transitive and cycle-safe. The tables have only two edges today and no chain
    longer than one, but the rule is about what a mission inherits and not about
    how deep this particular data happens to go.
    """
    reached: list[str] = []
    seen: set[str] = set()
    pending = [(mission, giver)]
    while pending:
        current, current_giver = pending.pop()
        index = locations.MISSION_INDEX[current]
        earlier = list(locations.STRAND_MISSIONS[current_giver][:index])
        edges = list(data.STRAND_PREREQUISITES.get(current_giver, []))
        edges += list(data.MISSION_PREREQUISITES.get(current, []))
        for strand, count in edges:
            earlier += locations.STRAND_MISSIONS[strand][:count]
        for predecessor in earlier:
            if predecessor in seen:
                continue
            seen.add(predecessor)
            reached.append(predecessor)
            pending.append((predecessor, locations.MISSION_GIVER[predecessor]))
    return reached


def _predecessor_requirements(mission: str, giver: str,
                              active_items: frozenset[str],
                              split_content_locks: int) -> list[Requirement]:
    # What the missions this one inherits demand. A strand runs in order: APMARK
    # reveals only the strand's first unpassed mission and the vanilla launcher
    # starts are severed, so a mission cannot start until every earlier mission
    # of its strand has PASSED. Whatever passing those takes is therefore part of
    # reaching this one, which is the same reasoning
    # _asset_completion_requirements applies to the slice of a venue strand an
    # asset completes through.
    #
    # Three kinds of requirement come from the one inherited set, so none of the
    # three can be left behind: the progressives an inherited mission opens on,
    # its own locks, and, through _inherited_regions walking the same set, its
    # region. A venue's ownership item and the property-sale requirements are not
    # among them; build_location_rules adds those for the mission's own strand,
    # so an edge into a venue strand would inherit the three and not those.
    # A mission's own strand count is already the highest in its strand, so the
    # in-strand progressives here only ever restate it; the counts that matter
    # are the ones an inherited mission of ANOTHER strand opens on.
    requirements: list[Requirement] = []
    for earlier in _inherited_missions(mission, giver):
        edges = list(data.STRAND_PREREQUISITES.get(locations.MISSION_GIVER[earlier], []))
        edges += list(data.MISSION_PREREQUISITES.get(earlier, []))
        for prerequisite_giver, count in edges:
            requirements.append((data.progressive_item_name(prerequisite_giver), count))
        requirements.extend(
            _lock_terms(earlier, active_items, split_content_locks))
    return requirements


def _mission_requirements(mission: str, giver: str, active_items: frozenset[str],
                          split_content_locks: int,
                          split_mainland_access: bool) -> list[Requirement]:
    # The launcher-gate view: progressive unlocks, plus any area item the mission
    # needs that its own region does not give it, its own or a predecessor's, plus
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
    # Its own regions and the ones it inherits, from the one gatherer, so the
    # flat half here and the threshold half in _mission_region_thresholds always
    # describe the same set.
    region_requirements, _ = _region_terms(
        _inherited_regions(mission, giver), split_mainland_access)
    requirements.extend(region_requirements)
    requirements.extend(_lock_terms(mission, active_items, split_content_locks))
    requirements.extend(_predecessor_requirements(
        mission, giver, active_items, split_content_locks))
    return _deduplicated(requirements)


def _inherited_regions(mission: str, giver: str) -> list[str]:
    """Every region this mission needs, its own and the ones it inherits.

    A predecessor contributes two regions, and both are part of passing it: the
    island it is played on, which is the region its own location sits in, and any
    region beyond that in MISSION_REGION_REQUIREMENTS. The island matters even
    though the region graph gates the predecessor's own location, because holding
    a strand's progressives is what stands in for having passed its missions, and
    the items can be anywhere: Cap the Collector is played on the mainland and
    opens on three Progressive Vercetti Protection, and those three are played
    from the mansion on Starfish Island, which nothing else about it names.

    A predecessor on this mission's own island adds nothing, since the region
    graph gates this location there already, so it is left out; the rule then
    names an area item only where the graph does not supply it, and the SCM gate
    dump stays a list of the gates the mod actually implements.

    Gathered in one place because the flat half and the threshold half of a
    region requirement must come from the same list: with the crossings split the
    mainland has four ways in and can only be expressed as a threshold, and the
    two halves disagreeing is how a requirement gets silently dropped.
    """
    own_region = locations.LOCATION_REGIONS[mission]
    regions = list(data.MISSION_REGION_REQUIREMENTS.get(mission, []))
    for earlier in _inherited_missions(mission, giver):
        if locations.LOCATION_REGIONS[earlier] != own_region:
            regions.append(locations.LOCATION_REGIONS[earlier])
        regions.extend(data.MISSION_REGION_REQUIREMENTS.get(earlier, []))
    return list(dict.fromkeys(regions))


def _mission_region_thresholds(mission: str, giver: str,
                               split_mainland_access: bool) -> list[Threshold]:
    # The threshold part of those regions, which only the mainland has and only
    # while the crossings are split.
    _flat, thresholds = _region_terms(
        _inherited_regions(mission, giver), split_mainland_access)
    return thresholds


def _property_sale_requirements(active_items: frozenset[str],
                                split_content_locks: int,
                                split_mainland_access: bool) -> list[Requirement]:
    # A business is for sale only once Shakedown passes, so anything behind
    # buying one requires everything logic needs to pass Shakedown: its items
    # and the area item of the region its marker sits in (the mansion on
    # Starfish Island). The purchase price is money: grindable by amount, but
    # holdable only with the Wallet item while the wallet lock is selected, so
    # the wallet term rides here, covering business purchases, venue missions,
    # and the finale's assets in one place.
    mission = data.PROPERTY_UNLOCK_MISSION
    requirements = _mission_requirements(
        mission, locations.MISSION_GIVER[mission], active_items,
        split_content_locks, split_mainland_access)
    region = locations.LOCATION_REGIONS[mission]
    # Shakedown is on Starfish Island, which has one way in however the mainland
    # crossings are set, so its own region is always flat.
    region_requirements, _ = _region_terms([region], split_mainland_access)
    requirements = [*requirements, *region_requirements]
    # Everything behind a business purchase carries this list flat, so a
    # threshold in it would be dropped rather than gated, which is the loop the
    # crossing split exists to avoid: a mission needing the mainland to be
    # passed, and the crossing item free to sit behind a purchase that needs it.
    # Empty today, since Shakedown opens its own strand from the mansion and
    # inherits nothing. Give it or one of its predecessors a mainland term and
    # this raises, which is the signal to hand the callers both halves.
    if _mission_region_thresholds(mission, locations.MISSION_GIVER[mission],
                                  split_mainland_access):
        raise ValueError(
            f"{mission} needs a region with several ways in; the property sale "
            f"requirements are carried flat and cannot hold a threshold")
    if data.WALLET_ITEM in active_items:
        requirements = [*requirements, (data.WALLET_ITEM, 1)]
    # The property content lock does NOT ride here, because split by district it
    # is not one item for all fifteen icons: each caller adds the term for the
    # property it is buying, through _property_content_terms, or the strict union
    # through _any_property_content_terms where it can name none.
    return requirements


def _asset_completion_requirements(asset: str, progressive_count: int,
                                   active_items: frozenset[str],
                                   split_content_locks: int) -> list[Requirement]:
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
    #
    # Lock terms only, no region: these lists sit inside the finale's own
    # threshold over asset groups, where a nested threshold has no shape, and
    # they need none. Every region a sliced mission needs is one the finale's own
    # rule already requires, so the group's copy would add nothing, which
    # test_an_asset_slice_needs_no_region_the_finale_lacks pins.
    # Everything else about buying the property is the sale requirements' job,
    # carried once by the finale rule; what belongs to the asset itself is the
    # item releasing its own icon, since split locks make that the district's.
    requirements: list[Requirement] = [
        (data.ownership_item_name(asset), 1),
        *_property_content_terms(f"{asset} Purchase", active_items,
                                 split_content_locks),
    ]
    if progressive_count > 0:
        requirements.append((data.progressive_item_name(asset), progressive_count))
    for mission in data.VENUE_STRANDS.get(asset, [])[:progressive_count]:
        requirements.extend(_lock_terms(mission, active_items, split_content_locks))
    requirements.extend(
        (item, 1)
        for item in data.ASSET_ABILITY_REQUIREMENTS.get(asset, [])
        if item in active_items
    )
    return _deduplicated(requirements)


def _finale_asset_terms(
    active_items: frozenset[str],
    split_content_locks: int,
    split_mainland_access: bool,
) -> tuple[list[Requirement], list[list[Requirement]]]:
    # The finale's vanilla asset prerequisite as items. Hit the Courier
    # (Printworks' last mission) is individually mandatory, Cop Land arrives
    # through the protection progressives already in the finale's own
    # requirements, and the remaining threshold picks from the optional
    # assets. The sale requirements ride along once, covering every purchase.
    mandatory = (
        _asset_completion_requirements(
            "Printworks", len(data.VENUE_STRANDS["Printworks"]), active_items,
            split_content_locks)
        + _property_sale_requirements(
            active_items, split_content_locks, split_mainland_access)
    )
    optional = [
        _asset_completion_requirements(asset, progressive_count, active_items,
                                       split_content_locks)
        for asset, progressive_count in data.FINALE_OPTIONAL_ASSETS.items()
    ]
    return mandatory, optional


def build_location_rules(
    properties_enabled: bool = True,
    ability_locks: frozenset[str] = frozenset(),
    content_locks: frozenset[str] = frozenset(),
    split_mainland_access: bool = False,
    split_content_locks: int = data.CONTENT_SPLIT_OFF,
) -> dict[str, RulePredicate]:
    # One active set for both lock families: a term binds when its own key is
    # selected, and every predicate below filters against this.
    # The class item is what says a class is locked, whatever the granularity,
    # so it stays in here even when the items in the pool are the district ones:
    # every content term is emitted through data.content_item_for, which turns
    # the class into the covering item for the seed.
    active_items = frozenset(
        [item for key in ability_locks for item in data.ABILITY_LOCK_ITEMS[key]]
        + [data.CONTENT_LOCK_ITEMS[key] for key in content_locks]
    )
    rules: dict[str, RulePredicate] = {}
    sale_requirements = _property_sale_requirements(
        active_items, split_content_locks, split_mainland_access)
    finale_mandatory, finale_optional = _finale_asset_terms(
        active_items, split_content_locks, split_mainland_access)
    for mission, giver in locations.MISSION_GIVER.items():
        requirements = _mission_requirements(
            mission, giver, active_items, split_content_locks, split_mainland_access)
        region_thresholds = _mission_region_thresholds(
            mission, giver, split_mainland_access)
        if giver in data.VENUE_STRANDS:
            requirements = [
                *requirements,
                (data.ownership_item_name(giver), 1),
                *sale_requirements,
                *_property_content_terms(f"{giver} Purchase", active_items,
                                         split_content_locks),
            ]
        if giver == "Vercetti Finale":
            if properties_enabled:
                rules[mission] = _requires_with_thresholds(
                    requirements + finale_mandatory,
                    [*region_thresholds,
                     (finale_optional, data.FINALE_OPTIONAL_ASSETS_REQUIRED)],
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
                off_requirements = (
                    requirements + sale_requirements
                    + _any_property_content_terms(active_items, split_content_locks))
                rules[mission] = (
                    _requires_with_thresholds(off_requirements, region_thresholds)
                    if region_thresholds else _requires(off_requirements)
                )
            continue
        if region_thresholds:
            rules[mission] = _requires_with_thresholds(requirements, region_thresholds)
        elif requirements:
            rules[mission] = _requires(requirements)
    for purchase in data.BUSINESS_PURCHASES:
        rules[purchase] = _requires(
            sale_requirements
            + _property_content_terms(purchase, active_items, split_content_locks))
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
                *_property_content_terms(f"{venue} Purchase", active_items,
                                         split_content_locks),
                *_lock_terms(activity, active_items, split_content_locks),
            ])
    # Every remaining location with a lock term: the collectible and activity
    # classes and the safehouse purchases, which carry no other rule. A
    # business purchase and a venue activity are already ruled above, with the
    # item releasing their property's icon added there, so both are skipped here
    # rather than ruled twice.
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
        lock_terms = _lock_terms(location_name, active_items, split_content_locks)
        if lock_terms:
            rules[location_name] = _requires(lock_terms)
    return rules
