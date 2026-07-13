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
        pool: list[GTAViceCityItem] = []
        for giver in data.STORY_GIVERS:
            name = data.progressive_item_name(giver)
            pool.extend(self.create_item(name) for _ in range(ITEM_QUANTITIES[name]))
        pool.extend(self.create_item(area_item) for area_item in data.AREA_ITEMS)
        pool.extend(
            self.create_item(reward)
            for reward in data.PACKAGE_REWARD_ITEMS
            if self._item_enabled(reward)
        )

        active_locations = sum(
            1 for name in LOCATION_NAME_TO_ID if self._location_enabled(name)
        )
        delta = active_locations - len(pool)
        if delta < 0:
            raise OptionError(
                f"{self.game}: {len(pool)} progression and useful items but only "
                f"{active_locations} checks this seed. Enable more check classes "
                "so the progression items have reachable homes."
            )
        pool.extend(self.create_item(self.get_filler_item_name()) for _ in range(delta))
        self.multiworld.itempool += pool

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
