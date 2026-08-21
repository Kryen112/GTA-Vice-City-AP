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
from collections import Counter
from collections.abc import Callable

import settings
from BaseClasses import CollectionState, Item, ItemClassification, Location, Region
from Options import OptionError
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components
from worlds.LauncherComponents import launch as launch_component

from . import data, regions, rules, scm
from .items import (
    DISTRICT_CONTENT_NAMES,
    GENERAL_FILLER_NAMES,
    ITEM_CLASSIFICATIONS,
    ITEM_GROUPS,
    ITEM_NAME_TO_ID,
    ITEM_QUANTITIES,
)
from .locations import CLASS_TOGGLE, LOCATION_GROUPS, LOCATION_NAME_TO_ID, LOCATION_REGIONS, LOCATION_TOGGLE
from .options import CHECK_CLASS_OPTIONS, Goal, GTAViceCityOptions

# How many checks a seed must leave reachable on a new game before it needs no
# help. Nothing is granted at the start to widen a narrow seed, so a sphere 0 of
# one check would leave the fill chaining strictly through that check, which it
# survives only by luck of the seed. Nothing about the pool predicts which narrow
# seeds fill, so the count is what decides that a seed needs an opening item
# directed into it, and, for a solo seed with no opener to direct, the refusal.
# Measured against scripts/fuzz_fill.py, which generates solo.
MINIMUM_SPHERE_ZERO = 2

# How many checks the directed opening item must leave reachable before a narrow
# seed is widened instead of refused. Directing spends the fill's own choice of
# what goes in the only open check, so a weak opener is worse than none at all.
# Measured on the widest lock configuration at 60 seeds: leaving the fill alone
# fills 53 seeds, an opener leaving two checks open fills 31 to 33, and one
# leaving this many or more fills 60. This is the lowest value the ladder
# validates; three was never measured, so the test below it holds the refusal
# down to two and no further. Measured against scripts/fuzz_fill.py.
MINIMUM_DIRECTED_SPHERE_ZERO = 4


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

    # The lock items Tommy starts holding, one drawn at random from the selected
    # ability keys and one from the selected content keys. Chosen in
    # generate_early when the matching option is on; None when it is off or when
    # that family selected no key.
    starting_ability_item: str | None = None
    starting_content_item: str | None = None

    # The content item the fill is told to place in a check a new game reaches,
    # chosen in generate_early and ahead of the starting draws so they cannot
    # take it. None when the start is wide enough to chain through on its own,
    # and None as well when it is not but no held class opens enough of the
    # start island to be worth directing, which is the case the refusal covers.
    directed_opening_item: str | None = None

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
        if "split_mainland_access" in slot_data:
            options.split_mainland_access.value = int(
                bool(slot_data["split_mainland_access"]))
        if "ability_locks" in slot_data:
            options.ability_locks.value = set(slot_data["ability_locks"])
        if "content_locks" in slot_data:
            options.content_locks.value = set(slot_data["content_locks"])
        if "split_content_locks" in slot_data:
            # Without this a regeneration rebuilds a split seed's rules against
            # the whole-class items, which the pool does not hold: every
            # collectible would read as gated on an item that never arrives.
            options.split_content_locks.value = int(slot_data["split_content_locks"])
        if "starting_ability_unlock" in slot_data:
            options.starting_ability_unlock.value = int(bool(slot_data["starting_ability_unlock"]))
        if "starting_content_unlock" in slot_data:
            options.starting_content_unlock.value = int(bool(slot_data["starting_content_unlock"]))
        if "trap_percentage" in slot_data:
            options.trap_percentage.value = int(slot_data["trap_percentage"])
        for name in CHECK_CLASS_OPTIONS:
            if name in slot_data:
                getattr(options, name).value = int(bool(slot_data[name]))

    def _tracker_passthrough(self) -> dict | None:
        # The played seed's slot_data while a Universal Tracker regeneration
        # runs, None during an ordinary generation. Every place that has to
        # know reads it here, so the tests for it cannot drift apart.
        return getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game)

    def generate_early(self) -> None:
        # A Universal Tracker regeneration runs on its own seed and passes the
        # played seed's slot_data through; replay its options instead of the
        # tracker's defaults.
        passthrough = self._tracker_passthrough()
        if passthrough is not None:
            self._restore_options(passthrough)
            self._choose_radio_start(passthrough)
            self._choose_pickup_permutation(passthrough)
            self._choose_starting_unlocks(passthrough)
            return
        options = self.options
        self._choose_radio_start(None)
        self._choose_pickup_permutation(None)
        self._choose_directed_opener()
        self._choose_starting_unlocks(None)
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

    def _choose_starting_unlocks(self, passthrough: dict | None) -> None:
        # The lock items Tommy already holds. Fixed here, before the pool builds,
        # and carried in slot_data so a tracker regeneration replays the seed's
        # draw instead of rerolling. A restored name that the restored keys no
        # longer offer is dropped, so mismatched slot_data cannot ask create_items
        # for an item that is not in the pool.
        replaying = passthrough is not None
        self.starting_ability_item = self._draw_starting_unlock(
            bool(self.options.starting_ability_unlock.value),
            [item for key in sorted(self.options.ability_locks.value)
             for item in data.ABILITY_LOCK_ITEMS[key]],
            (passthrough or {}).get("starting_ability_item"),
            replaying,
        )
        # The directed opener is left out of the draw. A narrow seed needs it
        # in the pool for the fill to place, and with heavy ability locks the
        # held packages are often the only class that opens the start at all, so
        # a draw free to take it would decide whether the seed generates.
        self.starting_content_item = self._draw_starting_unlock(
            bool(self.options.starting_content_unlock.value),
            [name for name in self._content_items()
             if name != self.directed_opening_item],
            (passthrough or {}).get("starting_content_item"),
            replaying,
        )

    def _draw_starting_unlock(
        self, enabled: bool, eligible: list[str], restored: str | None,
        replaying: bool,
    ) -> str | None:
        # One item out of those the seed's own lock keys put in the pool. The
        # draw is over items, not keys, so the vehicles key hands over one of
        # land, sea, or air rather than all three.
        #
        # A replay never rolls. The played seed can have drawn nothing with the
        # option on and a key selected, since the item a narrow seed directs is
        # kept out of the draw and can be the only one there is, and a restored
        # None reads the same as a field the slot_data never carried. Rolling on
        # either would hand the tracker an item the seed left in its pool.
        if not enabled or not eligible:
            return None
        if replaying:
            return restored if restored in eligible else None
        return self.random.choice(eligible)

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
        if name in data.CONTENT_ITEM_KEY or name in DISTRICT_CONTENT_NAMES:
            # A content lock rides its own key, never the class toggle: a key
            # selected on a disabled class still holds the content in game, so
            # the item that releases it still belongs in the pool. Which of the
            # three granularities' items those are is content_items' answer, and
            # the item table holds all of them, so membership is the test.
            return name in set(self._content_items())
        return True

    def _split_content_locks(self) -> int:
        return int(self.options.split_content_locks.value)

    def _content_items(self) -> list[str]:
        # The content items this seed puts in the pool, at its granularity.
        # Deterministic despite content_locks being a set: content_items walks
        # CONTENT_ITEMS and DISTRICTS, both fixed orders, rather than the keys.
        return data.content_items(
            frozenset(self.options.content_locks.value), self._split_content_locks())

    def _ability_lock_keys(self) -> frozenset[str]:
        return frozenset(self.options.ability_locks.value)

    def _content_lock_keys(self) -> frozenset[str]:
        return frozenset(self.options.content_locks.value)

    def _active_lock_items(self) -> frozenset[str]:
        # The lock items a seed actually has, which is what decides whether a
        # term binds. Region routes name a vehicle, and that term only exists
        # while the vehicles key is selected.
        return frozenset(
            item for key in self._ability_lock_keys()
            for item in data.ABILITY_LOCK_ITEMS[key]
        )

    def _location_rules(self) -> dict[str, rules.RulePredicate]:
        # Built per world: the finale missions carry the asset prerequisite
        # only while the properties class is on (its items are in the pool),
        # a lock term exists only for the selected ability_locks and
        # content_locks keys, and the mainland is reached by one item or by any
        # one crossing depending on split_mainland_access.
        return rules.build_location_rules(
            bool(self.options.enable_properties.value),
            self._ability_lock_keys(),
            self._content_lock_keys(),
            bool(self.options.split_mainland_access.value),
            self._split_content_locks(),
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
        entry_rules = regions.build_region_entry_rules(
            bool(self.options.split_mainland_access.value),
            self._active_lock_items())
        for region_name, region in by_name.items():
            if region_name == regions.START_REGION:
                continue
            rule = entry_rules.get(region_name)
            if rule is None:
                start.connect(region)
            else:
                start.connect(region, rule=self._bind(rule))

        # One event per mission the audit uses as a way onto an island. Passing
        # a mission is not something a seed can place, so it arrives as an event
        # item on an event location that sits in the mission's own region and
        # carries the mission's own rule. The region graph then reads the event
        # like any other item, and the sweep can only collect it once the mission
        # is genuinely reachable, so a route through an island's own missions
        # cannot open that island for itself.
        for mission in data.ROUTE_MISSIONS:
            event = GTAViceCityLocation(
                self.player, data.mission_event_name(mission), None,
                by_name[LOCATION_REGIONS[mission]],
            )
            event.place_locked_item(GTAViceCityItem(
                data.mission_passed_item_name(mission),
                ItemClassification.progression, None, self.player,
            ))
            by_name[LOCATION_REGIONS[mission]].locations.append(event)

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
        # Mainland Access and the four crossings are alternatives: the option
        # picks which reaches the mainland, and the other never enters the pool.
        # Kept in AREA_ITEMS order so the pool reads the same as the id table.
        mainland_items = (
            data.MAINLAND_CROSSING_ITEMS if self.options.split_mainland_access
            else [data.AREA_ITEM_BY_REGION[data.REGION_MAINLAND]]
        )
        placeable.extend(name for name in data.AREA_ITEMS
                         if name in {*mainland_items,
                                     data.AREA_ITEM_BY_REGION[data.REGION_STARFISH]})
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
        # Each selected key holds its class at new game and shuffles the items
        # that release it into the pool, whether or not that class is also a
        # check class this seed. One item for the class, or one per district, or
        # one per class per district, as split_content_locks says.
        placeable.extend(self._content_items())
        for chosen in (self.starting_ability_item, self.starting_content_item):
            if chosen is None:
                continue
            # Starting inventory, so it leaves the pool rather than adding to it:
            # one copy of a lock item exists and Tommy already holds it. The
            # draw only ever names an item the keys above placed, so the removal
            # cannot miss.
            placeable.remove(chosen)
            self.multiworld.push_precollected(self.create_item(chosen))
        if self.options.goal == Goal.option_hidden_packages:
            # The hunt: one Package Fragment per physical package, scattered
            # across the multiworld. The goal counts how many are received, so
            # a physical package pickup stays an ordinary check.
            placeable.extend([data.PACKAGE_FRAGMENT_ITEM] * data.HIDDEN_PACKAGE_COUNT)

        active_locations = sum(
            1 for name in LOCATION_NAME_TO_ID if self._location_enabled(name)
        )
        overflow = len(placeable) - active_locations
        if overflow > 0:
            # More progression and useful items than checks. Filler is what
            # gives way as the item count grows, and by here there is none left
            # to give, so only the options can resolve it. Splitting the content
            # locks is the widest of them, turning five items into 42, so it is
            # named when it is on.
            advice = ("Widen the seed with another check class, or narrow "
                      "split_content_locks")
            if not self.options.split_content_locks.value:
                advice = "Enable another check class"
            raise OptionError(
                f"{self.game}: {len(placeable)} progression and useful items but "
                f"only {active_locations} checks this seed. {advice} so the items "
                "have reachable homes."
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
        filler_slots = active_locations - len(pool)
        trap_slots = filler_slots * self.options.trap_percentage.value // 100
        pool.extend(self.create_item(self._random_trap()) for _ in range(trap_slots))
        for entry in self._filler_entries(filler_slots - trap_slots):
            name = entry if entry is not None else self.multiworld.random.choice(GENERAL_FILLER_NAMES)
            pool.append(self.create_item(name))
        self.multiworld.itempool += pool

    def _filler_entries(self, slots: int) -> list[str | None]:
        # Which mirror entries survive when the mirror has more entries than
        # there are slots. The smallest amounts give way first, so what a seed
        # keeps is the money that matters: an item worth $100 saves a player
        # almost no grinding where one worth thousands does. Progression and
        # useful items take their slots before filler does, so the more of them a
        # seed carries the further up this order it cuts, and a seed whose items
        # only just fit keeps only its largest rewards.
        #
        # A check that paid nothing in vanilla sorts last and becomes generic
        # filler if it survives at all. Ties break on the location name so the
        # order is total, and the shuffle afterwards is what decides where the
        # survivors land.
        ranked = sorted(self._enabled_locations(),
                        key=lambda name: (-data.LOCATION_REWARD[name], name))
        kept = [data.mirror_item(name) for name in ranked[:slots]]
        self.multiworld.random.shuffle(kept)
        return kept

    def _enabled_locations(self) -> list[str]:
        # Every check this seed has, in id order. The same predicate
        # create_regions uses, so the mirror stays one entry per location.
        return [name for name in LOCATION_NAME_TO_ID if self._location_enabled(name)]

    def _reward_mirror(self) -> list[str | None]:
        # One filler entry per enabled check, mirroring the vanilla cash it would
        # have paid: a cash item name, or None for a check that paid nothing.
        # create_items goes through _filler_entries, which orders and trims this;
        # what is left here is the mirror itself, which the tests assert on.
        return [data.mirror_item(name) for name in self._enabled_locations()]

    def _random_trap(self) -> str:
        # The trap types are equally weighted, so each filler-replacing slot
        # draws one uniformly at random.
        return self.multiworld.random.choice(data.TRAP_ITEMS)

    def _guard_fill_room(self) -> None:
        # A new game opens the sphere-zero giver's first mission plus whatever
        # start-region check the seed's classes leave unruled. A class narrows
        # the start two ways: a lock puts its checks behind an item, and a class
        # whose checks all sit on the mainland puts none in the start region to
        # begin with.
        #
        # A narrow start is widened wherever a held content class can widen it:
        # the content item opening the most start-region checks is directed into
        # the one open check, so the fill chains through it by construction
        # rather than by luck of the seed. Refusal is what is left when no held
        # class opens enough, and it stays solo only.
        #
        # A Universal Tracker regeneration replays a played seed's options on
        # its own solo multiworld, so a slot that generated inside a real
        # multiworld would meet this guard on the way back. That seed already
        # exists and its fill already happened, so there is nothing left to
        # widen or to refuse.
        if self._tracker_passthrough() is not None:
            return
        if self.directed_opening_item is not None:
            # An early item rather than starting inventory: the opener stays
            # in the pool and stays the reward for a check, and the fill puts it
            # in a location a new game reaches. Which one is the fill's to
            # choose, since its own sphere 0 counts the starting draws and is
            # never narrower than the count here. Directed at every player count,
            # since widening one slot costs the others nothing, but only a solo
            # seed gets a guarantee out of it: Fill places the pooled early items
            # of every world before it places this world's local ones, so a
            # partner's early item can take the only check this slot can reach
            # and leave the opener to the ordinary pool.
            self.multiworld.local_early_items[
                self.player][self.directed_opening_item] = 1
            return
        free_start_locations = self._free_start_location_count()
        if free_start_locations >= MINIMUM_SPHERE_ZERO:
            return
        # Only a solo seed is refused. Other worlds lend the fill their
        # locations to place this world's items into and their items to fill
        # this world's one open check with, and refusing there would abort
        # everyone's generation over one slot's options.
        if self.multiworld.players > 1:
            return
        raise OptionError(
            f"{self.game}: only {free_start_locations} check is reachable on a "
            "new game with these options, and no held content class opens enough "
            "of the start island to widen it, too narrow for the fill to chain "
            "through. Enable a class with unlocked checks on the start island, "
            "hidden packages being the one no ability term touches, or drop a "
            "lock key."
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

    def _choose_directed_opener(self) -> None:
        # The item the fill is told to put in a check a new game reaches, fixed
        # here so it is settled before the starting draws pick from the same
        # list. A start wide enough to chain through on its own directs
        # nothing, and neither does one whose best opener is too weak to help:
        # spending the only open check on an unlock worth a check or two fills
        # worse than leaving the fill to choose, which is what the floor is for.
        if self._free_start_location_count() >= MINIMUM_SPHERE_ZERO:
            return
        opener = self._best_start_opener()
        if opener is not None and opener[1] >= MINIMUM_DIRECTED_SPHERE_ZERO:
            self.directed_opening_item = opener[0]

    def _best_start_opener(self) -> tuple[str, int] | None:
        """The content item opening the most start-region checks, with how many.

        None when the seed holds no content class at all, so a narrow start has
        nothing to direct.
        """
        # Content items only. An ability or area item opens the start too, but
        # Land Vehicles and the crossings are milestones a seed is meant to wait
        # for, and spending one on the opening check hands them over at the
        # first mission.
        #
        # One state serves every candidate. Building one per candidate would run
        # every other world's collect override once per candidate, since
        # CollectionState replays the precollected items as it is built, and a
        # partner world whose override reads state it only builds later would
        # abort the whole generation from in here.
        location_rules = self._location_rules()
        state = CollectionState(self.multiworld)
        best: tuple[str, int] | None = None
        for name in self._content_items():
            # Progression only. The count is written into the state rather than
            # collected, which skips the classification check collecting would
            # have made, and an item logic cannot honour would score as an
            # opener the fill then cannot chain through. Every content item is
            # progression today, so this is a belt on that staying true.
            if not ItemClassification.progression & ITEM_CLASSIFICATIONS[name]:
                continue
            opened = self._start_locations_opened_by(name, location_rules, state)
            if best is None or opened > best[1]:
                best = (name, opened)
        return best

    def _start_locations_opened_by(
        self, item_name: str, location_rules: dict[str, rules.RulePredicate],
        state: CollectionState,
    ) -> int:
        """How many start-region checks this one item opens by itself.

        CONSUMES state: its item counts are overwritten, so pass a scratch
        CollectionState and never self.multiworld.state.
        """
        # The count is written straight into the state rather than collected,
        # which is what lets one state serve every candidate: an access rule
        # reads item counts and nothing else, never reachability, so there is no
        # other field to keep in step. Anything already precollected is
        # overwritten deliberately, the way _free_start_location_count counts no
        # item at all, so what a seed directs rests on its options alone.
        state.prog_items[self.player] = Counter({item_name: 1})
        return sum(
            1 for name, region in LOCATION_REGIONS.items()
            if region == data.REGION_VICE_CITY
            and self._location_enabled(name)
            and (name not in location_rules
                 or location_rules[name](state, self.player))
        )

    def set_rules(self) -> None:
        from worlds.generic.Rules import set_rule
        location_rules = self._location_rules()
        for location_name, rule in location_rules.items():
            if not self._location_enabled(location_name):
                continue
            set_rule(self.multiworld.get_location(location_name, self.player), self._bind(rule))
        # An event carries the rule of the mission it stands for, so holding the
        # event means that mission was reachable.
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
            "hidden_package_item_id": ITEM_NAME_TO_ID[data.PACKAGE_FRAGMENT_ITEM],
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
            "split_mainland_access": bool(self.options.split_mainland_access.value),
            "mainland_routes": scm.mainland_routes(
                bool(self.options.split_mainland_access.value)),
            "randomize_pickups": bool(self.options.randomize_pickups.value),
            # The selected ability lock keys (sorted; JSON has no sets), so a
            # tracker regeneration rebuilds the same pool and rules. The lock
            # flags themselves reach the ASI through config_globals.
            "ability_locks": sorted(self.options.ability_locks.value),
            "content_locks": sorted(self.options.content_locks.value),
            "split_content_locks": int(self.options.split_content_locks.value),
            "starting_ability_unlock": bool(self.options.starting_ability_unlock.value),
            "starting_content_unlock": bool(self.options.starting_content_unlock.value),
            # The drawn items themselves (None when the option is off or the
            # family selected no key), so a tracker regeneration precollects the
            # same two rather than rerolling them.
            "starting_ability_item": self.starting_ability_item,
            "starting_content_item": self.starting_content_item,
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
            # One content item can release many district globals: a whole-class
            # item releases all eleven of its class's. item_globals is one global
            # per item, so the fan-out rides beside it rather than bending that
            # shape. Every granularity's items are listed, since the item table
            # holds them all and a seed only ever receives the ones it placed.
            "content_district_globals": {
                str(item_id): global_indices
                for item_id, global_indices in scm.content_district_globals().items()
            },
            # Where each holdable pickup stands and which district it is in, so
            # the ASI can put a pool entry it found by type or model into a
            # district without carrying the district audit itself.
            "content_districts": scm.content_districts(),
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
        flags.update(scm.content_lock_flags(self._content_lock_keys()))
        # A class this seed does not lock arrives already released in every
        # district, so each gate and each hold is one condition and a seed with
        # no content_locks key behaves exactly vanilla.
        flags.update(scm.unlocked_district_globals(self._content_lock_keys()))
        if not self.options.enable_properties.value:
            flags.update(scm.properties_vanilla_globals())
        if self.options.randomize_pickups.value:
            # Retires the one vanilla help text that names the item at a spot
            # rather than the item in hand: it would describe the police bribe
            # the shuffle moved elsewhere. A vanilla flag, not a reserved one.
            flags.update(scm.pickups_randomized_globals())
        return flags

    def _completion_condition(self) -> Callable[[CollectionState], bool]:
        player = self.player
        goal = self.options.goal
        if goal == Goal.option_hidden_packages:
            # A hunt on received macguffins, not on collecting your own packages:
            # the goal is how many Package Fragments you receive, from anywhere
            # in the multiworld.
            need = self.options.hidden_packages_required.value
            return lambda state: state.has(data.PACKAGE_FRAGMENT_ITEM, player, need)
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
