"""Player options.

Story missions are always on. Every other check class has a toggle. A disabled
class behaves fully vanilla in game: its locations do not exist and its
class-specific items leave the pool (CLAUDE.md toggle invariant). The 100% goal
is rejected unless every check class holding content the game's own completion
stat counts is enabled, which is every class except the ambient pickups and
the shops.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from Options import (
    Choice,
    DeathLink,
    DefaultOnToggle,
    NamedRange,
    OptionSet,
    PerGameCommonOptions,
    StartInventoryPool,
    Toggle,
)


class Goal(Choice):
    """Which condition beats the seed.

    final_mission (default): complete "Keep Your Friends Close...".
    hidden_packages: receive the configured number of Package Fragment items, a
    hunt across the multiworld. Collecting a package in game is a check, never
    goal progress.
    hundred_percent: reach the game's own 100 percent stat. Requires Hidden
    Packages, Rampages, Stunt Jumps, Emergency Vehicles, Properties, Robbable
    Stores and Side Events to be enabled. Pickups and shops are not required,
    because the stat counts none of them.
    """
    display_name = "Goal"
    option_final_mission = 0
    option_hidden_packages = 1
    option_hundred_percent = 2
    default = 0


class HiddenPackagesRequired(NamedRange):
    """Amount of Package Fragment items to receive for the hidden-packages goal.
    The pool holds 100 fragments. Has no effect under the other goals."""
    display_name = "Hidden Packages required"
    range_start = 1
    range_end = 100
    default = 50
    special_range_names: ClassVar[dict[str, int]] = {"few": 10, "half": 50, "most": 80, "all": 100}


class EnableHiddenPackages(DefaultOnToggle):
    """If on, the 100 Hidden Packages are checks and their vanilla threshold
    rewards enter the item pool. If off, packages stay collectible vanilla-style
    and their rewards are not shuffled."""
    display_name = "Enable Hidden Packages"


class EnableRampages(DefaultOnToggle):
    """If on, the 35 Rampages are checks."""
    display_name = "Enable Rampages"


class EnableStuntJumps(DefaultOnToggle):
    """If on, the 36 unique Stunt Jumps are checks."""
    display_name = "Enable Stunt Jumps"


class EnableEmergencyVehicles(DefaultOnToggle):
    """If on, the per-level Emergency Vehicle milestones (12 paramedic,
    12 vigilante, 12 firefighter, 10 taxi, 10 pizza) are checks."""
    display_name = "Enable Emergency Vehicle missions"


class ShuffleEmergencyRewards(Toggle):
    """If on, the 5 emergency-vehicle completion rewards (infinite sprint,
    fireproof, max armor, taxi jump ability, max health) become useful items in
    the pool and finishing an emergency chain hands over nothing.

    Independent of enable_emergency_vehicles. This is about the rewards only."""
    display_name = "Shuffle Emergency Vehicle rewards"


class EnableProperties(DefaultOnToggle):
    """If on, the 15 Property purchases and the 25 venue missions are checks.
    This does include the 6 Sunshine Autos races and its 4 import lists."""
    display_name = "Enable Properties and assets"


class EnableRobbableStores(DefaultOnToggle):
    """If on, the 15 Robbable Stores are checks."""
    display_name = "Enable Robbable Stores"


class EnableSideEvents(DefaultOnToggle):
    """If on, the 14 side events (Hotring, Bloodring, Dirtring, Chopper checkpoints,
    RC missions, Cone Crazy, PCJ Playground, Trial by Dirt and Test Track) are checks."""
    display_name = "Enable side events"


class EnablePickups(Toggle):
    """If on, the 116 pickups lying around the world are checks the first time
    each one is taken: weapons, health, body armor, adrenaline and bribes.
    An untaken pickup shows a GTA III logo, the one sprite the game never uses,
    and once its check is taken it goes back to being an ordinary pickup, shuffled if
    randomize_pickups is on. Ten of them sit inside hospitals and pharmacies
    and charge $1000 for the marker."""
    display_name = "Enable pickups"


class RandomizePickups(Toggle):
    """If on, the ambient world pickups shuffle in their own pool:
    Weapons, Health, Body armors, Adrenaline and Bribes trade places.
    This is in-world flavor only, not Archipelago locations."""
    display_name = "Randomize pickups"


class ShuffleShops(Toggle):
    """If on, shop items are checks the first time each one is bought.
    7 shops sell: 3 Ammu-Nations, 3 tool stores and Phil's Place,
    unlocked after Boomshine Saigon is completed."""
    display_name = "Shuffle shops"


class RandomizeRadioStations(Toggle):
    """If on, the 9 radio stations become useful items. You start with one
    at random and the other eight are in the pool.
    The radio can always be turned off and the MP3 player is excluded."""
    display_name = "Randomize radio stations"


class ShuffleMinimap(Toggle):
    """If on, the minimap starts hidden and the Minimap item joins the pool as
    a useful item."""
    display_name = "Shuffle minimap"


class SplitMainlandAccess(Toggle):
    """If on, Mainland Access is replaced by one item per vanilla crossing:
    Prawn Island Bridge, Leaf Links Bridge, Ocean Beach Bridge and Starfish
    Island Causeway. Each opens only its own barrier, so any single one reaches
    the whole mainland. The causeway also needs Starfish Island Access, since
    the gate is on the island.

    If off, one Mainland Access item opens every crossing at once, the vanilla
    flip."""
    display_name = "Split mainland access"


class AbilityLocks(OptionSet):
    """Lock abilities and add them as items to the pool. This impacts logic.
    Valid keys: [sprint, jump, crouch, vehicles, weapon_equip, wallet]

    Vehicles are split into Land Vehicles, Sea Vehicles and Air Vehicles.
    Cash is void until you have a Wallet."""
    display_name = "Ability locks"
    valid_keys = frozenset({
        "sprint", "jump", "crouch", "vehicles", "weapon_equip", "wallet",
    })
    default = frozenset()


class StartingAbilityUnlock(Toggle):
    """Start with one random ability that you have locked, drawn at random
    from the Ability locks keys selected above."""
    display_name = "Starting ability unlock"


class ContentLocks(OptionSet):
    """Lock content and add them as items to the pool. Each selected key
    locks its class and puts its item in the pool.
    Valid keys: [hidden_packages, rampages, stunt_jumps, properties, robbable_stores]

    Packages, rampage icons and property icons are absent from the world until
    their item arrives. A locked stunt jump still flies and stays re-doable but
    registers nothing, and aiming at a shopkeeper starts no robbery.

    If a seed is too restricted to have anywhere to go from the first mission,
    the held item that opens the most of the start island becomes the reward for
    that mission. A solo seed is refused when no held class opens enough."""
    display_name = "Content locks"
    valid_keys = frozenset({
        "hidden_packages", "rampages", "stunt_jumps", "properties",
        "robbable_stores",
    })
    default = frozenset()


class SplitContentLocks(Choice):
    """Splits the content locks into multiple items.

    off: one item per selected class for the whole city at once.
    per_district: one item per district, covering every selected class there.
    "Ocean Beach Content" releases the Hidden Packages, Rampages, Stunt Jumps
    and Properties in Ocean Beach.
    per_class: one item per class per district. "Ocean Beach Hidden Packages"
    releases only the packages in Ocean Beach. The finest and the most items:
    42 with every key selected against 5 with the locks whole.

    The districts are Ocean Beach, Washington Beach, Vice Point, Leaf Links,
    Prawn Island, Starfish Island, Downtown, Little Haiti, Little Havana,
    Viceport and Escobar International.
    A class-district pair holding nothing gets no item, so Leaf Links only
    holds Hidden Packages, as there is nothing else on that island."""
    display_name = "Split content locks"
    option_off = 0
    option_per_district = 1
    option_per_class = 2
    default = 0


class StartingContentUnlock(Toggle):
    """Start with one random content item that you have locked, drawn at random
    from the Content locks keys selected above. Honors Split content locks if on,
    and then draws only from the start island's districts, since a mainland
    district item would be worth nothing on a new game."""
    display_name = "Starting content unlock"


class TrapPercentage(NamedRange):
    """Percentage of filler items replaced by traps (0 disables).
    The 7 trap types share the slice equally: raised wanted level,
    hostile pedestrians, stormy weather, foggy weather, sped-up time,
    slowed time and drunk vision."""
    display_name = "Trap percentage"
    range_start = 0
    range_end = 100
    default = 15
    special_range_names: ClassVar[dict[str, int]] = {
        "none": 0, "some": 15, "half": 50, "all": 100,
    }


# Every check-class toggle, by option attribute name. Story missions are always
# on and are not listed. This is the list a seed publishes into slot_data and a
# Universal Tracker regeneration replays, so a class missing from it is a class
# whose setting the played seed does not record and a tracker silently defaults.
# Which of these the client then hands the ASI is a separate choice, made by the
# fixed key list in client/context.py.
CHECK_CLASS_OPTIONS: list[str] = [
    "enable_hidden_packages", "enable_rampages", "enable_stunt_jumps",
    "enable_emergency_vehicles", "enable_properties",
    "enable_robbable_stores", "enable_side_events", "enable_pickups",
    "shuffle_shops",
]

# The classes the 100 percent goal demands, because each HOLDS content the
# game's own completion stat counts. Holding some is the test: the emergency
# class carries 56 checks and the stat counts five of them, one per activity
# completed, ignoring every intermediate milestone and it is demanded on the
# strength of those five.
HUNDRED_PERCENT_CLASS_OPTIONS: list[str] = [
    "enable_hidden_packages", "enable_rampages", "enable_stunt_jumps",
    "enable_emergency_vehicles", "enable_properties",
    "enable_robbable_stores", "enable_side_events",
]

# The classes the stat counts nothing in, so the goal cannot demand them without
# meaning something the game does not. Named rather than subtracted: a list built
# by taking one name out of another says nothing about a class added later, which
# would then be demanded by default and silently. Every check class belongs to
# this list or the one above and a test refuses one that belongs to neither.
UNCOUNTED_CLASS_OPTIONS: list[str] = ["enable_pickups", "shuffle_shops"]

# The class keys those options belong to, for the goal to skip their
# locations. Neither was ever part of the game's 100 percent.
UNCOUNTED_CLASS_KEYS: list[str] = ["pickups", "shops"]


@dataclass
class GTAViceCityOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    goal: Goal
    hidden_packages_required: HiddenPackagesRequired
    enable_hidden_packages: EnableHiddenPackages
    enable_rampages: EnableRampages
    enable_stunt_jumps: EnableStuntJumps
    enable_emergency_vehicles: EnableEmergencyVehicles
    shuffle_emergency_rewards: ShuffleEmergencyRewards
    enable_properties: EnableProperties
    enable_robbable_stores: EnableRobbableStores
    enable_side_events: EnableSideEvents
    enable_pickups: EnablePickups
    randomize_pickups: RandomizePickups
    shuffle_shops: ShuffleShops
    randomize_radio_stations: RandomizeRadioStations
    shuffle_minimap: ShuffleMinimap
    split_mainland_access: SplitMainlandAccess
    ability_locks: AbilityLocks
    starting_ability_unlock: StartingAbilityUnlock
    content_locks: ContentLocks
    split_content_locks: SplitContentLocks
    starting_content_unlock: StartingContentUnlock
    trap_percentage: TrapPercentage
    death_link: DeathLink
