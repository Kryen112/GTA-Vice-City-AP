"""Shakedown's mission check and business availability have independent triggers."""

import importlib
from collections import defaultdict

import pytest
from test_mission_dispatch import dispatch, synthetic_source
from test_mission_order import mission_order, run_lines

effects = importlib.import_module("mission_world_effects")
APPLIED = dispatch.BUSINESS_SALES_APPLIED
BUY_THREADS = effects.BUSINESS_BUY_THREADS


def execute(body, state, timing):
    return run_lines([*body, "terminate_this_script", *dispatch.dispatcher_lines([3, 31], business_timing=timing),
                      ":AP_OPEN_BUSINESSES", *[f"start_new_script @{thread}" for thread in BUY_THREADS],
                      "return"], state)


@pytest.mark.parametrize("timing", dispatch.WORLD_EVENT_TIMINGS)
def test_failure_retry_cleanup_timing_once_only_and_save_reload(timing):
    state = defaultdict(int)
    # Rosenberg's first slot contains Shakedown; an attempted mission grants nothing.
    assert execute(dispatch.launch_lines(3, 31), state, timing) == [31]
    execute(dispatch.finish_lines(31, "$9079"), state, timing)
    assert state[f"${APPLIED}"] == state["$9079"] == state[f"${dispatch.SLOT_BASE + 3}"] == 0
    execute(dispatch.launch_lines(3, 31), state, timing)
    assert execute(dispatch.success_lines(31), state, timing) == []
    assert state[f"${APPLIED}"] == state["$9079"] == 0
    opened = execute(dispatch.finish_lines(31, "$9079"), state, timing)
    expected = timing == "mission_completion"
    assert opened == (list(BUY_THREADS) if expected else [])
    assert state[f"${APPLIED}"] == expected
    assert state["$9079"] == state[f"${dispatch.SLOT_BASE + 3}"] == 1
    assert state["$9059"] == state[f"${dispatch.SLOT_BASE + 31}"] == 0
    # Offline local progress survives restoration without using AP checked history.
    state = defaultdict(int, dict(state))
    execute(dispatch.launch_lines(31, 3), state, timing)
    execute(dispatch.success_lines(3), state, timing)
    opened = execute(dispatch.finish_lines(3, "$9059"), state, timing)
    assert opened == ([] if expected else list(BUY_THREADS))
    assert state[f"${APPLIED}"] == state["$9059"] == state[f"${dispatch.SLOT_BASE + 31}"] == 1
    # Repeated successful finishes cannot restart buy threads or recreate purchase pickups.
    for slot, payload in ((3, 31), (31, 3)):
        execute(dispatch.launch_lines(slot, payload), state, timing)
        execute(dispatch.success_lines(payload), state, timing)
        assert execute(dispatch.finish_lines(payload), state, timing) == []


@pytest.mark.parametrize("timing", dispatch.WORLD_EVENT_TIMINGS)
def test_unrelated_payload_cannot_apply_business_event(timing):
    state = defaultdict(int)
    execute(dispatch.launch_lines(3, 31), state, timing)
    execute(dispatch.success_lines(31), state, timing)
    assert execute(dispatch.finish_lines(3), state, timing) == []
    assert state[f"${APPLIED}"] == 0
    assert state[f"${dispatch.ACTIVE_MISSION}"] == 31


@pytest.mark.parametrize("timing", dispatch.WORLD_EVENT_TIMINGS)
def test_runtime_trigger_matches_the_worlds_resolved_event_slot(timing):
    strands = {"Rosenberg": ["The Party"], "Vercetti Protection": ["Shakedown"]}
    assignment = {"Rosenberg": ["Shakedown"], "Vercetti Protection": ["The Party"]}
    expected = mission_order.event_trigger_slot(strands, assignment, "Shakedown", timing)
    identities = {3: ("Rosenberg", 0), 31: ("Vercetti Protection", 0)}
    for slot, payload in dispatch.SHAKEDOWN_SMOKE_ASSIGNMENT.items():
        state = defaultdict(int)
        execute(dispatch.launch_lines(slot, payload), state, timing)
        execute(dispatch.success_lines(payload), state, timing)
        opened = execute(dispatch.finish_lines(payload), state, timing)
        assert bool(opened) == (identities[slot] == expected)


def shakedown_source():
    lines = synthetic_source()
    entry = lines.index(":GEN1")
    lines[entry:entry] = [":AP_OPEN_BUSINESSES", *[f"start_new_script @{thread}" for thread in BUY_THREADS],
                        "return", ":PRO1", "script_name 'PRO1'", "if ", "  $266 == 1",
                        "goto_if_false @PRO1_START", "$9079 = 1", "terminate_this_script", ":PRO1_START",
                        "print_big 'PROT1' 15000 ms 2", "load_and_launch_mission_internal 31", "goto @PRO1"]
    lines += ["//-------------Mission 31---------------", "script_name 'PROTEC1'",
              "gosub @AP_OPEN_BUSINESSES", "print_now 'BUYP1' time 8000 1", ":PROTEC1_6843",
              "set_car_density_multiplier 1.0", "$266 = 1", "gosub @CLEANUP", "terminate_this_script",
              "script_name 'PROTEC2'"]
    # These three objects control narrative and mansion decoration.
    lines += [":CELL_6836", "  $266 == 1", ":CELL_14699", "  $266 == 1", ":PICKUPS_882", "  $266 == 0"]
    return lines


@pytest.mark.parametrize("timing", dispatch.WORLD_EVENT_TIMINGS)
def test_transform_owns_only_sales_and_preserves_mission_native_consumers(timing):
    lines = shakedown_source()
    markers = [{"launcher": "LAW1", "passed": "$passed"}, {"launcher": "PRO1", "passed": "$266"}]
    dispatch.instrument_identity_dispatch(lines, markers, shakedown_smoke=True, world_event_timing=timing)
    assert lines.count("gosub @AP_OPEN_BUSINESSES") == 1
    assert lines.index("gosub @AP_OPEN_BUSINESSES") < lines.index("script_name 'PROTEC1'")
    mission = lines.index("script_name 'PROTEC1'")
    assert lines[mission + 1] == ("goto @PROTEC1_6843" if timing == "quest_giver_progress"
                                 else "print_now 'BUYP1' time 8000 1")
    assert "$266 = 1" in lines
    for label, condition in (("CELL_6836", "  $266 == 1"), ("CELL_14699", "  $266 == 1"),
                             ("PICKUPS_882", "  $266 == 0")):
        assert lines[lines.index(f":{label}") + 1] == condition
    assert lines.count(f"${APPLIED} = 0") == 1
    assert lines[lines.index("script_name 'HOT'") + 1] == f"${APPLIED} = 0"
    for slot, payload in dispatch.SHAKEDOWN_SMOKE_ASSIGNMENT.items():
        start = lines.index(f"${dispatch.ACTIVE_SLOT} = {slot}")
        assert lines[start:start + 4] == dispatch.launch_lines(slot, payload)
    # Native pass and its AP check remain payload-owned, while the giver guard reads its slot.
    cleanup = lines.index("gosub @CLEANUP", mission)
    finish = dispatch.finish_lines(31, "$9079")
    assert lines[cleanup + 1:cleanup + 1 + len(finish)] == finish
    assert markers[1]["passed"] == f"${dispatch.SLOT_BASE + 31}"


@pytest.mark.parametrize("change", ["call", "duplicate", "restoration", "overlap", "timing"])
def test_invalid_event_source_rejects_without_partial_edits(change):
    lines = shakedown_source()
    if change == "call":
        lines.remove("gosub @AP_OPEN_BUSINESSES")
    elif change == "duplicate":
        lines.append("gosub @AP_OPEN_BUSINESSES")
    elif change == "restoration":
        lines[lines.index("set_car_density_multiplier 1.0")] = "wait 0"
    elif change == "overlap":
        lines.append(f"${APPLIED} = 0")
    original = lines.copy()
    markers = [{"launcher": "LAW1", "passed": "$passed"}, {"launcher": "PRO1", "passed": "$266"}]
    with pytest.raises(AssertionError):
        dispatch.instrument_identity_dispatch(lines, markers, shakedown_smoke=True,
                                             world_event_timing="invalid" if change == "timing"
                                             else "quest_giver_progress")
    assert lines == original
    assert markers[1]["passed"] == "$266"
