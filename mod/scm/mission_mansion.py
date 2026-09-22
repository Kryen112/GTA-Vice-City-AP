"""Separate Rub Out's temporary combat scene from its permanent mansion transfer."""

import re

MANSION_APPLIED = 10462
MANSION_PREPARED = 10463
MANSION_LABEL = "AP_MANSION_TRANSFER"
RESTORE_LABEL = "AP_MANSION_RESTORE"
NATIVE_PASSED = "$passed_ASS1_Rub_Out"


def mansion_event_lines(trigger_global: int) -> list[str]:
    """The caller checks mission success before changing permanent events."""
    done = "AP_MANSION_EVENT_DONE"
    return ["if ", f"  ${trigger_global} == 16", f"goto_if_false @{done}",
            "if ", f"  ${MANSION_APPLIED} == 0", f"goto_if_false @{done}",
            f"gosub @{MANSION_LABEL}", f"${MANSION_APPLIED} = 1", f":{done}"]


def mansion_changes(source: list[str], timing: str) -> tuple[list[tuple[int, int, list[str]]], list[str]]:
    """Return validated edits and MAIN routines without changing the input."""
    assert timing in ("quest_giver_progress", "mission_completion"), "unknown world event timing"
    assert not any("AP_MANSION" in line for line in source), "mansion adapter is already installed"

    def unique(anchor: str) -> int:
        hits = [index for index, line in enumerate(source) if line == anchor]
        assert len(hits) == 1, f"mansion: {anchor!r} matched {len(hits)}, expected one"
        return hits[0]

    mission = unique("script_name 'BARON5'")
    ending = unique(":BARON5_12576")
    cleanup = unique(":BARON5_12919")
    assert mission < ending < cleanup, "mansion: unexpected mission ownership"
    changes = []

    # An early finale loads the interior before Rub Out unlocks the mansion.
    # Keep vanilla roof/front/rear transitions alive only during that mission.
    for level, destination in ((0, "SHIT_15051"), (1, "SHIT_13656")):
        gate = unique(f"  $1001 > {level}")
        assert source[gate - 1].strip() == "if" and source[gate + 1] == f"goto_if_false @{destination}", (
            "mansion: unexpected interior access gate")
        changes.append((gate - 1, 2, ["if or", source[gate], "  $10176 == 1"]))

    def take(first: str, last: str, *, lower: int, upper: int) -> list[str]:
        starts = [index for index in range(lower + 1, upper) if source[index] == first]
        ends = [index + 1 for index in range(lower + 1, upper) if source[index] == last]
        assert len(starts) == len(ends) == 1, "mansion: ambiguous effect anchors"
        start, end = starts[0], ends[0]
        assert lower < start < end <= upper, "mansion: effect outside its audited block"
        body = source[start:end]
        assert all(line and not re.search(r"\b\d+@", line) and not line.startswith(
            (":", "if", "wait", "goto", "return")) for line in body), "mansion: unsafe shared effect"
        changes.append((start, len(body), []))
        return body

    failure = unique(":BARON5_12540")
    closed = source[failure + 1:failure + 4]
    assert (len(closed) == 3 and closed[0].startswith("create_object_no_offset $1787 = ")
            and closed[1:] == ["dont_remove_object $1787", "$1001 = 0"]
            and source[failure + 4] == "return"), "mansion: unexpected failure restoration"
    changes.append((failure + 1, 3, []))
    front = unique("dont_remove_object $1788")
    closed_front = source[front - 1:front + 1]
    assert front < mission and closed_front[0].startswith("create_object_no_offset $1788 = "), (
        "mansion: missing original closed front door")

    door = take("delete_object $1788", "$1001 = 2", lower=ending, upper=cleanup)
    assert len(door) == 4 and door[1].startswith("create_object_no_offset $1789 = ") and (
        door[2] == "dont_remove_object $1789"), "mansion: unexpected ownership door"
    model_lines = (closed[0], closed_front[0], door[1])
    models = [match.group(1) for line in model_lines
              if (match := re.search(r"= init_object (#\w+) at ", line))]
    assert len(set(models)) == 3, "mansion: expected three door models"
    release = [f"mark_model_as_no_longer_needed {model}" for model in models]
    # Vanilla expects Rub Out to have removed the mansion's door barriers.
    # Early finale has to remove them temporarily.
    finale = unique("script_name 'FIN_1'")
    finale_cleanup = unique("gosub @FIN_1_27446")
    start = "-378.466 -596.1799 24.7818"
    finale_scenes = [index for index in range(len(source) - 3)
                     if source[index] == f"load_scene {start}"
                     and source[index + 1] == "set_threat_reaction_range_multiplier 2.0"
                     and source[index + 3] == f"set_player_coordinates $player_char at {start}"]
    assert len(finale_scenes) == 1, "mansion: ambiguous finale player placement"
    finale_scene = finale_scenes[0]
    changes.append((finale_scene, 0, ["request_collision -378.466 -596.1799"]))
    changes.append((finale + 1, 0, ["if ", f"  ${MANSION_APPLIED} == 0",
                                   "goto_if_false @AP_FINALE_DOORS_READY", "delete_object $1787",
                                   ":AP_FINALE_DOORS_READY"]))
    changes.append((finale_cleanup + 1, 0, ["if ", f"  ${MANSION_APPLIED} == 0",
        "goto_if_false @AP_FINALE_DOORS_RESTORED", "gosub @AP_MANSION_MODELS",
        *closed, *closed_front, *release, ":AP_FINALE_DOORS_RESTORED"]))
    # Its original front-door deletion stays intact.
    vehicles = take("switch_car_generator $1996 cars_to_generate_to 101", "start_new_script @PSAVE2",
                    lower=ending, upper=cleanup)
    assert len(vehicles) == 16 and vehicles[3] == "change_garage_type $686 change_to_type 31", (
        "mansion: unexpected transfer grants")
    assert not any("@PRO1" in line for line in vehicles), "mansion: vanilla mission reveal is still attached"
    helicopter = take("switch_car_generator $1987 cars_to_generate_to 101",
                      "set_zone_ped_info 'GANG1' 0 12 0 0 0 0 0 0 1000 0 0 0",
                      lower=mission, upper=ending)
    assert len(helicopter) == 3, "mansion: unexpected helicopter or population grant"
    original_population = [line for line in source[:mission]
                           if re.fullmatch(r"set_zone_ped_info 'GANG1' [01] 13 0 0 0 1000 0 0 0 0 0 0", line)]
    assert len(original_population) == 2, "mansion: missing initial estate population"
    wanted = [index for index in range(ending, cleanup) if source[index] == "set_max_wanted_level 6"]
    assert len(wanted) == 1, "mansion: ambiguous permanent wanted ceiling"
    changes.append((wanted[0], 1, []))

    preparation = unique("$1001 = 1")
    assert mission < preparation < ending and source[preparation + 1] == "delete_object $1787", (
        "mansion: unexpected combat preparation")
    changes.append((mission + 1, 0, [f"${MANSION_PREPARED} = 0"]))
    changes.append((preparation, 2, ["gosub @AP_MANSION_MODELS", f"${MANSION_PREPARED} = 1", "if ",
                                   f"  ${MANSION_APPLIED} == 0", "goto_if_false @AP_MANSION_PREPARE_OWNED",
                                   "delete_object $1787", "goto @AP_MANSION_PREPARE_DONE",
                                   ":AP_MANSION_PREPARE_OWNED", "delete_object $1789", *closed_front,
                                   ":AP_MANSION_PREPARE_DONE", "$1001 = 1", *release]))
    combat_threat = "set_threat_for_ped_type 10 add_threat 1"
    threats = [index for index, line in enumerate(source) if line == combat_threat]
    assert len(threats) == 4 and all(mission < index < ending for index in threats), (
        "mansion: combat threat has another owner")
    # Cleanup precedes both the completion dispatcher and any event it applies.
    cleanup_call = unique("gosub @BARON5_12919")
    changes.append((cleanup_call, 1, [source[cleanup_call], f"gosub @{RESTORE_LABEL}"]))
    if timing == "quest_giver_progress":
        showcase = unique("print_big 'PROP_A' 7000 ms 6")
        assert mission < showcase < ending and source[showcase + 1] == "wait 6000", (
            "mansion: unexpected property announcement")
        changes.append((showcase, 2, []))

    for label, expected in (("SHIT_13156", 0), ("SHIT_13865", 0), ("SHIT_14592", 0),
                            ("PICKUPS_2764", 1)):
        start = unique(f":{label}")
        end = next(index for index in range(start + 1, len(source)) if source[index].startswith(":"))
        reads = [index for index in range(start + 1, end) if source[index] == f"  {NATIVE_PASSED} == {expected}"]
        assert len(reads) == 1, f"mansion: {label} ownership read is ambiguous"
        changes.append((reads[0], 1, [f"  ${MANSION_APPLIED} == {expected}"]))
    for launcher in ("PRO1", "PRO2", "PRO3"):
        start = unique(f":{launcher}")
        end = next(index for index in range(start + 2, mission) if source[index].startswith("script_name '"))
        reads = [index for index in range(start, end) if source[index] == f"  {NATIVE_PASSED} == 1"]
        assert len(reads) == 1, f"mansion: {launcher} world prerequisite is ambiguous"
        changes.append((reads[0], 1, [f"  ${MANSION_APPLIED} == 1"]))

    routines = [":AP_MANSION_MODELS", *[f"request_model {model}" for model in models],
                "load_all_models_now", "return",
                f":{MANSION_LABEL}", "gosub @AP_MANSION_MODELS", "delete_object $1787", *door, *helicopter, *vehicles,
                "set_max_wanted_level 6", *release, "return", f":{RESTORE_LABEL}", "if ",
                f"  ${MANSION_PREPARED} == 1", "goto_if_false @AP_MANSION_RESTORE_DONE",
                "gosub @AP_MANSION_MODELS", "if ",
                f"  ${MANSION_APPLIED} == 0", "goto_if_false @AP_MANSION_RESTORE_OWNED",
                *closed, *original_population, "goto @AP_MANSION_RESTORE_CLEAR",
                ":AP_MANSION_RESTORE_OWNED", *door, *helicopter[1:],
                ":AP_MANSION_RESTORE_CLEAR", *release, "clear_threat_for_ped_type 10 remove_threat 1",
                f"${MANSION_PREPARED} = 0",
                ":AP_MANSION_RESTORE_DONE", "return"]
    return changes, routines
