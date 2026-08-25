"""Player options.

Story missions are always on. Every other check class has a toggle. A disabled
class behaves fully vanilla in game: its locations do not exist and its
class-specific items leave the pool (CLAUDE.md toggle invariant). The 100% goal
is rejected unless every check class holding content the game's own completion
stat counts is enabled, which is every class except the ambient pickups.
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
    hundred_percent: reach the game's own 100 percent stat. Generation rejects
    this unless every check class holding content that stat counts is enabled,
    so that beating the seed means the stat is actually full: a class left off
    stays vanilla and playable, so the goal would fire short of 100 percent
    rather than become unreachable. Ambient pickups are the one class it does
    not require, because the stat counts none of them.
    """
    display_name = "Goal"
    option_final_mission = 0
    option_hidden_packages = 1
    option_hundred_percent = 2
    default = 0


class HiddenPackagesRequired(NamedRange):
    """Package Fragment items to receive for the hidden-packages goal. The pool
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
    fireproof, max armor, taxi jump ability, max health) become useful items in
    the pool and the vanilla grant is suppressed, so finishing an emergency
    chain hands over nothing and the reward arrives from the multiworld instead.

    Independent of enable_emergency_vehicles. Whether the levels are CHECKS and
    who hands over the REWARDS are different questions, and this answers only the
    second: with the levels left vanilla and this on, the chains still play as
    they always did and simply stop paying out."""
    display_name = "Shuffle emergency vehicle rewards"


class EnableProperties(DefaultOnToggle):
    """If on, property purchases and venue mission strands are checks."""
    display_name = "Enable properties and assets"


class EnableRobbableStores(DefaultOnToggle):
    """If on, the robbable stores are checks."""
    display_name = "Enable robbable stores"


class EnablePickups(Toggle):
    """If on, the 116 pickups lying around the world are checks the first time
    each one is taken: street weapons, health, body armor, adrenaline and
    police bribes. Six of them are not lying there from the start, because a
    mission puts them there and leaves them: the minigun on the ruined Haitian
    drugs factory, four in the Vercetti Estate courtyard, and a knife outside
    the Malibu Club. An untaken pickup shows an Archipelago marker, and once its
    check is taken it goes back to being an ordinary pickup, shuffled if
    randomize_pickups is on. Ten of them sit inside shops and charge a thousand
    dollars for the marker.

    Off by default, because 116 extra checks change how a game plays. The 100
    percent goal ignores them, since the game never counted a health pickup off
    the street."""
    display_name = "Enable pickups"
    # The reach terms were missing when this shipped, deliberately, because the
    # walk that writes them needed the checks live to walk to. That walk has
    # happened: 20 carry an ability or route term, the six a mission creates wait
    # on that mission, and the rest are walked to, so the docstring no longer
    # warns about a pickup that can dead-end.


class ShuffleShops(Toggle):
    """If on, the 36 things the weapon shops sell are checks the first time each
    one is bought. Seven shops sell: three Ammu-Nations, with guns, grenades and
    body armor, three tool stores, with melee weapons, and Phil's Place, which
    racks a rocket launcher, an M60, a minigun and remote grenades once
    Boomshine Saigon has passed. Each shop has its own stock and its own prices,
    so the same weapon in two shops is two separate checks. Every one of them
    needs the Wallet if you play with that ability lock, since a shop charges.

    While a check is pending the shop shows an Archipelago marker in place of
    the item. Buying it costs the shop's usual price and hands over nothing,
    and the stand then turns back into the real item, so buying again is an
    ordinary purchase. Phil's four are priced by the game rather than by a
    script, so a pending one there charges what that weapon costs at his
    counter, the same as the other six shops. With this off the shops are
    exactly vanilla.

    The 100 percent goal ignores them, since buying a shotgun never counted
    toward it.

    17 of the 36 only come into stock after a particular mission, and logic
    knows which: 13 stand on the wall out of stock until a story mission sets the
    flag their shop reads, and Phil's four are not in the world at all until
    Boomshine Saigon passes. The Vice Point sniper is handled differently again,
    because vanilla stocks it off the same flag the mainland crossing sets, so it
    asks for Mainland Access despite standing on the first island."""
    display_name = "Shuffle shops"


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
    spot keeps its respawn behavior. The spots a mission leaves behind for good
    are in it too, so the minigun on the ruined Haitian drugs factory, the four
    pickups in the Vercetti Estate courtyard and the knife outside the Malibu
    Club shuffle like any other once their mission has passed. Hidden packages,
    rampage icons, safehouse reward spawns, property icons, shop stock, and the
    pickups a mission places and clears again stay vanilla, and no locations or
    items change: this is in-world flavor only. If off, every pickup is fully
    vanilla."""
    display_name = "Randomize pickups"


class SplitMainlandAccess(Toggle):
    """If on, Mainland Access is replaced by one item per vanilla crossing:
    Prawn Island Bridge, Leaf Links Bridge, Ocean Beach Bridge, and Starfish
    Island Causeway. Each opens only its own barrier, so any single one reaches
    the whole mainland and which one you hold decides where you cross. The
    causeway also needs Starfish Island Access, since the gate is on the island.
    If off, one Mainland Access item opens every crossing at once, the vanilla
    flip."""
    display_name = "Split mainland access"


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


class StartingAbilityUnlock(Toggle):
    """Start with one locked ability already unlocked, drawn at random from the
    ability_locks keys this seed selected. The seed makes the choice, so the
    ability is not known until the game starts. The item is starting
    inventory, so it leaves the pool rather than adding to it, and the vehicles
    key draws one of its three items rather than all of them. Nothing happens
    when ability_locks is empty."""
    display_name = "Starting ability unlock"


class ContentLocks(OptionSet):
    """Content held inert at new game until its item arrives from the
    multiworld. Each selected key locks its class and puts its item in the
    pool; an unselected key is fully vanilla. A key holds its content even when
    that class's own enable toggle is off, so a seed can lock world content
    without turning it into checks. Valid keys:

    hidden_packages: the 100 package pickups are absent until Hidden Packages
    arrives.
    rampages: the 35 rampage icons are absent until Rampages arrives.
    stunt_jumps: a unique stunt jump registers nothing and pays nothing until
    Stunt Jumps arrives. The jump itself always flies and stays re-doable, so
    nothing is missable.
    properties: all 15 property purchase icons are absent until Property
    Purchases arrives, businesses and safehouses alike. The starting hotel and
    the mansion are story-given, so a save point is never locked away.
    robbable_stores: aiming at a shopkeeper starts no robbery until Robbable
    Stores arrives.

    Locking a class removes it from the start of the game. With every check
    class enabled all five keys together still leave a wide start, but anything
    else that narrows it can close the start down to the first mission alone:
    turning check classes off does, and so does ability_locks. Holding the
    hidden packages, the one class no ability term touches, is what usually
    keeps such a seed open.

    A start that closes down to one check is widened rather than refused: the
    held content item opening the most of the start island becomes the reward
    for that one check, so the seed has somewhere to go from the first mission.
    A solo seed is refused only when no held class opens enough of the start
    island to carry it. That is every seed holding no content class at all, and
    also one whose keys hold only classes an ability_locks key already gates or
    a disabled class, since such an item opens too little on its own. The error
    names what to change."""
    display_name = "Content locks"
    valid_keys = frozenset({
        "hidden_packages", "rampages", "stunt_jumps", "properties",
        "robbable_stores",
    })
    default = frozenset()


class SplitContentLocks(Choice):
    """How wide one content item's reach is. Only matters while content_locks
    selects something, and it never changes WHICH content is held, only how many
    items carry the holding.

    off: one item per selected class, the whole city at once. Hidden Packages
    releases all 100.
    per_district: one item per district, covering every selected class there.
    Ocean Beach Content releases the packages, rampages, jumps, stores and
    property icons in Ocean Beach.
    per_class: one item per class per district. Ocean Beach Hidden Packages
    releases only the packages in Ocean Beach. The finest, and the most items:
    42 with every key selected against 5 with the locks whole.

    The districts are the eleven the map names, so a district item covers what a
    player would call that part of town. A class-district pair holding nothing
    gets no item, which is why 42 rather than 55.

    Splitting narrows the biggest single unlock: whole, Hidden Packages opens
    100 checks at once; per_district the largest is Vice Point at 42; per_class
    it is the Vice Point packages at 21."""
    display_name = "Split content locks"
    option_off = 0
    option_per_district = 1
    option_per_class = 2
    default = 0


class StartingContentUnlock(Toggle):
    """Start with one held content item already released, drawn at random from
    the ones this seed's content_locks keys produce. The seed makes the choice,
    so what is released is not known until the game starts. With
    split_content_locks on that is one district's worth rather than a whole
    class, so this opens correspondingly less, and the draw is over the start
    island's districts only: a district item for the mainland or Starfish Island
    would be worth nothing on a new game. The item is starting inventory, so it
    leaves the pool rather than adding to it. Nothing happens when content_locks
    is empty, or when its keys hold nothing on the start island.

    A released class widens the start of the game, but generation never counts
    on it: the narrow-start measure reads what is open with no item at all, so
    this option cannot decide whether a seed generates. A seed narrow enough to
    need one item directed into its opening check keeps that item in the pool and
    out of this draw, so the draw takes one of the others, or nothing at all
    where that item was the only one the keys produced."""
    display_name = "Starting content unlock"


class TrapPercentage(NamedRange):
    """Percentage of filler items replaced by traps (0 disables). The seven
    trap types share the slice equally: raised wanted level, hostile
    pedestrians, stormy weather, foggy weather, sped-up time, slowed time, and
    drunk vision. Traps only ever replace filler, so they never crowd out
    progression."""
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
# completed, ignoring every intermediate milestone, and it is demanded on the
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
# this list or the one above, and a test refuses one that belongs to neither.
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
    enable_properties: EnableProperties
    enable_robbable_stores: EnableRobbableStores
    enable_pickups: EnablePickups
    shuffle_shops: ShuffleShops
    enable_side_events: EnableSideEvents
    shuffle_emergency_rewards: ShuffleEmergencyRewards
    randomize_radio_stations: RandomizeRadioStations
    shuffle_minimap: ShuffleMinimap
    split_mainland_access: SplitMainlandAccess
    randomize_pickups: RandomizePickups
    ability_locks: AbilityLocks
    starting_ability_unlock: StartingAbilityUnlock
    content_locks: ContentLocks
    split_content_locks: SplitContentLocks
    starting_content_unlock: StartingContentUnlock
    trap_percentage: TrapPercentage
    death_link: DeathLink
