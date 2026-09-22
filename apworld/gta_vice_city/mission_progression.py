"""Full-shuffle mission progression."""

from typing import NamedTuple

from BaseClasses import CollectionState, Item, ItemClassification, Location, Region

from . import data, mission_order
from .locations import LOCATION_NAME_TO_ID
from .rules import LocationRequirements, compile_requirements

BUSINESSES_PURCHASABLE = "Businesses purchasable"
MANSION_TAKEN_OVER = "Mansion taken over"
CORTEZ_DEPARTED = "Cortez departed"
WORLD_EVENTS = {"Shakedown": BUSINESSES_PURCHASABLE, "Rub Out": MANSION_TAKEN_OVER,
                "All Hands On Deck!": CORTEZ_DEPARTED}


def full_strands(properties_enabled: bool) -> dict[str, list[str]]:
    return {giver: list(missions) for giver, (group, missions) in data.progressive_strands().items()
            if giver not in {"Sunshine Autos", "Cherry Popper", "Boatyard"}
            and (group == "story_missions" or properties_enabled)}


def shuffle_full(strands: dict[str, list[str]], random) -> dict[str, list[str]]:
    movable = {giver: [mission for mission in missions if mission != "An Old Friend"]
               for giver, missions in strands.items()}
    assignment = mission_order.shuffle_slots(movable, random)
    assignment["Rosenberg"].insert(0, "An Old Friend")
    return assignment


def purchase_completed(venue: str) -> str:
    return f"Business purchased: {venue}"


def asset_completed(venue: str) -> str:
    return f"Income asset completed: {venue}"


def slot_completed(giver: str, ordinal: int) -> str:
    return f"Mission slot completed: {giver} {ordinal + 1}"


def mission_completed(mission: str) -> str:
    return f"Shuffled mission completed: {mission}"


class MissionSlot(NamedTuple):
    giver: str
    ordinal: int
    mission: str
    requirements: LocationRequirements


def build_slots(strands: dict[str, list[str]], assignment: dict[str, list[str]],
                entry_requirements: dict[tuple[str, int], LocationRequirements],
                gameplay_requirements: dict[str, LocationRequirements]) -> list[MissionSlot]:
    """Combine slot entry rules with the assigned mission's rules."""
    destinations = mission_order.assigned_slots(strands, assignment)
    if set(entry_requirements) != set(destinations.values()):
        raise ValueError("Every destination slot needs explicit entry requirements.")
    if set(gameplay_requirements) != set(destinations):
        raise ValueError("Every assigned mission needs explicit gameplay requirements.")
    if not set(destinations) <= LOCATION_NAME_TO_ID.keys():
        raise ValueError("Assigned missions must retain existing AP location IDs.")
    result = []
    for giver, missions in assignment.items():
        for ordinal, mission in enumerate(missions):
            entry = entry_requirements[giver, ordinal]
            gameplay = gameplay_requirements[mission]
            previous = [(slot_completed(giver, ordinal - 1), 1)] if ordinal else []
            result.append(MissionSlot(giver, ordinal, mission, LocationRequirements(
                [*entry.requirements, *gameplay.requirements, *previous],
                [*entry.thresholds, *gameplay.thresholds])))
    return result


def add_slot_locations(strands: dict[str, list[str]], assignment: dict[str, list[str]],
                       slots: list[MissionSlot], giver_regions: dict[str, Region],
                       timing: str) -> list[Location]:
    """Add mission checks and completion events to giver regions."""
    destinations = mission_order.assigned_slots(strands, assignment)
    if timing not in ("quest_giver_progress", "mission_completion"):
        raise ValueError(f"Unknown world event timing: {timing}")
    triggers = {event: mission_order.event_trigger_slot(strands, assignment, mission, timing)
                for mission, event in WORLD_EVENTS.items() if mission in destinations}
    if len(slots) != len(destinations) or {
            slot.mission: (slot.giver, slot.ordinal) for slot in slots} != destinations:
        raise ValueError("Slot records disagree with the mission assignment.")
    if set(giver_regions) != set(strands):
        raise ValueError("Every giver needs a destination region.")
    events = []

    def add(region: Region, name: str, requirements: LocationRequirements, event: bool) -> None:
        location = Location(region.player, name, None if event else LOCATION_NAME_TO_ID[name], region)
        predicate = compile_requirements(requirements)
        location.access_rule = lambda state: predicate(state, region.player)
        if event:
            location.place_locked_item(Item(name, ItemClassification.progression, None, region.player))
            events.append(location)
        region.locations.append(location)

    for slot in slots:
        region = giver_regions[slot.giver]
        fact = slot_completed(slot.giver, slot.ordinal)
        add(region, slot.mission, slot.requirements, False)
        add(region, fact, slot.requirements, True)
        add(region, mission_completed(slot.mission), LocationRequirements([(fact, 1)], []), True)
    for event, (giver, ordinal) in triggers.items():
        add(giver_regions[giver], event,
            LocationRequirements([(slot_completed(giver, ordinal), 1)], []), True)
    return events


def validate_slot_reachability(state: CollectionState, events: list[Location]) -> None:
    """Reject assignments with unreachable completion events."""
    if any(location.item is None or location.address is not None for location in events):
        raise ValueError("Slot validation requires addressless event locations.")
    if any(state.has(location.item.name, location.player) for location in events):
        raise ValueError("Completion facts must not be pregranted for slot validation.")
    candidate = state.copy()
    candidate.sweep_for_advancements(events)
    unreachable = [location.name for location in events
                   if not candidate.has(location.item.name, location.player)]
    if unreachable:
        raise ValueError("Unreachable mission progression: " + ", ".join(unreachable))
