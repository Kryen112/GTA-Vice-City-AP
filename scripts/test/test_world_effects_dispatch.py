"""The compact test dispatcher commits slots and world events only after success."""

from collections import defaultdict

import pytest
from test_mission_dispatch import dispatch
from test_mission_order import run_lines


@pytest.mark.parametrize("timing", dispatch.WORLD_EVENT_TIMINGS)
def test_fixed_assignment_commit_failure_retry_and_event_timing(timing):
    state = defaultdict(int)
    routines = [*dispatch.dispatcher_lines([3, 7, 11, 16], business_timing=timing, world_effects=True),
                ":AP_OPEN_BUSINESSES", "start_new_script @BUSINESSES", "return",
                ":AP_MANSION_TRANSFER", "start_new_script @MANSION", "return",
                ":AP_YACHT_REMOVE", "start_new_script @DEPARTURE", "return"]

    def execute(body):
        return run_lines([*body, "terminate_this_script", *routines], state)

    for slot, payload in dispatch.WORLD_EFFECTS_SMOKE_ASSIGNMENT.items():
        execute(dispatch.launch_lines(slot, payload))
        assert execute(dispatch.finish_lines(payload, slot=slot)) == []
        assert state[f"${dispatch.SLOT_BASE + slot}"] == 0
        execute(dispatch.launch_lines(slot, payload))
        execute(dispatch.success_lines(payload))
        assert state[f"${dispatch.SLOT_BASE + slot}"] == 0
        actions = execute(dispatch.finish_lines(payload, slot=slot))
        identity = slot if timing == "quest_giver_progress" else payload
        assert actions == ({11: ["DEPARTURE"], 16: ["MANSION"]}.get(identity, []))
        assert state[f"${dispatch.SLOT_BASE + slot}"] == 1
        assert state[f"${dispatch.ACTIVE_SLOT}"] == state[f"${dispatch.ACTIVE_MISSION}"] == 0
        state = defaultdict(int, dict(state))
    assert state["$10462"] == state["$10464"] == 1


def test_suite_preserves_every_displaced_mission_and_rejects_duplicates():
    route = dispatch.WORLD_EFFECTS_SUITE_ROUTE
    assignment = dispatch.close_assignment(route)
    assert all(assignment[slot] == payload for slot, payload in route.items())
    assert set(assignment) == set(assignment.values())
    assert len(set(assignment.values())) == len(assignment)
    assert {11, 16, 24, 30, 31, 33, 35, 51, 52, 74} <= set(route.values())
    assert {7, 13, 19, 20, 26, 29, 59, 71} <= set(route.values())
    with pytest.raises(AssertionError, match="duplicate"):
        dispatch.close_assignment({3: 31, 4: 31})


@pytest.mark.parametrize("success", [0, 1])
def test_mission_local_return_runs_before_finish_clears_the_active_slot(success):
    point = ("110.6", "-824.2", "9.6", "327.9")
    state = defaultdict(int, {f"${dispatch.ACTIVE_SLOT}": 18, f"${dispatch.ACTIVE_MISSION}": 26,
                             f"${dispatch.RETURN_PENDING}": 1, f"${dispatch.SUCCESS}": success})
    actions = []
    conditions = {"is_player_playing $player_char": True, "not has_deatharrest_been_executed": True,
                  "not is_player_in_any_car $player_char": True}
    body = ["gosub @AP_RETURN", *dispatch.finish_lines(26, slot=18), "terminate_this_script",
            *dispatch.return_lines({18: point}, dispatch.ACTIVE_SLOT, dispatch.ACTIVE_MISSION),
            *dispatch.dispatcher_lines([18, 26], world_effects=True, mission_local_returns=True)]
    run_lines(body, state, conditions=conditions, executed=actions)
    assert "set_player_coordinates $player_char at 110.6 -824.2 9.6" in actions
    assert state[f"${dispatch.SLOT_BASE + 18}"] == success
    assert state[f"${dispatch.ACTIVE_SLOT}"] == state[f"${dispatch.RETURN_PENDING}"] == 0


def test_job_failure_hook_does_not_mark_the_shared_gameplay_exit():
    source = [":BANKJO4_23867", "warp_player_from_car_to_coord $player_char at 1.0 2.0 3.0",
              ":BANKJO4_23951", "set_player_coordinates $player_char at 1.0 2.0 3.0",
              ":GAMEPLAY", "gosub @BANKJO4_24234", ":BANKJO4_22302", "gosub @BANKJO4_24234",
              ":BANKJO4_24234", "set_player_coordinates $player_char at 4.0 5.0 6.0"]
    assert dispatch.ending_relocations(source, {24: (0, len(source))}, 24) == [1, 3, 7]


def test_boomshine_return_tracks_the_occupied_car_at_the_ending_only():
    source = [":INTRO", "set_car_coordinates $4342 at -1183.0 -664.2 10.5",
              ":PHIL2_5606", "set_car_coordinates $4342 at -1183.0 -664.2 10.5"]
    assert dispatch.ending_relocations(source, {26: (0, len(source))}, 26) == [3]
