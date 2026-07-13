"""Grand Theft Auto: Vice City for Archipelago.

Hand-written world. Content tables live in data.py; the item and location id
maps in items.py and locations.py; the access-rule predicates in rules.py; the
region graph in regions.py. There is no code-generation step.

This world implements two check classes: story missions (always on) and
hidden packages. The other check classes and the client bridge are not part
of it.
"""

from __future__ import annotations

from collections.abc import Callable

from BaseClasses import CollectionState, Item, Location, Region
from Options import OptionError
from worlds.AutoWorld import WebWorld, World

from . import data, locations, regions, rules
from .items import FILLER_NAMES, ITEM_CLASSIFICATIONS, ITEM_GROUPS, ITEM_NAME_TO_ID, ITEM_QUANTITIES
from .locations import LOCATION_GROUPS, LOCATION_NAME_TO_ID, LOCATION_REGIONS
from .options import CHECK_CLASS_OPTIONS, Goal, GTAViceCityOptions

# Below this many free-at-start locations, the world grants the east-island
# spine strands so an all-progression pool (a collectible-free seed) can still
# fill.
MINIMUM_SPHERE_ZERO = 10


class GTAViceCityItem(Item):
    game = "Grand Theft Auto Vice City"


class GTAViceCityLocation(Location):
    game = "Grand Theft Auto Vice City"


class GTAViceCityWeb(WebWorld):
    """Web frontend metadata for archipelago.gg."""
    theme = "dirt"


class GTAViceCityWorld(World):
    """Grand Theft Auto: Vice City randomizer.

    Completing a mission sends a check. Progressive per-giver unlocks arriving
    from the multiworld open each giver's next mission in vanilla order.
    """

    game = "Grand Theft Auto Vice City"
    web = GTAViceCityWeb()
    options_dataclass = GTAViceCityOptions
    options: GTAViceCityOptions

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID
    item_name_groups = ITEM_GROUPS
    location_name_groups = LOCATION_GROUPS

    def generate_early(self) -> None:
        options = self.options
        if options.goal == Goal.option_hundred_percent:
            missing = [name for name in CHECK_CLASS_OPTIONS
                       if not getattr(options, name).value]
            if missing:
                raise OptionError(
                    f"{self.game}: the 100 percent goal requires every check "
                    "class enabled, because every stat contributor must be a "
                    f"check. Disabled: {', '.join(sorted(missing))}."
                )
        if options.goal == Goal.option_hidden_packages and not options.enable_hidden_packages:
            raise OptionError(
                f"{self.game}: the hidden-packages goal needs the hidden "
                "packages class enabled."
            )

    def _location_enabled(self, name: str) -> bool:
        if name in locations.PACKAGE_NAMES:
            return bool(self.options.enable_hidden_packages.value)
        return True

    def _item_enabled(self, name: str) -> bool:
        if name in data.PACKAGE_REWARD_ITEMS:
            return bool(self.options.enable_hidden_packages.value)
        return True

    def create_item(self, name: str) -> GTAViceCityItem:
        return GTAViceCityItem(
            name, ITEM_CLASSIFICATIONS[name], ITEM_NAME_TO_ID[name], self.player,
        )

    def get_filler_item_name(self) -> str:
        return self.multiworld.random.choice(FILLER_NAMES)

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)

        by_name: dict[str, Region] = {}
        for region_name in regions.REGION_NAMES:
            region = Region(region_name, self.player, self.multiworld)
            by_name[region_name] = region
            self.multiworld.regions.append(region)

        start = by_name[regions.START_REGION]
        menu.connect(start)
        for region_name, region in by_name.items():
            if region_name == regions.START_REGION:
                continue
            rule = regions.REGION_ENTRY_RULES.get(region_name)
            if rule is None:
                start.connect(region)
            else:
                start.connect(region, rule=self._bind(rule))

        for location_name, region_name in LOCATION_REGIONS.items():
            if not self._location_enabled(location_name):
                continue
            region = by_name[region_name]
            region.locations.append(GTAViceCityLocation(
                self.player, location_name, LOCATION_NAME_TO_ID[location_name], region,
            ))

    def create_items(self) -> None:
        placeable: list[str] = []
        for giver in data.STORY_GIVERS:
            name = data.progressive_item_name(giver)
            placeable.extend([name] * ITEM_QUANTITIES[name])
        placeable.extend(data.AREA_ITEMS)
        placeable.extend(
            reward for reward in data.PACKAGE_REWARD_ITEMS if self._item_enabled(reward)
        )

        active_locations = sum(
            1 for name in LOCATION_NAME_TO_ID if self._location_enabled(name)
        )
        # A new game starts with only the first Rosenberg mission free, so the
        # sphere-0 room comes from the free-roam collectibles (hidden packages
        # and, later, the other pickup classes). With every collectible class
        # off the pool is all-progression with a one-location sphere 0, and the
        # spine chain makes it unplaceable. In that case grant the east-island
        # spine strands at the start: this opens a large sphere 0 and leaves
        # ample filler slack, keeping the seed solvable. A real multiworld would
        # instead place those unlocks in other worlds.
        if self._free_start_location_count() < MINIMUM_SPHERE_ZERO:
            for giver in self._opening_grant_givers():
                name = data.progressive_item_name(giver)
                while name in placeable:
                    placeable.remove(name)
                    self.multiworld.push_precollected(self.create_item(name))

        overflow = len(placeable) - active_locations
        if overflow > 0:
            # More progression and useful items than checks. Not reachable with
            # the current classes and item math; guard rather than misfill.
            raise OptionError(
                f"{self.game}: {len(placeable)} progression and useful items but "
                f"only {active_locations} checks this seed. Enable another check "
                "class so the items have reachable homes."
            )

        pool = [self.create_item(name) for name in placeable]
        pool.extend(
            self.create_item(self.get_filler_item_name())
            for _ in range(active_locations - len(pool))
        )
        self.multiworld.itempool += pool

    def _opening_grant_givers(self) -> list[str]:
        # The east-island spine, in dependency order: the sphere-0 giver first,
        # then each spine giver that stays on the start island (the mainland
        # ones cannot open until Mainland Access, so granting them would not
        # enlarge sphere 0). Granting whole strands here both opens the missions
        # and creates filler slack.
        return [data.SPHERE_ZERO_GIVER] + [
            giver for giver in data.SPINE_PREREQUISITES
            if giver not in data.MAINLAND_GIVERS
        ]

    def _free_start_location_count(self) -> int:
        # Locations reachable on a new game with no item: enabled start-region
        # locations that carry no access rule. This is the sphere-0 room the
        # fill has to work with.
        return sum(
            1 for name, region in LOCATION_REGIONS.items()
            if region == data.REGION_VICE_CITY
            and self._location_enabled(name)
            and name not in rules.LOCATION_RULES
        )

    def set_rules(self) -> None:
        from worlds.generic.Rules import set_rule
        for location_name, rule in rules.LOCATION_RULES.items():
            if not self._location_enabled(location_name):
                continue
            set_rule(self.multiworld.get_location(location_name, self.player), self._bind(rule))
        self.multiworld.completion_condition[self.player] = self._completion_condition()

    def _bind(self, rule: Callable[[CollectionState, int], bool]) -> Callable[[CollectionState], bool]:
        player = self.player
        return lambda state: rule(state, player)

    def _completion_condition(self) -> Callable[[CollectionState], bool]:
        player = self.player
        goal = self.options.goal
        if goal == Goal.option_hidden_packages:
            need = self.options.hidden_packages_required.value
            package_names = locations.PACKAGE_NAMES
            return lambda state: sum(
                state.can_reach_location(name, player) for name in package_names
            ) >= need
        if goal == Goal.option_hundred_percent:
            package_names = locations.PACKAGE_NAMES
            return lambda state: (
                state.can_reach_location(data.FINAL_MISSION, player)
                and all(state.can_reach_location(name, player) for name in package_names)
            )
        return lambda state: state.can_reach_location(data.FINAL_MISSION, player)
