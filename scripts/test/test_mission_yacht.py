"""Yacht scenes survive early departure, failure, retries, and saved state."""

import importlib
from collections import defaultdict

import pytest
from test_mission_dispatch import dispatch
from test_mission_order import run_lines

yacht = importlib.import_module("mission_yacht")


def source_lines():
    models = {714: "YT_MAIN_BODY", 715: "YT_MAIN_BODY2", 717: "YT_DOORS14", 718: "YT_TMP_BOAT",
              719: "LODMAIN_BODY", 721: "YACHT_CHUNK_KB", 720: "YT_GANGPLNK_TMP"}
    lines = ["initialise_object_path $722 = scripted_path_file 0 width 90.0"]
    for number, model in models.items():
        if number == 721:
            lines += ["wait 0", "wait 0"]
        lines += [f"create_object_no_offset ${number} = init_object #{model} at 1.0 2.0 3.0",
                  f"dont_remove_object ${number}"]
    lines += ["load_and_launch_mission_internal 1", ":GEN1", "terminate_this_script"]
    for number in yacht.YACHT_MISSIONS:
        lines += [f"//-------------Mission {number}---------------", "$onmission = 1"]
        if number == 11:
            lines += [":COL_5_1765", "delete_object $720", "delete_object $721",
                      "delete_object $718", ":COL_5_27542",
                      *[f"delete_object ${handle}" for handle in range(714, 722)],
                      "clear_object_path $722", ":COL_5_27598"]
        lines += ["$onmission = 0", "terminate_this_script"]
    return lines


def test_scene_hooks_are_inside_mission_lifetime_and_handles_are_invalidated():
    source = source_lines()
    edits, routines = yacht.yacht_changes(source)
    for index, removed, replacement in sorted(edits, reverse=True):
        source[index:index + removed] = replacement
    assert source.count("gosub @AP_YACHT_CREATE") == 7
    assert source.count("gosub @AP_YACHT_RESTORE") == 6
    for index, line in enumerate(source):
        if line == "$onmission = 1":
            assert source[index + 1] == "gosub @AP_YACHT_CREATE"
        if line == "$onmission = 0":
            assert source[index - 1] == "gosub @AP_YACHT_RESTORE"
        if line in {"delete_object $720", "delete_object $721", "delete_object $718"}:
            assert source[index + 1] == f"{line.split()[1]} = -1"
    assert routines.count("clear_object_path $722") == 1
    assert routines.index("load_all_models_now") < next(
        index for index, line in enumerate(routines) if line.startswith("create_object_no_offset"))
    assert routines.index(f"${yacht.YACHT_PRESENT} = 2") < routines.index("wait 0")
    assert routines.index("gosub @AP_YACHT_REMOVE") < routines.index(f"${yacht.YACHT_PRESENT} = 2")


@pytest.mark.parametrize("timing", ("quest_giver_progress", "mission_completion"))
def test_departure_and_temporary_scene_lifecycle(timing):
    _, routines = yacht.yacht_changes(source_lines())
    # Execute the guards and cleanup.
    start, end = routines.index("load_all_models_now") + 1, routines.index(":AP_YACHT_RESTORE")
    routines[start:end] = ["start_new_script @CONSTRUCT_YACHT",
                           f"${yacht.YACHT_PRESENT} = 1", "return"]
    state = defaultdict(int)
    trigger = dispatch.ACTIVE_SLOT if timing == "quest_giver_progress" else dispatch.ACTIVE_MISSION

    def execute(body):
        return run_lines([*body, "terminate_this_script", *routines], state,
                         conditions={f"does_object_exist ${number}": True for number in range(714, 722)})

    assert execute(["gosub @AP_YACHT_CREATE"]) == ["CONSTRUCT_YACHT"]
    assert execute(["gosub @AP_YACHT_CREATE"]) == []
    state[f"${dispatch.ACTIVE_SLOT}"] = 3
    state[f"${dispatch.ACTIVE_MISSION}"] = 11
    execute(["gosub @AP_YACHT_REMOVE"])  # All Hands success ending.
    execute(["gosub @AP_YACHT_RESTORE"])
    execute(yacht.yacht_event_lines(trigger))
    assert state[f"${yacht.YACHT_DEPARTED}"] == (timing == "mission_completion")
    assert state[f"${yacht.YACHT_PRESENT}"] == (timing == "quest_giver_progress")
    state[f"${dispatch.ACTIVE_SLOT}"] = 11
    state[f"${dispatch.ACTIVE_MISSION}"] = 3
    execute(yacht.yacht_event_lines(trigger))
    assert state[f"${yacht.YACHT_PRESENT}"] == 0
    state = defaultdict(int, dict(state))
    for _ in range(2):  # Failed late scenes and retries leave the departed overworld intact.
        assert execute(["gosub @AP_YACHT_CREATE"]) == ["CONSTRUCT_YACHT"]
        execute(["gosub @AP_YACHT_RESTORE"])
        assert state[f"${yacht.YACHT_PRESENT}"] == 0
        assert state[f"${yacht.YACHT_DEPARTED}"] == 1
    # Death during either constructor wait leaves a partial scene that cleanup removes.
    for departed in (0, 1):
        state[f"${yacht.YACHT_PRESENT}"] = 2
        state[f"${yacht.YACHT_DEPARTED}"] = departed
        assert execute(["gosub @AP_YACHT_RESTORE"]) == ([] if departed else ["CONSTRUCT_YACHT"])
        assert state[f"${yacht.YACHT_PRESENT}"] == 1 - departed
        assert all(state[f"${number}"] == -1 for number in range(714, 722))


def test_changed_source_is_rejected_before_mutation():
    source = source_lines()
    source.remove("wait 0")
    original = source.copy()
    with pytest.raises(AssertionError, match="yacht"):
        yacht.yacht_changes(source)
    assert source == original
