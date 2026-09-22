"""Mission routing for full shuffle."""

import re

from mission_access import needs_travel, route_lines
from mission_returns import PHONE_RETURN_POSITION, RETURN_PENDING, ending_relocations, giver_return_point, return_lines
from mission_world_effects import (
    BUSINESS_SALES_APPLIED,
    WORLD_EVENT_TIMINGS,
    business_event_lines,
    shakedown_event_changes,
)
from mission_yacht import YACHT_PRESENT, yacht_changes, yacht_event_lines

# The marker pass reserves 180 globals above 10176.
ACTIVE_SLOT = 10357
ACTIVE_MISSION = 10358
SUCCESS = 10359
SLOT_BASE = 10360
SLOT_CAPACITY = 100
# The Party and Treacherous Swine stage their own on-foot scenes on island one.
SMOKE_ASSIGNMENT = {3: 7, 7: 3}
RETURN_SMOKE_ASSIGNMENT = {3: 60, 60: 3}
SHAKEDOWN_SMOKE_ASSIGNMENT = {3: 31, 31: 3}
WORLD_EFFECTS_SMOKE_ASSIGNMENT = {3: 11, 11: 3, 7: 16, 16: 7}
WORLD_EFFECTS_SUITE_ROUTE = {3: 31, 4: 16, 5: 11, 6: 33, 7: 24,
                             8: 30, 9: 35, 10: 74, 11: 51,
                             18: 26, 19: 7, 20: 29, 25: 71, 26: 59, 17: 19,
                             12: 13, 13: 20, 14: 5, 15: 6, 16: 8,
                             63: 9, 64: 12, 56: 32, 53: 18, 54: 60, 55: 52}


def close_assignment(route: dict[int, int]) -> dict[int, int]:
    """Return displaced missions to the end of each open permutation path."""
    assert len(set(route.values())) == len(route), "duplicate test payload"
    assignment = dict(route)
    for start in route.keys() - set(route.values()):
        end = route[start]
        while end in route:
            end = route[end]
        assignment[end] = start
    assert set(assignment) == set(assignment.values()), "test assignment is not bijective"
    return assignment


def launch_lines(number: int, payload: int | None = None, *, capture_phone: bool = False) -> list[str]:
    capture = ([(f"get_player_coordinates $player_char position_to ${PHONE_RETURN_POSITION} "
                f"${PHONE_RETURN_POSITION + 1} ${PHONE_RETURN_POSITION + 2}"),
                f"get_player_heading ${PHONE_RETURN_POSITION + 3} = player $player_char"] if capture_phone else [])
    return [*capture, f"${ACTIVE_SLOT} = {number}", f"${ACTIVE_MISSION} = {number if payload is None else payload}",
            f"${SUCCESS} = 0", "gosub @AP_DISPATCH"]


def non_cutscene_intro_changes(source: list[str], spans: dict[int, tuple[int, int]],
                              slot: int, payload: int,
                              launcher_span: tuple[int, int]) -> list[tuple[int, int, list[str]]]:
    """Stage phone and taxi openings without inheriting a loaded-cutscene lock."""
    taxi = payload in (72, 73, 74)
    if payload not in range(67, 75) or slot == payload or (taxi and slot in (72, 73, 74)):
        return []
    start, end = spans[payload]
    name = f"TAXWAR{payload - 71}" if taxi else f"ASSIN{payload - 66}"
    entries = [index for index in range(start, end)
               if source[index] == f"script_name '{name}'"]
    assert len(entries) == 1, "non-cutscene intro: expected one mission entry"
    # Keep scene setup inside the payload, preserving saved MAIN thread offsets.
    scene = (["switch_streaming 1", "restore_camera_jumpcut", "do_fade 1 500"] if taxi
             else ["switch_streaming 1", "do_fade 0 0"])
    changes = [(entries[0] + 1, 0, scene)]
    if not taxi:
        relocations = [index for index in range(start, end)
                       if source[index].startswith("set_player_coordinates $player_char at ")]
        assert len(relocations) == 1, "phone intro: expected one exterior relocation"
        x, y, z = source[relocations[0]].split()[3:]
        changes.append((relocations[0], 0, ["clear_extra_colours 0", "set_area_visible 0", "$991 = 0",
                                           f"request_collision {x} {y}", f"load_scene {x} {y} {z}"]))
    # Direct safety commands and HELP_2883 apply a cutscene-only input lock.
    # These payloads release only the normal control lock.
    changes += [(index, 1, ["set_player_control $player_char can_move False"])
                for index in range(*launcher_span)
                if source[index] in ("gosub @HELP_2883", "make_player_safe_for_cutscene $player_char")]
    return changes


def success_lines(number: int) -> list[str]:
    label = f"AP_DISPATCH_SUCCESS_{number}"
    return ["if ", f"  ${ACTIVE_MISSION} == {number}", f"goto_if_false @{label}",
            f"${SUCCESS} = 1", f":{label}"]


def finish_lines(number: int, completion: str | None = None, slot: int | None = None) -> list[str]:
    label = f"AP_DISPATCH_EXIT_{number}"
    grants = ([] if completion is None else [f"{completion} = 1"])
    if slot is not None:
        grants.append(f"${SLOT_BASE + slot} = 1")
    report = [] if not grants else [
        "if ", f"  ${SUCCESS} == 1", f"goto_if_false @AP_DISPATCH_REPORT_{number}",
        *grants, f":AP_DISPATCH_REPORT_{number}"]
    return ["if ", f"  ${ACTIVE_MISSION} == {number}", f"goto_if_false @{label}",
            *report, "gosub @AP_DISPATCH_FINISH", f":{label}"]


def dispatcher_lines(numbers: list[int], return_points: dict[int, tuple[str, ...]] | None = None,
                     business_timing: str | None = None, world_effects: bool = False,
                     mission_local_returns: bool = False) -> list[str]:
    assert business_timing is None or business_timing in WORLD_EVENT_TIMINGS, "unknown world event timing"
    reset = [f"${RETURN_PENDING} = 0"] if return_points or mission_local_returns else []
    result = [":AP_DISPATCH", *reset, f"load_and_launch_mission_internal ${ACTIVE_MISSION}", "return",
              ":AP_DISPATCH_FINISH", *(["gosub @AP_RETURN"] if return_points else []),
              "if ", f"  ${SUCCESS} == 1",
              "goto_if_false @AP_DISPATCH_CLEAR"]
    if business_timing is not None:
        trigger = ACTIVE_SLOT if business_timing == "quest_giver_progress" else ACTIVE_MISSION
        result += business_event_lines(trigger)
        if world_effects:
            from mission_mansion import mansion_event_lines
            result += mansion_event_lines(trigger) + yacht_event_lines(trigger)
    for number in ([] if world_effects else numbers):
        result += ["if ", f"  ${ACTIVE_SLOT} == {number}",
                   f"goto_if_false @AP_DISPATCH_NEXT_{number}",
                   f"${SLOT_BASE + number} = 1", "goto @AP_DISPATCH_CLEAR",
                   f":AP_DISPATCH_NEXT_{number}"]
    return [*result, ":AP_DISPATCH_CLEAR", f"${ACTIVE_SLOT} = 0",
            f"${ACTIVE_MISSION} = 0", f"${SUCCESS} = 0", *reset, "return",
            *(return_lines(return_points, ACTIVE_SLOT, ACTIVE_MISSION) if return_points else [])]


def instrument_identity_dispatch(lines: list[str], managed: list[dict], *, smoke: bool = False,
                                 return_smoke: bool = False, shakedown_smoke: bool = False,
                                 world_effects_smoke: bool = False,
                                 world_effects_suite: bool = False,
                                 world_event_timing: str = "quest_giver_progress",
                                 travel_source: list[str] | None = None, production: bool = False) -> None:
    """Route missions and save completed slots after cleanup."""
    assert sum((smoke, return_smoke, shakedown_smoke, world_effects_smoke)) <= 1, (
        "choose one dispatcher test assignment")
    assert world_event_timing in WORLD_EVENT_TIMINGS, "unknown world event timing"
    assert not world_effects_suite or world_effects_smoke, "suite requires world effects"
    assignment = (close_assignment(WORLD_EFFECTS_SUITE_ROUTE) if world_effects_suite
                  else SMOKE_ASSIGNMENT if smoke else RETURN_SMOKE_ASSIGNMENT if return_smoke
                  else SHAKEDOWN_SMOKE_ASSIGNMENT if shakedown_smoke
                  else WORLD_EFFECTS_SMOKE_ASSIGNMENT if world_effects_smoke else {})
    if production:
        from mission_layout import MISSION_NUMBERS
        assignment = {number: number for number in MISSION_NUMBERS.values()}
    source = [line.rstrip() for line in lines]
    assert not any("AP_DISPATCH" in line for line in source), "dispatcher is already installed"
    occupied = {int(match.group(1)) for line in source for match in re.finditer(r"\$(\d+)\b", line)}
    highest_global = (YACHT_PRESENT if world_effects_smoke else
                      BUSINESS_SALES_APPLIED if shakedown_smoke else RETURN_PENDING)
    assert not occupied.intersection(range(PHONE_RETURN_POSITION, highest_global + 1)), "dispatcher globals overlap"
    headers = [(int(match.group(1)), index) for index, line in enumerate(source)
               if (match := re.fullmatch(r"//-------------Mission (\d+)---------------", line))]
    spans = {number: (start, headers[index + 1][1] if index + 1 < len(headers) else len(source))
             for index, (number, start) in enumerate(headers)}
    records = [(mission["launcher"], mission["passed"], mission) for mission in managed]
    records += [("HOT", "$222", None), ("ICE1", "$612", None), ("COKRUN", "$607", None)]
    changes = shakedown_event_changes(source, world_event_timing) if shakedown_smoke or world_effects_smoke else []
    routines = []
    if world_effects_smoke:
        from mission_mansion import mansion_changes
        for edits, shared in (mansion_changes(source, world_event_timing), yacht_changes(source)):
            changes += edits
            routines += shared
    numbers = []
    marker_updates = []
    titles = {}
    title_sites = {}
    return_points = {}
    travel_payloads = set()
    if assignment and travel_source is not None:
        for launcher, _, marker in records:
            start = source.index(f":{launcher}")
            launch = next(line for line in source[start:] if line.startswith("load_and_launch_mission_internal "))
            number = int(launch.split()[-1])
            if marker is not None and (production or needs_travel(number, launcher)):
                travel_payloads.add(number)
    travel_open = route_lines(travel_source, restore=False) if travel_payloads else []
    travel_close = route_lines(travel_source, restore=True) if travel_payloads else []
    finish_edits = {}
    exit_sites = {}
    for launcher, passed, marker in records:
        start = source.index(f":{launcher}")
        end = next(index for index in range(start + 2, headers[0][1])
                   if source[index].startswith("script_name '"))
        launches = [(index, int(match.group(1))) for index in range(start, end)
                    if (match := re.fullmatch(r"load_and_launch_mission_internal (\d+)", source[index]))]
        assert launches, f"{launcher}: no accepted launch"
        number = launches[0][1]
        assert all(value == number for _, value in launches), f"{launcher}: ambiguous payload"
        assert 0 < number < SLOT_CAPACITY and number not in numbers, f"{launcher}: invalid slot"
        numbers.append(number)
        block_start, block_end = spans[number]
        successes = [index for index in range(block_start, block_end) if source[index] == f"{passed} = 1"]
        exits = [index for index in range(block_start, block_end) if source[index] == "terminate_this_script"]
        assert len(successes) == len(exits) == 1, f"{launcher}: ambiguous success or cleanup exit"
        payload = assignment.get(number, number)
        changes += non_cutscene_intro_changes(source, spans, -1 if production else number, payload,
                                                 (0, 0) if production else (start, end))
        changes += [(index, 1, launch_lines(number, payload,
                                             capture_phone=bool(travel_payloads)
                                             and launcher.startswith("ASSIN_")))
                    for index, _ in launches]
        if payload in travel_payloads:
            return_points[number] = giver_return_point(source, spans[number], launcher)
        if number in assignment:
            relocations = [] if payload in travel_payloads else ending_relocations(source, spans, payload)
            if relocations:
                return_points[number] = giver_return_point(source, spans[number], launcher)
                changes += [(index + 1, 0, [f"${RETURN_PENDING} = 1"]) for index in relocations]
            title_sites[number] = [index for index in range(start, end)
                                   if re.fullmatch(r"print_big '\w+' 15000 ms 2", source[index])]
            assert len({source[index] for index in title_sites[number]}) == 1, f"{launcher}: ambiguous mission title"
            titles[number] = source[title_sites[number][0]]
        if launcher == "FIN2":
            warp_start = source.index(":APFIN")
            warp_end = next(index for index in range(warp_start + 2, headers[0][1])
                            if source[index].startswith("script_name '"))
            warp_launches = [index for index in range(warp_start, warp_end)
                             if source[index] == f"load_and_launch_mission_internal {number}"]
            assert len(warp_launches) == 1, "finale warp: ambiguous launch"
            warp_slot = next((slot for slot, payload in assignment.items() if payload == number), number)
            changes.append((warp_launches[0], 1, launch_lines(warp_slot, number)))
        completion = None
        if marker is not None:
            guard = next(index for index in range(start, launches[0][0])
                         if source[index] == f"  {passed} == 1")
            assert source[guard + 1].startswith("goto_if_false @"), f"{launcher}: missing done guard"
            slot = f"${SLOT_BASE + number}"
            reports = [(index, match.group(1)) for index in range(guard + 2, guard + 5)
                       if (match := re.fullmatch(r"(\$\d+) = 1", source[index]))]
            assert len(reports) == 1, f"{launcher}: ambiguous AP completion write"
            report_index, completion = reports[0]
            changes.append((report_index, 1, []))
            changes.append((guard, 1, [f"  {slot} == 1"]))
            marker_updates.append((marker, slot))
        finish_edits[number] = finish_lines(number, completion,
                                           next((slot for slot, payload in assignment.items() if payload == number),
                                                number) if world_effects_smoke else None)
        exit_sites[number] = exits[0]
        changes += [(successes[0] + 1, 0, success_lines(number)), (exits[0], 0, finish_edits[number])]
    if assignment:
        assert assignment.keys() <= set(numbers), "smoke missions are missing"
        assert set(assignment) == set(assignment.values()), "smoke assignment is not bijective"
        changes += [(index, 1, [titles[payload]]) for slot, payload in assignment.items()
                    for index in title_sites[slot]]
    if world_effects_suite or travel_payloads:
        # Each fixed payload carries its return routine within its mission buffer.
        for slot, point in return_points.items():
            payload = assignment.get(slot, slot)
            label = f"AP_RETURN_PAYLOAD_{payload}"
            finish_edits[payload][:0] = [f"gosub @{label}"]
            body = [line.replace("AP_RETURN", label)
                    for line in return_lines({slot: point}, ACTIVE_SLOT, ACTIVE_MISSION,
                                             force=payload in travel_payloads)]
            if payload in travel_payloads:
                entry = next(index for index in range(*spans[payload])
                             if source[index].startswith("script_name "))
                opening = f"AP_TRAVEL_BEGIN_{payload}"
                closing = f"AP_TRAVEL_END_{payload}"
                changes.append((entry + 1, 0, [f"gosub @{opening}"]))
                finish_edits[payload].insert(1, f"gosub @{closing}")
                body += [f":{opening}",
                         *(line.replace("AP_TRAVEL", f"AP_TRAVEL_{payload}")
                           for line in travel_open), "return",
                         f":{closing}",
                         *(line.replace("AP_TRAVEL", f"AP_TRAVEL_{payload}")
                           for line in travel_close), "return"]
            changes.append((exit_sites[payload] + 1, 0, body))
    insertion = source.index(":GEN1")
    previous = next(line for line in reversed(source[:insertion]) if line)
    assert previous.startswith(("goto @", "return", "terminate_this_script")), "dispatcher fallthrough"
    changes.append((insertion, 0, dispatcher_lines(
        numbers, None if world_effects_suite or travel_payloads else return_points,
        world_event_timing if shakedown_smoke or world_effects_smoke else None,
        world_effects=world_effects_smoke,
        mission_local_returns=world_effects_suite or bool(travel_payloads)) + routines))
    foundation = source.index("script_name 'HOT'") + 1
    sizing_global = (BUSINESS_SALES_APPLIED if shakedown_smoke else RETURN_PENDING if return_points
                     else SLOT_BASE + SLOT_CAPACITY - 1)
    changes.append((foundation, 0, [f"${sizing_global} = 0"]))
    for index, removed, replacement in sorted(changes, reverse=True):
        lines[index:index + removed] = replacement
    if production:
        from mission_runtime import configure_runtime_dispatch
        configure_runtime_dispatch(lines, source, managed, return_points, titles, travel_open, travel_close)
    for marker, slot in marker_updates:
        marker["passed"] = slot
    mode = ("production" if production
            else f"world-effects suite ({world_event_timing})" if world_effects_suite
            else f"world-effects smoke ({world_event_timing})" if world_effects_smoke
            else f"early-Shakedown smoke ({world_event_timing})" if shakedown_smoke
            else "mission-return smoke" if return_smoke else "cross-giver smoke" if smoke else "identity")
    suffix = "" if production else "; fresh test saves only"
    print(f"{mode} dispatcher: {len(numbers)} saved slots{suffix}")


def instrument_production_dispatch(lines: list[str], managed: list[dict],
                                   travel_source: list[str]) -> None:
    instrument_identity_dispatch(lines, managed, world_effects_smoke=True,
                                 world_effects_suite=True, travel_source=travel_source,
                                 production=True)
