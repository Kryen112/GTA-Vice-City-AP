"""Mansion ownership survives Rub Out's temporary scene and failed retries."""

import importlib.util
from collections import defaultdict
from pathlib import Path

import pytest
from test_mission_order import run_lines

SOURCE = Path(__file__).resolve().parents[2] / "mod/scm/mission_mansion.py"
specification = importlib.util.spec_from_file_location("mission_mansion", SOURCE)
mansion = importlib.util.module_from_spec(specification)
specification.loader.exec_module(mansion)


def source_lines():
    lines = ["create_object_no_offset $1788 = init_object #SYNTH_CLOSED_FRONT at 0 0 0", "dont_remove_object $1788",
             "set_zone_ped_info 'GANG1' 1 13 0 0 0 1000 0 0 0 0 0 0",
             "set_zone_ped_info 'GANG1' 0 13 0 0 0 1000 0 0 0 0 0 0"]
    lines += ["if ", "  $1001 > 0", "goto_if_false @SHIT_15051",
              "if ", "  $1001 > 1", "goto_if_false @SHIT_13656"]
    for label in ("SHIT_13156", "SHIT_13865", "SHIT_14592", "PICKUPS_2764"):
        value = 1 if label == "PICKUPS_2764" else 0
        lines += [f":{label}", "if ", f"  {mansion.NATIVE_PASSED} == {value}", f"goto_if_false @{label}_DONE",
                  f":{label}_DONE"]
    for launcher in ("PRO1", "PRO2", "PRO3"):
        lines += [f":{launcher}", f"script_name '{launcher}'", "if ", f"  {mansion.NATIVE_PASSED} == 1",
                  f"goto_if_false @{launcher}", f"goto @{launcher}"]
    lines += [":OTHER", "script_name 'OTHER'", "terminate_this_script", ":BARON5",
              "gosub @BARON5_36", "gosub @BARON5_12919", "terminate_this_script", ":BARON5_36",
              "script_name 'BARON5'", "wait 0", "$1001 = 1", "delete_object $1787",
              *["set_threat_for_ped_type 10 add_threat 1"] * 4,
              "switch_car_generator $1987 cars_to_generate_to 101",
              "set_zone_ped_info 'GANG1' 1 12 0 0 0 0 0 0 1000 0 0 0",
              "set_zone_ped_info 'GANG1' 0 12 0 0 0 0 0 0 1000 0 0 0",
              "print_big 'PROP_A' 7000 ms 6", "wait 6000", ":BARON5_12540",
              "create_object_no_offset $1787 = init_object #SYNTH_CLOSED_BACK at 0 0 0", "dont_remove_object $1787",
              "$1001 = 0", "return", ":BARON5_12576", f"{mansion.NATIVE_PASSED} = 1",
              "delete_object $1788", "create_object_no_offset $1789 = init_object #SYNTH_OPEN_FRONT at 0 0 0",
              "dont_remove_object $1789", "$1001 = 2", "clear_wanted_level $player_char",
              "set_max_wanted_level 6", "register_mission_passed 'ASS_1'", "player_made_progress 1",
              "switch_car_generator $1996 cars_to_generate_to 101",
              "switch_car_generator $1997 cars_to_generate_to 101",
              "switch_car_generator $1998 cars_to_generate_to 101",
              "change_garage_type $686 change_to_type 31",
              "create_pickup_with_ammo $77 = synthetic_weapon", "create_pickup_with_ammo $78 = synthetic_weapon",
              "create_pickup $79 = synthetic_health", "create_pickup $80 = synthetic_armour",
              "create_clothes_pickup $1297 = synthetic_clothes", "$1278 = 1",
              "switch_car_generator $1880 cars_to_generate_to 0", "switch_car_generator $83 cars_to_generate_to 101",
              "$855 = 1", "$906 = 1", "$907 = 1", "start_new_script @PSAVE2", "return",
              ":BARON5_12919", "$onmission = 0", "mission_has_finished", "return",
              ":CELL", f"  {mansion.NATIVE_PASSED} == 1", ":TROPHY", f"  {mansion.NATIVE_PASSED} == 1",
              ":FINALE", "delete_object $1788", "script_name 'FIN_1'",
              "load_scene -378.466 -596.1799 24.7818", "set_threat_reaction_range_multiplier 2.0",
              "clear_area 1 at -378.466 -596.1799 24.7818 range 1.0",
              "set_player_coordinates $player_char at -378.466 -596.1799 24.7818",
              "set_player_heading $player_char z_angle_to 0.0", "set_camera_behind_player ",
              "do_fade 1 1500", "if ", "  $onmission == 0", "goto_if_false @FIN_1_5216",
              ":FIN_1_5216", "gosub @FIN_1_27446"]
    return lines


def apply_changes(lines, timing):
    changes, routines = mansion.mansion_changes(lines, timing)
    for index, removed, replacement in sorted(changes, reverse=True):
        lines[index:index + removed] = replacement
    return routines


@pytest.mark.parametrize("timing", ("quest_giver_progress", "mission_completion"))
def test_early_finale_temporarily_enables_all_mansion_transitions(timing):
    lines = source_lines()
    apply_changes(lines, timing)
    for level, destination in ((0, "SHIT_15051"), (1, "SHIT_13656")):
        end = lines.index(f"goto_if_false @{destination}")
        assert lines[end - 3:end] == ["if or", f"  $1001 > {level}", "  $10176 == 1"]
        # Interpret the emitted OR conditions for locked, combat, and owned
        # states, including the finale flag dropping after failure or success.
        for mansion_state in range(3):
            for finale_active in (0, 1, 0):
                values = {"$1001": mansion_state, "$10176": finale_active}
                conditions = []
                for condition in lines[end - 2:end]:
                    variable, operator, value = condition.split()
                    conditions.append(values[variable] > int(value) if operator == ">"
                                      else values[variable] == int(value))
                assert any(conditions) == (mansion_state > level or finale_active == 1)
    assert "$1001 = 2" not in lines  # No permanent ownership grant.


def test_finale_loads_collision_before_placing_remote_player():
    lines = source_lines()
    apply_changes(lines, "mission_completion")
    load = lines.index("load_scene -378.466 -596.1799 24.7818")
    assert lines[load - 1] == "request_collision -378.466 -596.1799"
    assert lines[load + 3] == "set_player_coordinates $player_char at -378.466 -596.1799 24.7818"


@pytest.mark.parametrize("timing", ("quest_giver_progress", "mission_completion"))
def test_transfer_is_separate_from_success_and_scoped_consumers_follow_ownership(timing):
    lines = source_lines()
    routines = apply_changes(lines, timing)
    assert f"{mansion.NATIVE_PASSED} = 1" in lines
    assert "register_mission_passed 'ASS_1'" in lines
    assert "player_made_progress 1" in lines
    assert "clear_wanted_level $player_char" in lines
    assert "start_new_script @PSAVE2" not in lines
    assert routines.count("start_new_script @PSAVE2") == 1
    assert "set_max_wanted_level 6" not in lines
    assert "set_max_wanted_level 6" in routines
    assert ("print_big 'PROP_A' 7000 ms 6" in lines) == (timing == "mission_completion")
    failure = lines.index(":BARON5_12540")
    assert lines[failure + 1] == "return"
    cleanup = lines.index("gosub @BARON5_12919")
    assert lines[cleanup + 1] == f"gosub @{mansion.RESTORE_LABEL}"
    assert lines[lines.index(":CELL") + 1] == f"  {mansion.NATIVE_PASSED} == 1"
    assert lines[lines.index(":TROPHY") + 1] == f"  {mansion.NATIVE_PASSED} == 1"
    assert lines[lines.index(":FINALE") + 1] == "delete_object $1788"
    assert lines.count(f"  ${mansion.MANSION_APPLIED} == 1") == 4
    assert lines.count(f"  ${mansion.MANSION_APPLIED} == 0") == 6


@pytest.mark.parametrize("owned", (0, 1))
def test_finale_removes_locked_doors_and_restores_without_granting_ownership(owned):
    lines = source_lines()
    routines = apply_changes(lines, "mission_completion")
    start = lines.index("script_name 'FIN_1'") + 1
    cleanup = lines.index("gosub @FIN_1_27446") + 1
    state = defaultdict(int, {f"${mansion.MANSION_APPLIED}": owned, "$1001": 2 if owned else 0})
    actions = []
    run_lines([*lines[start:cleanup - 1], "terminate_this_script"], state, executed=actions)
    assert ("delete_object $1787" in actions) == (not owned)
    actions.clear()
    run_lines([*lines[cleanup:], "terminate_this_script", *routines], state, executed=actions)
    creations = [line for line in actions if line.startswith("create_object_no_offset ")]
    assert len(creations) == (0 if owned else 2)
    if not owned:
        assert "$1787" in creations[0] and "$1788" in creations[1]
        assert actions.index("load_all_models_now") < actions.index(creations[0])
    assert state[f"${mansion.MANSION_APPLIED}"] == owned
    assert state["$1001"] == (2 if owned else 0)
    assert not any(line.startswith(("create_pickup", "switch_car_generator", "start_new_script")) for line in actions)


@pytest.mark.parametrize("owned", (0, 1))
@pytest.mark.parametrize("prepared", (0, 1))
def test_cleanup_restores_current_ownership_without_regranting_items(owned, prepared):
    lines = source_lines()
    changes, routines = mansion.mansion_changes(lines, "quest_giver_progress")
    preparation = next(replacement for _, _, replacement in changes
                       if f"${mansion.MANSION_PREPARED} = 1" in replacement)
    state = defaultdict(int, {f"${mansion.MANSION_APPLIED}": owned, "$1001": 2 if owned else 0})
    actions = []
    if prepared:
        run_lines([*preparation, "terminate_this_script", *routines], state, executed=actions)
        assert state["$1001"] == 1
        if owned:
            assert "delete_object $1789" in actions
            assert "create_object_no_offset $1788 = init_object #SYNTH_CLOSED_FRONT at 0 0 0" in actions
        else:
            assert "delete_object $1787" in actions
    actions.clear()
    started = run_lines([f"gosub @{mansion.RESTORE_LABEL}", "terminate_this_script", *routines],
                        state, executed=actions)
    assert started == []
    assert state[f"${mansion.MANSION_APPLIED}"] == owned
    assert state[f"${mansion.MANSION_PREPARED}"] == 0
    assert state["$1001"] == (2 if owned else 0)
    creations = [line for line in actions if line.startswith("create_object_no_offset ")]
    handle, model = (1789, "OPEN_FRONT") if owned else (1787, "CLOSED_BACK")
    expected = f"create_object_no_offset ${handle} = init_object #SYNTH_{model} at 0 0 0"
    assert creations == ([expected] if prepared else [])
    assert not any(line.startswith(("create_pickup", "create_clothes", "switch_car_generator")) for line in actions)
    # Repeated cleanup does not recreate doors, even after a save round trip.
    state = defaultdict(int, dict(state))
    actions.clear()
    run_lines([f"gosub @{mansion.RESTORE_LABEL}", "terminate_this_script", *routines], state, executed=actions)
    assert not any(line.startswith("create_object") for line in actions)


def test_doors_load_before_remote_creation_and_restore_does_not_yield():
    _, routines = mansion.mansion_changes(source_lines(), "mission_completion")
    state = defaultdict(int)
    actions = []
    run_lines([f"gosub @{mansion.MANSION_LABEL}", "terminate_this_script", *routines], state, executed=actions)
    created = next(index for index, line in enumerate(actions) if line.startswith("create_object ")
                   or line.startswith("create_object_no_offset "))
    loaded = actions.index("load_all_models_now")
    assert loaded < created
    assert len([line for line in actions[:loaded] if line.startswith("request_model ")]) == 3
    assert len([line for line in actions if line.startswith("mark_model_as_no_longer_needed ")]) == 3
    assert not any(line.startswith("wait ") for line in routines)


@pytest.mark.parametrize("trigger", (10357, 10358))
def test_transfer_grants_once_and_cannot_reset_scene_on_repeated_completion(trigger):
    _, routines = mansion.mansion_changes(source_lines(), "mission_completion")
    state = defaultdict(int, {f"${trigger}": 3})
    program = [*mansion.mansion_event_lines(trigger), "terminate_this_script", *routines]
    assert run_lines(program, state) == []
    state[f"${trigger}"] = 16
    assert run_lines(program, state) == ["PSAVE2"]
    assert state[f"${mansion.MANSION_APPLIED}"] == 1
    assert state["$1001"] == 2
    assert state[mansion.NATIVE_PASSED] == 0
    assert state["$1278"] == state["$855"] == state["$906"] == state["$907"] == 1
    assert run_lines(program, defaultdict(int, dict(state))) == []


@pytest.mark.parametrize("change", ("missing", "local", "grant", "population", "threat", "door"))
def test_changed_source_is_rejected_without_mutation(change):
    lines = source_lines()
    if change == "missing":
        lines.remove("start_new_script @PSAVE2")
    elif change == "local":
        lines[lines.index("create_pickup $79 = synthetic_health")] = "create_pickup 0@ = synthetic_health"
    elif change == "grant":
        lines.insert(lines.index("start_new_script @PSAVE2"), "start_new_script @UNKNOWN")
    elif change == "population":
        lines.remove("set_zone_ped_info 'GANG1' 1 13 0 0 0 1000 0 0 0 0 0 0")
    elif change == "threat":
        lines.append("set_threat_for_ped_type 10 add_threat 1")
    else:
        lines[lines.index("$1001 = 2")] = "$1001 = 3"
    before = lines.copy()
    with pytest.raises(AssertionError, match="mansion"):
        mansion.mansion_changes(lines, "quest_giver_progress")
    assert lines == before
