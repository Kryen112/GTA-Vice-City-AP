"""Player options.

Story missions are always on. Every other check class has a toggle. A disabled
class behaves fully vanilla in game: its locations do not exist and its
class-specific items leave the pool (CLAUDE.md toggle invariant). The 100% goal
is rejected unless every check class is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from Options import Choice, DeathLink, DefaultOnToggle, NamedRange, PerGameCommonOptions, StartInventoryPool


class Goal(Choice):
    """Which condition beats the seed.

    final_mission (default): complete "Keep Your Friends Close...".
    hidden_packages: collect the configured number of hidden packages.
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
    """Packages needed for the hidden-packages goal. Counted from the in-game
    package counter, so it works whatever the class toggles are."""
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


class EnableRampagesStunts(DefaultOnToggle):
    """If on, the 35 rampages and 36 unique stunt jumps are checks. This world
    creates no locations for the class yet; the toggle drives the option
    surface and the 100 percent goal requirement."""
    display_name = "Enable rampages and stunt jumps"


class EnableEmergencyVehicles(DefaultOnToggle):
    """If on, the per-level emergency vehicle milestones (paramedic, vigilante,
    firefighter, taxi, pizza) are checks."""
    display_name = "Enable emergency vehicle missions"


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


# The check-class toggles, by option attribute name. Story missions are always
# on and are not listed. The 100 percent goal requires every one of these true.
CHECK_CLASS_OPTIONS: list[str] = [
    "enable_hidden_packages", "enable_rampages_stunts",
    "enable_emergency_vehicles", "enable_properties",
    "enable_robbable_stores", "enable_side_events",
]


@dataclass
class GTAViceCityOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    goal: Goal
    hidden_packages_required: HiddenPackagesRequired
    enable_hidden_packages: EnableHiddenPackages
    enable_rampages_stunts: EnableRampagesStunts
    enable_emergency_vehicles: EnableEmergencyVehicles
    enable_properties: EnableProperties
    enable_robbable_stores: EnableRobbableStores
    enable_side_events: EnableSideEvents
    death_link: DeathLink
