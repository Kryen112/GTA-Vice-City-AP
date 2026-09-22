"""Execute temporary barrier changes against changing item ownership."""

# ruff: noqa: I001 -- test_mission_dispatch establishes the SCM module path.

import ast
import itertools
from collections import defaultdict
from pathlib import Path

import pytest
from test_mission_dispatch import dispatch
from test_mission_order import run_lines

from mission_access import EXTRA_TRAVEL_MISSIONS, needs_travel, route_lines
from mission_returns import return_lines


def travel_source():
    source = [":APAREA"]
    for handle in (1781, 1782, 1783, 1780, 1779):
        source += [f"switch_roads_on {handle} 0.0 0.0 1.0 1.0 1.0", f"delete_object ${handle}"]
        if handle in (1779, 1780):
            source += [f"create_object_no_offset ${handle} = init_object #COMGATEOPEN at 8.0 8.0 8.0"]
    source += [":APAREA_SHARED"]
    for handle in (1779, 1780, 1781, 1782, 1783):
        source += [f"create_object_no_offset ${handle} = init_object #COMGATECLOSED at 1.0 2.0 3.0"]
    return source


def execute_routes(body, state, objects):
    # Collapse multi-condition blocks for the shared scalar-instruction interpreter.
    program, predicates = [], {}
    index = 0
    while index < len(body):
        line = body[index]
        index += 1
        if line.startswith("if"):
            tests = []
            while index < len(body) and body[index].startswith("  "):
                tokens = body[index].split()
                tests.append(state[tokens[0]] >= int(tokens[2]) if tokens[0].startswith("$")
                             else int(tokens[-1][1:]) in objects)
                index += 1
            name = f"predicate_{index}"
            predicates[name] = any(tests) if line == "if or" else all(tests)
            program += ["if ", f"  {name}"]
        else:
            program.append(line)
    actions = []
    run_lines(program, state, conditions=predicates, executed=actions)
    return [line for line in actions if line.startswith(("set_object_coordinates", "switch_roads"))]


def test_temporary_routes_restore_current_items_without_granting_content():
    source = travel_source()
    opening, closing = route_lines(source, restore=False), route_lines(source, restore=True)
    objects = {1779, 1780, 1781, 1782, 1783}
    state = defaultdict(int)
    opened = execute_routes(opening, state, objects)
    assert len(opened) == 10
    for line in opened:
        if line.startswith("set_object_coordinates"):
            requested_z = float(line.split()[-1])
            # The native opcode substitutes ground height for Z <= -100.
            actual_z = 10.0 if requested_z <= -100.0 else requested_z
            assert actual_z < -50.0
    for counts in itertools.product((0, 1), repeat=6):
        state = defaultdict(int, {f"${9030 + index}": count for index, count in enumerate(counts)})
        before = dict(state)
        actions = execute_routes(closing, state, objects)
        restored = {int(line.split()[1][1:]) for line in actions if line.startswith("set_object")}
        mainland, starfish, prawn, leaf, ocean, west = counts
        assert restored == {handle for handle, owned in (
            (1781, mainland or prawn), (1782, mainland or leaf), (1783, mainland or ocean),
            (1780, starfish), (1779, starfish and (mainland or west))) if not owned}
        assert dict(state) == before
    assert execute_routes(closing, defaultdict(int), set()) == []
    assert not any(line.startswith(("$", "gosub", "wait")) for line in opening + closing)


def test_forced_return_covers_failure_and_identity_but_preserves_respawn():
    for playing, died in itertools.product((False, True), repeat=2):
        state = defaultdict(int, {f"${dispatch.ACTIVE_SLOT}": 12, f"${dispatch.ACTIVE_MISSION}": 12})
        actions = []
        run_lines(["gosub @AP_RETURN", "terminate_this_script",
                   *return_lines({12: ("1.0", "2.0", "3.0", "4.0")},
                                 dispatch.ACTIVE_SLOT, dispatch.ACTIVE_MISSION, force=True)], state,
                  conditions={"is_player_playing $player_char": playing,
                              "not has_deatharrest_been_executed": not died,
                              "not is_player_in_any_car $player_char": True}, executed=actions)
        assert any(line.startswith("set_player_coordinates") for line in actions) == (playing and not died)


def test_extra_travel_mirrors_direct_world_requirements():
    source = Path(__file__).resolve().parents[2] / "apworld/gta_vice_city/data.py"
    tree = ast.parse(source.read_text())
    table = next(node.value for node in tree.body if isinstance(node, ast.AnnAssign)
                 and node.target.id == "MISSION_REGION_REQUIREMENTS")
    assert set(EXTRA_TRAVEL_MISSIONS.values()) == {ast.literal_eval(key) for key in table.keys}
    assert needs_travel(72, "TWAR1") and needs_travel(12, "BAR1") and needs_travel(10, "GEN4")
    assert not needs_travel(3, "LAW1")


def test_dispatch_opens_before_payload_and_restores_after_return():
    from test_mission_dispatch import return_source

    source = return_source()
    source.insert(source.index(":HAIT1_INTRO") + 1, "script_name 'HAIT1'")
    dispatch.instrument_identity_dispatch(source, [{"launcher": "LAW1", "passed": "$passed"},
                                                  {"launcher": "HAT1", "passed": "$juju"}],
                                          return_smoke=True, travel_source=travel_source())
    entry = source.index("script_name 'HAIT1'")
    assert source[entry + 1] == "gosub @AP_TRAVEL_BEGIN_60"
    cleanup = source.index("gosub @AP_RETURN_PAYLOAD_60")
    assert source[cleanup + 1] == "gosub @AP_TRAVEL_END_60"
    finish = source.index("gosub @AP_DISPATCH_FINISH", cleanup)
    assert cleanup < finish < source.index(":AP_RETURN_PAYLOAD_60")
    assert not any(line.startswith("wait ") for line in source[cleanup:finish])
    body = source[source.index(":AP_RETURN_PAYLOAD_60"):source.index(":AP_TRAVEL_BEGIN_60")]
    assert f"  ${dispatch.RETURN_PENDING} == 1" not in body


def test_phone_return_captures_position_without_touching_access_items():
    from mission_returns import PHONE_RETURN_POSITION, giver_return_point

    point = giver_return_point([], (0, 0), "ASSIN_5")
    assert point == tuple(f"${PHONE_RETURN_POSITION + index}" for index in range(4))
    lines = dispatch.launch_lines(71, 12, capture_phone=True)
    assert lines[:2] == ["get_player_coordinates $player_char position_to $10353 $10354 $10355",
                         "get_player_heading $10356 = player $player_char"]
    assert lines[2:] == dispatch.launch_lines(71, 12)


@pytest.mark.parametrize("died_during_hold", [False, True])
def test_return_holds_entry_gates_until_movement_resynchronizes(died_during_hold):
    state = defaultdict(int, {f"${dispatch.ACTIVE_SLOT}": 4, f"${dispatch.ACTIVE_MISSION}": 73})
    conditions = {"is_player_playing $player_char": True,
                  "not has_deatharrest_been_executed": True,
                  "not is_player_in_any_car $player_char": True}

    class Actions(list):
        def append(self, line):
            super().append(line)
            if line == "wait 0":
                assert state["$onmission"] == 1
                assert "set_player_coordinates $player_char at 1.0 2.0 3.0" in self
                assert "set_player_control $player_char can_move True" not in self
                if died_during_hold:
                    conditions["is_player_playing $player_char"] = False
                    conditions["not has_deatharrest_been_executed"] = False

    actions = Actions()
    run_lines(["gosub @AP_RETURN", "terminate_this_script",
               *return_lines({4: ("1.0", "2.0", "3.0", "4.0")},
                             dispatch.ACTIVE_SLOT, dispatch.ACTIVE_MISSION, force=True)],
              state, conditions=conditions, executed=actions)
    assert actions.count("wait 0") == 2
    assert state["$onmission"] == 0
    assert "set_player_control $player_char can_move True" in actions
    assert ("do_fade 1 500" in actions) == (not died_during_hold)
