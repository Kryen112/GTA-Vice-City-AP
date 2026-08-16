"""Player options.

Story missions are always on. Every other check class has a toggle. A disabled
class behaves fully vanilla in game: its locations do not exist and its
class-specific items leave the pool (CLAUDE.md toggle invariant). The 100% goal
is rejected unless every check class is enabled.
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
    hidden_packages: receive the configured number of Hidden Package items, a
    hunt across the multiworld. Collecting a package in game is a check, never
    goal progress.
    hundred_percent: reach the game's own 100 percent stat. Generation rejects
    this unless every check class is enabled, since every stat contributor must
    be a check.
    """
    display_name = "Goal"
    option_final_mission = 0
    option_hidden_packages = 1
    option_hundred_percent = 2
    default = 0


class HiddenPackagesRequired(NamedRange):
    """Hidden Package items to receive for the hidden-packages goal. The pool
    holds one per physical package, scattered across the multiworld; receiving
    this many wins. Has no effect under the other goals."""
    display_name = "Hidden packages required"
    range_start = 1
    range_end = 100
    default = 50
    special_range_names: ClassVar[dict[str, int]] = {"few": 10, "half": 50, "most": 80, "all": 100}


class EnableHiddenPackages(DefaultOnToggle):
    """If on, the 100 hidden packages are checks and their vanilla threshold
    rewards enter the item pool. If off, packages stay collectible vanilla-style
    and their rewards are not shuffled."""
    display_name = "Enable hidden packages"


class EnableRampages(DefaultOnToggle):
    """If on, the 35 rampages are checks."""
    display_name = "Enable rampages"


class EnableStuntJumps(DefaultOnToggle):
    """If on, the 36 unique stunt jumps are checks."""
    display_name = "Enable stunt jumps"


class EnableEmergencyVehicles(DefaultOnToggle):
    """If on, the per-level emergency vehicle milestones (paramedic, vigilante,
    firefighter, taxi, pizza) are checks."""
    display_name = "Enable emergency vehicle missions"


class ShuffleEmergencyRewards(Toggle):
    """If on, the five emergency-vehicle completion rewards (infinite sprint,
    fireproof, max armor, taxi jump ability, max health) become useful items
    in the pool and the vanilla full-completion grant is suppressed. Has no
    effect unless emergency vehicle missions are enabled."""
    display_name = "Shuffle emergency vehicle rewards"


class EnableProperties(DefaultOnToggle):
    """If on, property purchases and venue mission strands are checks."""
    display_name = "Enable properties and assets"


class EnableRobbableStores(DefaultOnToggle):
    """If on, the robbable stores are checks."""
    display_name = "Enable robbable stores"


class EnableSideEvents(DefaultOnToggle):
    """If on, the side events (stadium, chopper checkpoints, RC, and the stat
    minigames) are checks. Required for the 100 percent goal."""
    display_name = "Enable side events"


class RandomizeRadioStations(Toggle):
    """If on, the nine radio stations become useful items: you start with one
    at random and the other eight are in the pool. Only unlocked stations play,
    in your own vehicle and in every car, taxi, or mission vehicle you enter;
    the radio can always be turned off, and the MP3 player is excluded. A
    mission that forces a station plays it if unlocked, otherwise the next
    unlocked one. The police scanner is untouched. If off, the radio is fully
    vanilla."""
    display_name = "Randomize radio stations"


class ShuffleMinimap(Toggle):
    """If on, the minimap starts hidden and the Minimap item joins the pool as
    a useful item; the radar disc comes back when it is received. Mission blips
    are part of the disc, so until then navigation runs on the world markers
    and memory. If off, the minimap is fully vanilla."""
    display_name = "Shuffle minimap"


class RandomizePickups(Toggle):
    """If on, the ambient world pickups shuffle among their own spots as one
    permutation: street weapons, health hearts, body armors, adrenaline pills,
    and police bribes trade places, a weapon's ammo traveling with it. Every
    spot keeps its respawn behavior. Hidden packages, rampage icons, safehouse
    reward spawns, property icons, shop stock, and mission-spawned pickups
    stay vanilla, and no locations or items change: this is in-world flavor
    only. If off, every pickup is fully vanilla."""
    display_name = "Randomize pickups"


class AbilityLocks(OptionSet):
    """Abilities locked at new game until their item arrives from the
    multiworld. Each selected key locks its ability and puts its item in the
    pool; an unselected key is fully vanilla. Valid keys:

    sprint: the sprint input masks until Sprint arrives; the jog is untouched.
    jump: Tommy cannot jump until Jump arrives.
    crouch: Tommy cannot crouch until Crouch arrives.
    vehicles: Tommy cannot enter vehicles; Land Vehicles, Sea Vehicles, and
    Air Vehicles each unlock their class. Scripted cutscenes that seat him
    still work.
    weapon_equip: owned weapons cannot be equipped and vehicle drive-by fire
    is blocked until Weapon Equip arrives; bare fists always work. Weapon
    rampage icons wait for it too; the two run-them-down rampages need a land
    vehicle instead.
    wallet: the money balance pins to zero until Wallet arrives. Everything
    earned or received while locked burns, cash items included, and property
    purchases logically require the Wallet item."""
    display_name = "Ability locks"
    valid_keys = frozenset({
        "sprint", "jump", "crouch", "vehicles", "weapon_equip", "wallet",
    })
    default = frozenset()


class TrapPercentage(NamedRange):
    """Percentage of filler items replaced by traps (0 disables). The eight
    trap types share the slice equally: raised wanted level, exploding cars,
    hostile pedestrians, stormy weather, foggy weather, sped-up time, slowed
    time, and drunk vision. Traps only ever replace filler, so they never
    crowd out progression."""
    display_name = "Trap percentage"
    range_start = 0
    range_end = 100
    default = 15
    special_range_names: ClassVar[dict[str, int]] = {
        "none": 0, "some": 15, "half": 50, "all": 100,
    }


# The check-class toggles, by option attribute name. Story missions are always
# on and are not listed. The 100 percent goal requires every one of these true.
CHECK_CLASS_OPTIONS: list[str] = [
    "enable_hidden_packages", "enable_rampages", "enable_stunt_jumps",
    "enable_emergency_vehicles", "enable_properties",
    "enable_robbable_stores", "enable_side_events",
]


@dataclass
class GTAViceCityOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    goal: Goal
    hidden_packages_required: HiddenPackagesRequired
    enable_hidden_packages: EnableHiddenPackages
    enable_rampages: EnableRampages
    enable_stunt_jumps: EnableStuntJumps
    enable_emergency_vehicles: EnableEmergencyVehicles
    enable_properties: EnableProperties
    enable_robbable_stores: EnableRobbableStores
    enable_side_events: EnableSideEvents
    shuffle_emergency_rewards: ShuffleEmergencyRewards
    randomize_radio_stations: RandomizeRadioStations
    shuffle_minimap: ShuffleMinimap
    randomize_pickups: RandomizePickups
    ability_locks: AbilityLocks
    trap_percentage: TrapPercentage
    death_link: DeathLink
