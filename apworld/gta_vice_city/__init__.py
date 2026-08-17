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
from .items import GENERAL_FILLER_NAMES, ITEM_CLASSIFICATIONS, ITEM_GROUPS, ITEM_NAME_TO_ID, ITEM_QUANTITIES
from .locations import CLASS_TOGGLE, LOCATION_GROUPS, LOCATION_NAME_TO_ID, LOCATION_REGIONS, LOCATION_TOGGLE
from .options import CHECK_CLASS_OPTIONS, Goal, GTAViceCityOptions

# How many checks a solo seed must leave reachable on a new game. Nothing is
# granted at the start to widen a narrow seed, so a sphere 0 of one check would
# leave the fill chaining strictly through that check, which it survives only
# by luck of the seed. Nothing else about the pool predicts which narrow seeds
# fill, so the count itself is the guard. Measured against
# scripts/fuzz_fill.py, which generates solo.
MINIMUM_SPHERE_ZERO = 2


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

    # The starting radio station's index into data.RADIO_STATION_ITEMS, chosen
    # in generate_early when the randomize option is on; None when it is off.
    radio_start_station: int | None = None

    # The ambient pickup layout as a permutation of data.PICKUP_SLOTS indices:
    # slot i shows the model and ammo of vanilla slot pickup_permutation[i].
    # Rolled in generate_early when randomize_pickups is on; None when off.
    pickup_permutation: list[int] | None = None

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
        if "randomize_radio_stations" in slot_data:
            options.randomize_radio_stations.value = int(bool(slot_data["randomize_radio_stations"]))
        if "shuffle_minimap" in slot_data:
            options.shuffle_minimap.value = int(bool(slot_data["shuffle_minimap"]))
        if "randomize_pickups" in slot_data:
            options.randomize_pickups.value = int(bool(slot_data["randomize_pickups"]))
        if "ability_locks" in slot_data:
            options.ability_locks.value = set(slot_data["ability_locks"])
        if "trap_percentage" in slot_data:
            options.trap_percentage.value = int(slot_data["trap_percentage"])
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
            self._choose_radio_start(passthrough)
            self._choose_pickup_permutation(passthrough)
            return
        options = self.options
        self._choose_radio_start(None)
        self._choose_pickup_permutation(None)
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

    def _choose_radio_start(self, passthrough: dict | None) -> None:
        # The starting radio station, one of the nine at random. Fixed here,
        # before the pool builds, and carried in slot_data so a tracker
        # regeneration replays the seed's choice instead of rerolling.
        if not self.options.randomize_radio_stations:
            self.radio_start_station = None
            return
        restored = (passthrough or {}).get("radio_start_station")
        self.radio_start_station = (
            int(restored) if restored is not None
            else self.random.randrange(len(data.RADIO_STATION_ITEMS))
        )

    def _choose_pickup_permutation(self, passthrough: dict | None) -> None:
        # The ambient pickup layout. Fixed here, before the pool builds, and
        # carried in slot_data so a tracker regeneration replays the seed's
        # layout instead of rerolling. The bribe model breaks the in-shop cost
        # lookup, so any bribe the shuffle drops on a shop-type slot trades
        # places with a non-bribe on a non-shop slot.
        if not self.options.randomize_pickups:
            self.pickup_permutation = None
            return
        restored = (passthrough or {}).get("pickup_permutation")
        if restored is not None:
            self.pickup_permutation = [int(index) for index in restored]
            return
        slots = data.PICKUP_SLOTS
        permutation = list(range(len(slots)))
        self.random.shuffle(permutation)
        for slot_index in range(len(slots)):
            if (slots[slot_index][3] == data.PICKUP_SHOP_TYPE
                    and slots[permutation[slot_index]][4] == data.PICKUP_BRIBE_MODEL):
                candidates = [
                    other for other in range(len(slots))
                    if slots[other][3] != data.PICKUP_SHOP_TYPE
                    and slots[permutation[other]][4] != data.PICKUP_BRIBE_MODEL
                ]
                other = self.random.choice(candidates)
                permutation[slot_index], permutation[other] = (
                    permutation[other], permutation[slot_index])
        self.pickup_permutation = permutation

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
        if name in data.PROPERTY_OWNERSHIP_ITEMS:
            return bool(self.options.enable_properties.value)
        if name in data.ABILITY_ITEM_KEY:
            return data.ABILITY_ITEM_KEY[name] in self.options.ability_locks.value
        return True

    def _ability_lock_keys(self) -> frozenset[str]:
        return frozenset(self.options.ability_locks.value)

    def _location_rules(self) -> dict[str, rules.RulePredicate]:
        # Built per world: the finale missions carry the asset prerequisite
        # only while the properties class is on (its items are in the pool),
        # and ability terms exist only for the selected ability_locks keys.
        return rules.build_location_rules(
            bool(self.options.enable_properties.value),
            self._ability_lock_keys(),
        )

    def create_item(self, name: str) -> GTAViceCityItem:
        return GTAViceCityItem(
            name, ITEM_CLASSIFICATIONS[name], ITEM_NAME_TO_ID[name], self.player,
        )

    def get_filler_item_name(self) -> str:
        # Generic filler only, never cash: the reward-mirror cash is placed by
        # create_items, and AP's generic filler path must not reintroduce money.
        return self.multiworld.random.choice(GENERAL_FILLER_NAMES)

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
        placeable.extend(
            ownership for ownership in data.PROPERTY_OWNERSHIP_ITEMS
            if self._item_enabled(ownership)
        )
        if self.options.randomize_radio_stations:
            # One random station is the start (precollected, so it arrives as
            # starting inventory); the other eight are useful pool items. In
            # game only unlocked stations play.
            for index, name in enumerate(data.RADIO_STATION_ITEMS):
                if index == self.radio_start_station:
                    self.multiworld.push_precollected(self.create_item(name))
                else:
                    placeable.append(name)
        if self.options.shuffle_minimap:
            # The minimap starts hidden; the item brings the radar disc back.
            placeable.append(data.MINIMAP_ITEM)
        for key in sorted(self.options.ability_locks.value):
            # Each selected key locks its ability at new game and shuffles the
            # unlocking item(s) into the pool. Sorted so the pool order is
            # deterministic (the option value is a set).
            placeable.extend(data.ABILITY_LOCK_ITEMS[key])
        if self.options.goal == Goal.option_hidden_packages:
            # The hunt: one Hidden Package macguffin per physical package,
            # scattered across the multiworld. The goal counts how many are
            # received, so a physical package pickup stays an ordinary check.
            placeable.extend([data.HIDDEN_PACKAGE_ITEM] * data.HIDDEN_PACKAGE_COUNT)

        active_locations = sum(
            1 for name in LOCATION_NAME_TO_ID if self._location_enabled(name)
        )
        overflow = len(placeable) - active_locations
        if overflow > 0:
            # More progression and useful items than checks. Not reachable with
            # the current classes and item math; guard rather than misfill.
            raise OptionError(
                f"{self.game}: {len(placeable)} progression and useful items but "
                f"only {active_locations} checks this seed. Enable another check "
                "class so the items have reachable homes."
            )
        self._guard_fill_room()

        pool = [self.create_item(name) for name in placeable]
        # The remaining slots are filler, drawn from the reward mirror: each
        # enabled check offers one entry worth the vanilla cash it would have paid
        # (None where it paid nothing). There are more mirror entries than filler
        # slots, since progression and useful items occupy some checks, so a
        # random sample fills the slots. That keeps the reward distribution while
        # bounding total money to the mirror. A trap_percentage share of the slots
        # become traps instead; traps only ever replace filler, so they never
        # crowd out progression or useful items.
        mirror = self._reward_mirror()
        filler_slots = active_locations - len(pool)
        trap_slots = filler_slots * self.options.trap_percentage.value // 100
        pool.extend(self.create_item(self._random_trap()) for _ in range(trap_slots))
        for entry in self.multiworld.random.sample(mirror, filler_slots - trap_slots):
            name = entry if entry is not None else self.multiworld.random.choice(GENERAL_FILLER_NAMES)
            pool.append(self.create_item(name))
        self.multiworld.itempool += pool

    def _reward_mirror(self) -> list[str | None]:
        # One filler entry per enabled check, mirroring the vanilla cash it would
        # have paid: a cash item name, or None for a check that paid nothing. The
        # same enabled-location predicate as create_regions, so it stays one entry
        # per location this seed.
        return [
            data.mirror_item(name)
            for name in LOCATION_NAME_TO_ID
            if self._location_enabled(name)
        ]

    def _random_trap(self) -> str:
        # The trap types are equally weighted, so each filler-replacing slot
        # draws one uniformly at random.
        return self.multiworld.random.choice(data.TRAP_ITEMS)

    def _guard_fill_room(self) -> None:
        # A new game opens the sphere-zero giver's first mission plus whatever
        # start-region check the seed's classes leave unruled. A class narrows
        # the start two ways: a lock puts its checks behind an item, and a class
        # whose checks all sit on the mainland (every stunt jump does) puts none
        # in the start region to begin with.
        #
        # Only a solo seed is refused for it. Other worlds lend the fill their
        # locations to place this world's items into and their items to fill
        # this world's one open check with, and refusing there would abort
        # everyone's generation over one slot's options. A multiworld of narrow
        # slots alone still gives the fill little room, but it surfaces as a
        # fill error rather than an unbeatable seed, since the fill enforces
        # logic either way.
        if self.multiworld.players > 1:
            return
        free_start_locations = self._free_start_location_count()
        if free_start_locations < MINIMUM_SPHERE_ZERO:
            raise OptionError(
                f"{self.game}: only {free_start_locations} check is reachable on "
                "a new game with these options, too narrow for the fill to chain "
                "through. Enable a class with unlocked checks on the start "
                "island, hidden packages being the one no ability term touches, "
                "or drop a lock key."
            )

    def _free_start_location_count(self) -> int:
        # Locations reachable on a new game with no item: enabled start-region
        # locations that carry no access rule. This is the sphere-0 room the
        # fill has to work with. Built from this world's own rules, so ability
        # terms (a stunt jump needing Land Vehicles) count as not free.
        location_rules = self._location_rules()
        return sum(
            1 for name, region in LOCATION_REGIONS.items()
            if region == data.REGION_VICE_CITY
            and self._location_enabled(name)
            and name not in location_rules
        )

    def set_rules(self) -> None:
        from worlds.generic.Rules import set_rule
        location_rules = self._location_rules()
        for location_name, rule in location_rules.items():
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
            "randomize_radio_stations": bool(self.options.randomize_radio_stations.value),
            # The starting station's index (None when the option is off), so a
            # tracker regeneration precollects the same station.
            "radio_start_station": self.radio_start_station,
            "shuffle_minimap": bool(self.options.shuffle_minimap.value),
            "randomize_pickups": bool(self.options.randomize_pickups.value),
            # The selected ability lock keys (sorted; JSON has no sets), so a
            # tracker regeneration rebuilds the same pool and rules. The lock
            # flags themselves reach the ASI through config_globals.
            "ability_locks": sorted(self.options.ability_locks.value),
            # The permutation itself (None when off), so a tracker regeneration
            # replays the seed's pickup layout instead of rerolling it.
            "pickup_permutation": self.pickup_permutation,
            # The target layout the ASI enforces: per ambient slot its position
            # and pickup type plus the permuted model and ammo. Empty when off,
            # so the ASI leaves every pickup vanilla.
            "pickup_layout": self._pickup_layout(),
            "trap_percentage": self.options.trap_percentage.value,
            "item_globals": {
                str(item_id): global_index
                for item_id, global_index in scm.item_globals().items()
            },
            "item_effects": {
                str(item_id): effect for item_id, effect in scm.item_effects().items()
            },
            "config_globals": {
                str(global_index): value
                for global_index, value in self._config_globals().items()
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

    def _pickup_layout(self) -> list[list[float | int]]:
        # One row per ambient slot: x, y, z, pickup type, then the model and
        # ammo the permutation assigns to that spot. The ASI matches rows to
        # pickup pool entries by position and type and rewrites the entries
        # whose model differs.
        if self.pickup_permutation is None:
            return []
        layout: list[list[float | int]] = []
        for slot_index, source_index in enumerate(self.pickup_permutation):
            x, y, z, pickup_type, _model, _ammo = data.PICKUP_SLOTS[slot_index]
            model, ammo = data.PICKUP_SLOTS[source_index][4:6]
            layout.append([x, y, z, pickup_type, model, ammo])
        return layout

    def write_spoiler(self, spoiler_handle: typing.TextIO) -> None:
        # The pickup layout is decided at generation, so the spoiler log lists
        # it: each spot named by its vanilla item, then what stands there now.
        if self.pickup_permutation is None:
            return
        spoiler_handle.write(
            f"\nAmbient pickups ({self.multiworld.player_name[self.player]}):\n")
        for slot_index, source_index in enumerate(self.pickup_permutation):
            x, y, z, _pickup_type, vanilla_model, _ammo = data.PICKUP_SLOTS[slot_index]
            model = data.PICKUP_SLOTS[source_index][4]
            spoiler_handle.write(
                f"{data.PICKUP_MODEL_NAMES[vanilla_model]} at ({x}, {y}, {z}): "
                f"{data.PICKUP_MODEL_NAMES[model]}\n")

    def _config_globals(self) -> dict[int, int]:
        # The reward-group config flags, the class-cash flags gating each
        # enabled class's one-time completion cash, the ability lock flags the
        # ASI enforces per frame, plus the vanilla-collapse
        # writes when the properties class is off: with the ownership items
        # out of the pool, the client stamps the venue unlock and ownership
        # globals so every static property gate reduces to purchase-only, the
        # vanilla semantics the toggle invariant demands.
        flags = scm.config_flags(
            bool(self.options.enable_hidden_packages.value),
            bool(self.options.enable_emergency_vehicles.value
                 and self.options.shuffle_emergency_rewards.value),
            bool(self.options.randomize_radio_stations.value),
            bool(self.options.shuffle_minimap.value),
        )
        flags.update(scm.class_cash_flags(
            bool(self.options.enable_side_events.value),
            bool(self.options.enable_stunt_jumps.value),
            bool(self.options.enable_rampages.value),
            bool(self.options.enable_properties.value),
        ))
        flags.update(scm.ability_lock_flags(self._ability_lock_keys()))
        if not self.options.enable_properties.value:
            flags.update(scm.properties_vanilla_globals())
        return flags

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
