"""Grand Theft Auto: Vice City for Archipelago.

Hand-written world. Content tables live in data.py; the item and location id
maps in items.py and locations.py; the access-rule predicates in rules.py; the
region graph in regions.py. There is no code-generation step.

Check classes: story missions (always on), hidden packages, rampages, stunt
jumps, emergency vehicle milestones, side events, robbable stores, and
properties (purchases plus venue mission strands), each optional behind a
toggle. The bridge client that talks to the game mod is the client subpackage,
registered as a launcher component below.
"""

from __future__ import annotations

import typing
from collections.abc import Callable

import settings
from BaseClasses import CollectionState, Item, Location, Region
from Options import OptionError
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components
from worlds.LauncherComponents import launch as launch_component

from . import data, regions, rules, scm
from .items import FILLER_NAMES, ITEM_CLASSIFICATIONS, ITEM_GROUPS, ITEM_NAME_TO_ID, ITEM_QUANTITIES
from .locations import CLASS_TOGGLE, LOCATION_GROUPS, LOCATION_NAME_TO_ID, LOCATION_REGIONS, LOCATION_TOGGLE
from .options import CHECK_CLASS_OPTIONS, Goal, GTAViceCityOptions

# Below this many free-at-start locations, the world grants the east-island
# spine strands so an all-progression pool (a collectible-free seed) can still
# fill.
MINIMUM_SPHERE_ZERO = 10


def launch_client(*args: str) -> None:
    # Lazy import so registering the component does not pull CommonClient and
    # its dependencies into every generation run.
    from .client.context import launch
    launch_component(launch, name="GTA Vice City Client", args=args)


components.append(Component(
    "GTA Vice City Client",
    func=launch_client,
    component_type=Type.CLIENT,
    game_name="Grand Theft Auto Vice City",
    supports_uri=True,
    description="Connect to a multiworld and bridge to the GTA Vice City mod.",
))


class GTAViceCitySettings(settings.Group):
    class InstallFolder(settings.UserFolderPath):
        """The GTA Vice City install folder, the one holding gta-vc.exe. The
        client launches the game from here on connect and on /play. Blank by
        default; the client offers a folder picker on first connect and saves
        the choice here. Use forward slashes."""
        description = "GTA Vice City install folder"
        required = False

    class AutoLaunchGame(settings.Bool):
        """Launch gta-vc.exe automatically when the client connects, once per
        client session. On by default; set false to launch it yourself or with
        the /play command."""

    class IsolateSaves(settings.Bool):
        """Keep each Archipelago seed's GTA Vice City saves in their own set,
        apart from your normal saves, swapped in when the client connects. On by
        default. Bring your normal saves back with the client's /restore
        command. Only the save files move; controls and display settings stay."""

    class AutoInstallMod(settings.Bool):
        """Compare the mod bundled in this apworld against the install when the
        client connects, and copy it in if it differs, before the game launches.
        On by default. Set false to manage the mod yourself with the /installmod
        command. You still supply Ultimate ASI Loader and CLEO."""

    install_folder: InstallFolder = InstallFolder("")
    auto_launch_game: AutoLaunchGame | bool = True
    isolate_saves: IsolateSaves | bool = True
    auto_install_mod: AutoInstallMod | bool = True


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
    settings: typing.ClassVar[GTAViceCitySettings]

    # The Universal Tracker regenerates this world from slot_data alone (see
    # interpret_slot_data), so it needs no yaml on hand.
    ut_can_gen_without_yaml = True

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID
    item_name_groups = ITEM_GROUPS
    location_name_groups = LOCATION_GROUPS

    @staticmethod
    def interpret_slot_data(slot_data: dict) -> dict:
        """Universal Tracker hook. Returning the slot_data asks the tracker to
        regenerate this world with it passed through, so generate_early restores
        the played seed's options instead of the tracker's defaults."""
        return slot_data

    def _restore_options(self, slot_data: dict) -> None:
        # Rebuild the world-shaping options from a played seed's slot_data, so a
        # tracker regeneration matches that seed's locations and pool.
        options = self.options
        options.goal.value = type(options.goal).options[slot_data["goal"]]
        options.hidden_packages_required.value = int(slot_data["hidden_packages_required"])
        options.death_link.value = int(bool(slot_data["death_link"]))
        if "shuffle_emergency_rewards" in slot_data:
            options.shuffle_emergency_rewards.value = int(bool(slot_data["shuffle_emergency_rewards"]))
        for name in CHECK_CLASS_OPTIONS:
            if name in slot_data:
                getattr(options, name).value = int(bool(slot_data[name]))

    def generate_early(self) -> None:
        # A Universal Tracker regeneration runs on its own seed and passes the
        # played seed's slot_data through; replay its options instead of the
        # tracker's defaults.
        passthrough = getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game)
        if passthrough is not None:
            self._restore_options(passthrough)
            return
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
        # Story missions carry no toggle and are always on. Every other class
        # is enabled by its option.
        option_attr = LOCATION_TOGGLE.get(name)
        if option_attr is None:
            return True
        return bool(getattr(self.options, option_attr).value)

    def _class_enabled(self, class_key: str) -> bool:
        # Story missions are always on; every optional class is enabled by its
        # option. Governs whether a progressive strand's items enter the pool.
        option_attr = CLASS_TOGGLE.get(class_key)
        if option_attr is None:
            return True
        return bool(getattr(self.options, option_attr).value)

    def _item_enabled(self, name: str) -> bool:
        if name in data.PACKAGE_REWARD_ITEMS:
            return bool(self.options.enable_hidden_packages.value)
        if name in data.EMERGENCY_REWARD_ITEMS:
            return bool(self.options.enable_emergency_vehicles.value
                        and self.options.shuffle_emergency_rewards.value)
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
        for strand, (class_key, _missions) in data.progressive_strands().items():
            if not self._class_enabled(class_key):
                continue
            name = data.progressive_item_name(strand)
            placeable.extend([name] * ITEM_QUANTITIES[name])
        placeable.extend(data.AREA_ITEMS)
        placeable.extend(
            reward for reward in data.PACKAGE_REWARD_ITEMS if self._item_enabled(reward)
        )
        placeable.extend(
            reward for reward in data.EMERGENCY_REWARD_ITEMS if self._item_enabled(reward)
        )
        if self.options.goal == Goal.option_hidden_packages:
            # The hunt: one Hidden Package macguffin per physical package,
            # scattered across the multiworld. The goal counts how many are
            # received, so a physical package pickup stays an ordinary check.
            placeable.extend([data.HIDDEN_PACKAGE_ITEM] * data.HIDDEN_PACKAGE_COUNT)

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

    def fill_slot_data(self) -> dict:
        # The client reads this on connect and configures the ASI from it: how
        # to turn received items into count-global writes (item_globals), the
        # one-shot consumable effects (item_effects), the config flags that tell
        # the SCM which reward groups are shuffled (config_globals), which
        # completion globals to poll for checks, plus the goal so the client
        # knows when to report it. The check-class toggles ride along so the
        # Universal Tracker can regenerate the world from slot_data alone. JSON
        # object keys are strings.
        return {
            "goal": self.options.goal.current_key,
            "hidden_packages_required": self.options.hidden_packages_required.value,
            # The client counts received copies of this item to detect the
            # hidden-packages hunt goal (the ASI has no part in it).
            "hidden_package_item_id": ITEM_NAME_TO_ID[data.HIDDEN_PACKAGE_ITEM],
            # The client watches for this location being checked to detect the
            # final-mission goal; the 100 percent goal needs no id (it waits for
            # every location).
            "final_location_id": LOCATION_NAME_TO_ID[data.FINAL_MISSION],
            "death_link": bool(self.options.death_link.value),
            "shuffle_emergency_rewards": bool(self.options.shuffle_emergency_rewards.value),
            "item_globals": {
                str(item_id): global_index
                for item_id, global_index in scm.item_globals().items()
            },
            "item_effects": {
                str(item_id): effect for item_id, effect in scm.item_effects().items()
            },
            "config_globals": {
                str(global_index): value
                for global_index, value in scm.config_flags(
                    bool(self.options.enable_hidden_packages.value),
                    bool(self.options.enable_emergency_vehicles.value
                         and self.options.shuffle_emergency_rewards.value),
                ).items()
            },
            "completion_watch": {
                str(global_index): location_id
                for global_index, location_id in scm.completion_watch().items()
            },
            # Only when the class is enabled: with packages off their locations
            # do not exist, so the ASI must not detect or report them.
            "package_coords": {
                str(global_index): coord
                for global_index, coord in scm.package_coords().items()
            } if self.options.enable_hidden_packages.value else {},
            **{name: bool(getattr(self.options, name).value) for name in CHECK_CLASS_OPTIONS},
        }

    def _completion_condition(self) -> Callable[[CollectionState], bool]:
        player = self.player
        goal = self.options.goal
        if goal == Goal.option_hidden_packages:
            # A hunt on received macguffins, not on collecting your own packages:
            # the goal is how many Hidden Package items you receive, from anywhere
            # in the multiworld.
            need = self.options.hidden_packages_required.value
            return lambda state: state.has(data.HIDDEN_PACKAGE_ITEM, player, need)
        if goal == Goal.option_hundred_percent:
            # The game's 100 percent requires every stat contributor, and
            # generation only allows this goal when every check class is on, so
            # completion is every enabled check reachable.
            enabled = [
                name for name in LOCATION_NAME_TO_ID if self._location_enabled(name)
            ]
            return lambda state: all(
                state.can_reach_location(name, player) for name in enabled
            )
        return lambda state: state.can_reach_location(data.FINAL_MISSION, player)
