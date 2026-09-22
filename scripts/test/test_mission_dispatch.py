"""Execute the identity dispatcher's emitted launch and completion instructions."""

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import pytest
from test_mission_order import run_lines

SOURCE = Path(__file__).resolve().parents[2] / "mod/scm/mission_dispatch.py"
sys.path.append(str(SOURCE.parent))
specification = importlib.util.spec_from_file_location("mission_dispatch", SOURCE)
dispatch = importlib.util.module_from_spec(specification)
specification.loader.exec_module(dispatch)


def execute(body, state):
    return run_lines([*body, "terminate_this_script", *dispatch.dispatcher_lines([3, 7])], state)


def test_launch_failure_retry_and_saved_completion():
    state = defaultdict(int)
    assert execute(dispatch.launch_lines(3), state) == [3]
    assert state[f"${dispatch.ACTIVE_SLOT}"] == 3
    assert state[f"${dispatch.SLOT_BASE + 3}"] == 0
    execute(dispatch.finish_lines(3), state)
    assert state[f"${dispatch.ACTIVE_SLOT}"] == 0
    assert state[f"${dispatch.SLOT_BASE + 3}"] == 0
    execute(dispatch.launch_lines(3), state)
    execute(dispatch.success_lines(3), state)
    assert state[f"${dispatch.SLOT_BASE + 3}"] == 0  # Cleanup has not returned.
    execute(dispatch.finish_lines(3), state)
    saved = dict(state)
    assert saved[f"${dispatch.SLOT_BASE + 3}"] == 1
    assert all(saved[f"${word}"] == 0 for word in (dispatch.ACTIVE_SLOT, dispatch.ACTIVE_MISSION, dispatch.SUCCESS))
    restored = defaultdict(int, saved)
    execute([*dispatch.launch_lines(7), *dispatch.finish_lines(7)], restored)
    assert restored[f"${dispatch.SLOT_BASE + 3}"] == 1
    assert restored[f"${dispatch.SLOT_BASE + 7}"] == 0


@pytest.mark.parametrize("payload", [72, 73, 74])
def test_taxi_audio_intro_restores_foreign_launcher_scene(payload):
    source = [f"script_name 'TAXWAR{payload - 71}'", "wait 0", "load_mission_audio 'INTRO' as 1"]
    spans = {payload: (0, len(source))}
    [(index, removed, lines)] = dispatch.non_cutscene_intro_changes(source, spans, 10, payload, (0, 0))
    assert index == 1 and removed == 0  # Inside the payload, leaving saved MAIN offsets intact.
    # Reproduce Cortez's entry state. Restore it before launching the payload,
    # whose opening only plays audio and eventually re-enables player control.
    streaming, camera, visible = False, "giver", False
    for line in [*lines, "gosub @AP_DISPATCH"]:
        if line == "switch_streaming 1":
            streaming = True
        elif line == "restore_camera_jumpcut":
            camera = "player"
        elif line == "do_fade 1 500":
            visible = True
        elif line == "gosub @AP_DISPATCH":
            assert streaming and visible and camera == "player"
    for slot in (72, 73, 74):
        assert dispatch.non_cutscene_intro_changes(source, spans, slot, payload, (0, 0)) == []
    assert dispatch.non_cutscene_intro_changes(source, spans, 10, 35, (0, 0)) == []
    with pytest.raises(AssertionError, match="mission entry"):
        dispatch.non_cutscene_intro_changes(["wrong mission"], {payload: (0, 1)}, 10, payload, (0, 0))


@pytest.mark.parametrize("payload", [72, 73, 74])
def test_foreign_taxi_intro_does_not_inherit_cutscene_input_lock(payload):
    source = ["gosub @HELP_3202", "gosub @HELP_2883", "gosub @HELP_2932",
              f"script_name 'TAXWAR{payload - 71}'", "wait 0",
              "set_player_control $player_char can_move True"]
    edits = dispatch.non_cutscene_intro_changes(source, {payload: (3, len(source))}, 10, payload, (0, 3))
    for index, removed, replacement in sorted(edits, reverse=True):
        source[index:index + removed] = replacement
    cutscene_lock = normal_lock = False
    for line in source:
        if line == "gosub @HELP_2883":
            cutscene_lock = True
        elif line == "set_player_control $player_char can_move False":
            normal_lock = True
        elif line == "set_player_control $player_char can_move True":
            normal_lock = False
    assert not normal_lock and not cutscene_lock
    assert source[:3] == ["gosub @HELP_3202", "set_player_control $player_char can_move False",
                          "gosub @HELP_2932"]


@pytest.mark.parametrize("payload", range(67, 72))
@pytest.mark.parametrize("launcher", [
    ["gosub @HELP_2883"],
    ["make_player_safe_for_cutscene $player_char", "gosub @HELP_2883"],
    ["make_player_safe_for_cutscene $player_char"],
])
def test_phone_intro_loads_exterior_before_teleport_and_releases_normal_control(payload, launcher):
    destination = "-977.4625 -530.668 9.9113"
    source = [*launcher, f"script_name 'ASSIN{payload - 66}'", "wait 0",
              f"set_player_coordinates $player_char at {destination}", "do_fade 1 500",
              "set_player_control $player_char can_move True"]
    spans = {payload: (len(launcher), len(source))}
    assert dispatch.non_cutscene_intro_changes(source, spans, payload, payload, (0, 1)) == []
    edits = dispatch.non_cutscene_intro_changes(source, spans, 25, payload, (0, len(launcher)))
    for index, removed, replacement in sorted(edits, reverse=True):
        source[index:index + removed] = replacement
    streaming, exterior, collision, loaded, cutscene_lock, controls = False, False, False, False, False, True
    for line in source:
        if line in ("gosub @HELP_2883", "make_player_safe_for_cutscene $player_char"):
            cutscene_lock = True
        elif line.startswith("set_player_control "):
            controls = line.endswith("True")
        elif line == "switch_streaming 1":
            streaming = True
        elif line == "set_area_visible 0":
            exterior = True
        elif line == "request_collision -977.4625 -530.668":
            collision = True
        elif line == f"load_scene {destination}":
            assert streaming and exterior and collision
            loaded = True
        elif line.startswith("set_player_coordinates "):
            assert loaded and not controls and not cutscene_lock
    assert controls and not cutscene_lock
    assert source.count(f"load_scene {destination}") == 1
    with pytest.raises(AssertionError, match="exterior relocation"):
        dispatch.non_cutscene_intro_changes(["script_name 'ASSIN5'"], {71: (0, 1)}, 25, 71, (0, 0))


def test_unrelated_payload_cannot_complete_or_clear_an_active_slot():
    state = defaultdict(int)
    execute(dispatch.launch_lines(3), state)
    execute([*dispatch.success_lines(7), *dispatch.finish_lines(7)], state)
    assert state[f"${dispatch.ACTIVE_SLOT}"] == 3
    assert state[f"${dispatch.SUCCESS}"] == 0
    assert state[f"${dispatch.SLOT_BASE + 3}"] == 0
    # A new accepted launch replaces a stale attempt without inheriting success.
    state[f"${dispatch.SUCCESS}"] = 1
    execute(dispatch.launch_lines(7), state)
    assert state[f"${dispatch.SUCCESS}"] == 0


def test_finale_warp_uses_the_same_slot_and_resets_stale_success():
    lines = synthetic_source()
    entry = lines.index(":GEN1")
    lines[entry:entry] = [":FIN2", "script_name 'FIN2'", "if ", "  $finale == 1",
                        "goto_if_false @FIN2_START", "$9101 = 1", "terminate_this_script", ":FIN2_START",
                        "load_and_launch_mission_internal 52", "goto @FIN2",
                        ":APFIN", "script_name 'APFIN'", "load_and_launch_mission_internal 52", "goto @APFIN"]
    lines += ["//-------------Mission 52---------------", "$finale = 1", "terminate_this_script"]
    dispatch.instrument_identity_dispatch(lines, [{"launcher": "FIN2", "passed": "$finale"}])
    warp = lines.index("script_name 'APFIN'") + 1
    assert lines[warp:warp + 4] == dispatch.launch_lines(52)
    state = defaultdict(int, {f"${dispatch.ACTIVE_MISSION}": 52, f"${dispatch.SUCCESS}": 1})
    program = [*lines[warp:warp + 4], *dispatch.finish_lines(52), "terminate_this_script",
               *dispatch.dispatcher_lines([52])]
    run_lines(program, state)
    assert state[f"${dispatch.SLOT_BASE + 52}"] == 0
    run_lines([*dispatch.launch_lines(52), *dispatch.success_lines(52), *dispatch.finish_lines(52),
               "terminate_this_script", *dispatch.dispatcher_lines([52])], state)
    assert state[f"${dispatch.SLOT_BASE + 52}"] == 1


def test_finale_warp_credits_the_destination_of_the_finale_payload(monkeypatch):
    import mission_returns

    monkeypatch.setattr(dispatch, "SMOKE_ASSIGNMENT", {3: 52, 52: 3})
    monkeypatch.setitem(mission_returns.ENDING_RELOCATIONS, 52, ())
    lines = synthetic_source()
    entry = lines.index(":GEN1")
    lines[entry:entry] = [":FIN2", "script_name 'FIN2'", "if ", "  $finale == 1",
                        "goto_if_false @FIN2_START", "$9101 = 1", "terminate_this_script", ":FIN2_START",
                        "print_big 'FINALE' 15000 ms 2", "load_and_launch_mission_internal 52", "goto @FIN2",
                        ":APFIN", "script_name 'APFIN'", "load_and_launch_mission_internal 52", "goto @APFIN"]
    lines += ["//-------------Mission 52---------------", "$finale = 1", "terminate_this_script"]
    dispatch.instrument_identity_dispatch(lines, [{"launcher": "LAW1", "passed": "$passed"},
                                                 {"launcher": "FIN2", "passed": "$finale"}], smoke=True)
    warp = lines.index("script_name 'APFIN'") + 1
    assert lines[warp:warp + 4] == dispatch.launch_lines(3, 52)
    state = defaultdict(int)
    run_lines([*lines[warp:warp + 4], *dispatch.success_lines(52), *dispatch.finish_lines(52),
               "terminate_this_script", *dispatch.dispatcher_lines([3, 52])], state)
    assert state[f"${dispatch.SLOT_BASE + 3}"] == 1
    assert state[f"${dispatch.SLOT_BASE + 52}"] == 0


def synthetic_source():
    records = [("HOT", 2, "$222"), ("LAW1", 3, "$passed"), ("GEN1", 7, "$swine"),
               ("ICE1", 83, "$612"), ("COKRUN", 96, "$607")]
    lines = []
    for launcher, number, passed in records:
        lines += [f":{launcher}", f"script_name '{launcher}'", "wait 0", "if ",
                  f"  {passed} == 1", f"goto_if_false @{launcher}_START", f"${9056 + number} = 1",
                  "terminate_this_script", f":{launcher}_START", f"print_big 'MISSION{number}' 15000 ms 2",
                  f"load_and_launch_mission_internal {number}", f"goto @{launcher}"]
    lines += [":OTHER", "script_name 'OTHER'", "terminate_this_script"]
    for launcher, number, passed in records:
        lines += [f"//-------------Mission {number}---------------", f":PAYLOAD_{launcher}",
                  f"{passed} = 1", "gosub @CLEANUP", "terminate_this_script"]
    return lines


def test_transform_changes_slot_guards_but_preserves_world_flags_and_cleanup():
    lines = synthetic_source()
    markers = [{"launcher": "LAW1", "passed": "$passed"}]
    dispatch.instrument_identity_dispatch(lines, markers)
    assert markers[0]["passed"] == f"${dispatch.SLOT_BASE + 3}"
    assert "  $passed == 1" not in lines
    assert "$passed = 1" in lines
    assert "  $612 == 1" in lines  # Distribution remains replayable.
    start = lines.index(":PAYLOAD_LAW1")
    cleanup = lines.index("gosub @CLEANUP", start)
    finish = dispatch.finish_lines(3, "$9059")
    assert lines[cleanup + 1:cleanup + 1 + len(finish)] == finish
    assert "$9059 = 1" not in lines[:lines.index(":PAYLOAD_LAW1")]
    original = lines.copy()
    with pytest.raises(AssertionError, match="already installed"):
        dispatch.instrument_identity_dispatch(lines, markers)
    assert lines == original


@pytest.mark.parametrize("change", ["overlap", "success", "exit", "payload"])
def test_invalid_source_is_rejected_without_partial_edits(change):
    lines = synthetic_source()
    if change == "overlap":
        lines.append(f"${dispatch.ACTIVE_SLOT} = 0")
    elif change == "success":
        lines.remove("$passed = 1")
    elif change == "exit":
        lines.append("terminate_this_script")
    else:
        lines.insert(lines.index("load_and_launch_mission_internal 3"), "load_and_launch_mission_internal 7")
    original = lines.copy()
    markers = [{"launcher": "LAW1", "passed": "$passed"}]
    with pytest.raises(AssertionError):
        dispatch.instrument_identity_dispatch(lines, markers)
    assert lines == original
    assert markers == [{"launcher": "LAW1", "passed": "$passed"}]


def test_cross_giver_payload_reports_its_check_and_advances_the_destination_slot():
    lines = synthetic_source()
    markers = [{"launcher": "LAW1", "passed": "$passed"}, {"launcher": "GEN1", "passed": "$swine"}]
    dispatch.instrument_identity_dispatch(lines, markers, smoke=True)
    for slot, payload in dispatch.SMOKE_ASSIGNMENT.items():
        start = lines.index(f"${dispatch.ACTIVE_SLOT} = {slot}")
        assert lines[start:start + 4] == dispatch.launch_lines(slot, payload)
        state = defaultdict(int)
        assert execute(lines[start:start + 4], state) == [payload]
        execute(dispatch.finish_lines(payload, f"${9056 + payload}"), state)
        assert state[f"${dispatch.SLOT_BASE + slot}"] == 0
        assert state[f"${9056 + payload}"] == 0
        execute(lines[start:start + 4], state)
        execute(dispatch.success_lines(payload), state)
        execute(dispatch.finish_lines(payload, f"${9056 + payload}"), state)
        assert state[f"${dispatch.SLOT_BASE + slot}"] == 1
        assert state[f"${dispatch.SLOT_BASE + payload}"] == 0
        assert state[f"${9056 + payload}"] == 1
        assert state[f"${9056 + slot}"] == 0
    law_start, cortez_start = lines.index(":LAW1"), lines.index(":GEN1")
    assert "print_big 'MISSION7' 15000 ms 2" in lines[law_start:cortez_start]
    assert "print_big 'MISSION3' 15000 ms 2" in lines[cortez_start:lines.index(":ICE1")]


@pytest.mark.parametrize("success", [0, 1])
@pytest.mark.parametrize("pending,playing,death,vehicle,slot,relocate", [
    (0, True, False, False, 3, False), (1, True, False, False, 3, True),
    (1, True, False, True, 3, True), (1, False, False, False, 3, False),
    (1, True, True, False, 3, False), (1, True, False, False, 60, False),
])
def test_return_requires_an_actual_ending_relocation_and_preserves_native_respawns(
        pending, playing, death, vehicle, slot, relocate, success):
    point = ("110.6", "-824.2", "9.6", "327.9")
    state = defaultdict(int, {f"${dispatch.RETURN_PENDING}": pending,
                             f"${dispatch.ACTIVE_SLOT}": slot, f"${dispatch.ACTIVE_MISSION}": 60,
                             f"${dispatch.SUCCESS}": success, "$991": 1, "$1001": 2})
    actions = []
    conditions = {"is_player_playing $player_char": playing,
                  "not has_deatharrest_been_executed": not death,
                  "not is_player_in_any_car $player_char": not vehicle}
    interior_flags = (989, 986, 1002, 1003, 1088, 987, 988, 990, 991)
    state.update({f"${flag}": 1 for flag in interior_flags})
    program = [*dispatch.finish_lines(60), "terminate_this_script", *dispatch.dispatcher_lines([3, 60], {3: point})]
    run_lines(program, state, conditions=conditions, executed=actions)
    moves = [line for line in actions if line.startswith(("set_player_coordinates", "warp_player_from_car_to_coord"))]
    expected = "warp_player_from_car_to_coord" if vehicle else "set_player_coordinates"
    assert moves == ([f"{expected} $player_char at 110.6 -824.2 9.6"] if relocate else [])
    # Outdoor returns clear every interio.
    assert all(state[f"${flag}"] == (0 if relocate else 1) for flag in interior_flags)
    assert state["$1001"] == 2
    assert state[f"${dispatch.RETURN_PENDING}"] == 0
    assert state[f"${dispatch.ACTIVE_MISSION}"] == 0
    assert state[f"${dispatch.SLOT_BASE + slot}"] == success
    assert actions.count("wait 0") == (2 if relocate else 0)
    assert state["$onmission"] == 0
    # A new launch cannot inherit a previous run's ending relocation.
    state[f"${dispatch.RETURN_PENDING}"] = 1
    run_lines([*dispatch.launch_lines(3, 60), "terminate_this_script",
               *dispatch.dispatcher_lines([3, 60], {3: point})], state)
    assert state[f"${dispatch.RETURN_PENDING}"] == 0


def return_source():
    lines = synthetic_source()
    start = lines.index(":LAW1_START") + 1
    lines.insert(start, "  locate_player_on_foot_3d $player_char 0 119.2 -826.9 9.7 radius 1.2 1.2 2.0")
    start = lines.index(":PAYLOAD_LAW1") + 1
    lines.insert(start, "set_shortcut_dropoff_point_for_mission 110.6 -824.2 9.6 327.9")
    entry = lines.index(":OTHER")
    lines[entry:entry] = [":HAT1", "script_name 'HAT1'", "if ", "  $juju == 1", "goto_if_false @HAT1_START",
                        "$9089 = 1", "terminate_this_script", ":HAT1_START", "print_big 'HAT_1' 15000 ms 2",
                        "load_and_launch_mission_internal 60", "goto @HAT1"]
    lines += ["//-------------Mission 60---------------", ":HAIT1_INTRO",
              "set_player_coordinates $player_char at 1.0 2.0 3.0", ":HAIT1_5407",
              "set_player_coordinates $player_char at 4.0 5.0 6.0", "$juju = 1", "terminate_this_script"]
    return lines


def test_only_the_audited_ending_sets_pending_and_return_uses_the_source_dropoff():
    lines = return_source()
    markers = [{"launcher": "LAW1", "passed": "$passed"}, {"launcher": "HAT1", "passed": "$juju"}]
    dispatch.instrument_identity_dispatch(lines, markers, return_smoke=True)
    intro = lines.index("set_player_coordinates $player_char at 1.0 2.0 3.0")
    ending = lines.index("set_player_coordinates $player_char at 4.0 5.0 6.0")
    assert lines[intro + 1] == ":HAIT1_5407"
    assert lines[ending + 1] == f"${dispatch.RETURN_PENDING} = 1"
    assert lines.count(f"${dispatch.RETURN_PENDING} = 1") == 1
    assert "set_player_coordinates $player_char at 110.6 -824.2 9.6" in lines


def test_missing_or_unsafe_source_return_data_is_rejected_without_mutation():
    for replacement in ("", "set_shortcut_dropoff_point_for_mission 119.2 -826.9 9.7 0.0"):
        lines = return_source()
        index = lines.index("set_shortcut_dropoff_point_for_mission 110.6 -824.2 9.6 327.9")
        lines[index] = replacement
        original = lines.copy()
        markers = [{"launcher": "LAW1", "passed": "$passed"}, {"launcher": "HAT1", "passed": "$juju"}]
        with pytest.raises(AssertionError, match="return point"):
            dispatch.instrument_identity_dispatch(lines, markers, return_smoke=True)
        assert lines == original
