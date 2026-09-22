"""Mission-slot assignments and SCM order emitters. No Archipelago imports."""

from random import Random

UNLOCK_FIRST = 9010
UNLOCK_LAST = 9029
ORDER_BASE = 9036
RANK_GLOBAL = 10166
DIGIT_GLOBAL = 10167
COMPLETED_GLOBAL = 10168


def assigned_slots(strands: dict[str, list[str]], assignment: dict[str, list[str]]) -> dict[str, tuple[str, int]]:
    """Return each mission's destination slot."""
    if not isinstance(assignment, dict) or assignment.keys() != strands.keys():
        raise ValueError("Mission assignment must contain exactly the enabled givers.")
    expected = [mission for missions in strands.values() for mission in missions]
    if len(set(expected)) != len(expected):
        raise ValueError("Mission pool contains duplicate missions.")
    result = {}
    for giver, missions in strands.items():
        assigned = assignment[giver]
        if not isinstance(assigned, list) or len(assigned) != len(missions):
            raise ValueError(f"Mission assignment has the wrong number of slots for {giver}.")
        for ordinal, mission in enumerate(assigned):
            if not isinstance(mission, str) or mission not in expected or mission in result:
                raise ValueError("Mission assignment contains an unknown or repeated mission.")
            result[mission] = (giver, ordinal)
    return result


def shuffle_slots(strands: dict[str, list[str]], random: Random) -> dict[str, list[str]]:
    """Shuffle the supplied gameplay missions across all supplied start slots."""
    assigned_slots(strands, strands)
    missions = [mission for strand in strands.values() for mission in strand]
    random.shuffle(missions)
    assignment = {}
    start = 0
    for giver, original in strands.items():
        assignment[giver] = missions[start:start + len(original)]
        start += len(original)
    return assignment


def event_trigger_slot(strands: dict[str, list[str]], assignment: dict[str, list[str]],
                       mission: str, timing: str) -> tuple[str, int]:
    """Resolve a permanent event to its original milestone or assigned mission."""
    destinations = assigned_slots(strands, assignment)
    if timing == "quest_giver_progress":
        destinations = assigned_slots(strands, strands)
    elif timing != "mission_completion":
        raise ValueError(f"Unknown world event timing: {timing}")
    if mission not in destinations:
        raise ValueError(f"World event mission is absent: {mission}")
    return destinations[mission]


def order_global(unlock: int) -> int:
    return ORDER_BASE + unlock - UNLOCK_FIRST


def rank_lines(unlock: int, count: int, label: str) -> list[str]:
    """Decode a mission's rank; zero order preserves its vanilla rank.

    Each decimal digit holds one mission's rank, first mission in the units
    digit. Givers have at most five missions. Integer arithmetic needs no CLEO
    extension. The scratch globals are shared only across code with no waits.
    """
    order = order_global(unlock)
    return [f"${RANK_GLOBAL} = {count}",
            "if ", f"  ${order} > 0", f"goto_if_false @{label}",
            f"set_var_int_to_var_int ${RANK_GLOBAL} = ${order}", f"${RANK_GLOBAL} /= {10 ** (count - 1)}",
            f"set_var_int_to_var_int ${DIGIT_GLOBAL} = ${RANK_GLOBAL}", f"${DIGIT_GLOBAL} /= 10",
            f"${DIGIT_GLOBAL} *= 10", f"sub_int_var_from_int_var ${RANK_GLOBAL} -= ${DIGIT_GLOBAL}", f":{label}"]


def gate_lines(unlock: int, count: int, loopback: str, label: str) -> list[str]:
    return [*rank_lines(unlock, count, label),
            "if ", f"  is_int_var_greater_or_equal_to_int_var ${unlock} >= ${RANK_GLOBAL}",
            f"goto_if_false @{loopback}"]
