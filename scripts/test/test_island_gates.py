"""Verify island permission gates preserve vanilla entry and cleanup paths."""

import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "mod/scm/island_gates.py"
specification = importlib.util.spec_from_file_location("island_gates", SOURCE)
gates = importlib.util.module_from_spec(specification)
specification.loader.exec_module(gates)


def permits(conditions, mask):
    comparisons = {"==": lambda left, right: left == right, "<>": lambda left, right: left != right,
                   ">=": lambda left, right: left >= right}
    return all(comparisons[operator](mask, int(operand))
               for _global, operator, operand in (line.split() for line in conditions))


@pytest.mark.parametrize("mask,mainland,starfish", [(0, False, False), (1, True, False),
                                                  (2, False, True), (3, True, True)])
def test_fixed_content_uses_independent_resolved_island_permissions(mask, mainland, starfish):
    assert permits(gates.district_conditions("Little Haiti"), mask) == mainland
    assert permits(gates.district_conditions("Starfish Island"), mask) == starfish
    assert permits(gates.district_conditions("Prawn Island"), mask)


def interaction_source():
    lines = [":LAW1", "script_name 'LAW1'", ":LAW1_LOOP", "wait 0", "if ", "  $onmission == 0",
             "goto_if_false @LAW1_LOOP", "load_and_launch_mission_internal 3", "goto @LAW1_LOOP",
             ":AMBULA", "script_name 'AMBULA'", ":AMBULA_LOOP", "wait 0", "if and",
             "  $onmission == 0", "  $319 == 0", "goto_if_false @AMBULA_LOOP",
             "load_and_launch_mission_internal 76", "goto @AMBULA_LOOP",
             ":APFIN", "script_name 'APFIN'", "if ", "  $onmission == 0", "goto_if_false @APFIN",
             "load_and_launch_mission_internal 52", "goto @APFIN",
             ":PSAVE2", "script_name 'PSAVE2'", "if ", "  $onmission == 0", "goto_if_false @PSAVE2",
             "activate_save_menu", "goto @PSAVE2"]
    for thread in sorted(gates.SHOP_THREADS):
        lines += [f":{thread}", f"script_name '{thread}'", "if ",
                  "  locate_stopped_player_on_foot_3d $player_char stopped 1 1.0 2.0 3.0 radius 1.0 1.0 2.0",
                  f"goto_if_false @{thread}_CLEANUP", "gosub @ENTER_SHOP", f":{thread}_CLEANUP",
                  "gosub @CLEANUP", f"goto @{thread}"]
    for number in range(1, 5):
        thread = f"IMPORT{number}"
        lines += [f":{thread}", f"script_name '{thread}'", "wait 500", "if ",
                  "  is_player_playing $player_char", f"goto_if_false @{thread}",
                  "gosub @IMPGEN4_183", f"goto @{thread}"]
    return [*lines, "//-------------Mission 3---------------", ":PAYLOAD", "script_name 'LAWYER1'",
            "if ", "  $onmission == 0", "goto_if_false @PAYLOAD", "terminate_this_script"]


def test_entry_gates_cover_launchers_shops_imports_and_saves_without_touching_payloads():
    lines = interaction_source()
    original = lines.copy()
    counts = gates.gate_interaction_entries(lines)
    assert counts == {"launchers": 2, "shops": 6, "imports": 4, "saves": 1}
    assert lines[lines.index(":PAYLOAD"):] == original[original.index(":PAYLOAD"):]
    assert lines[lines.index(":APFIN"):lines.index(":PSAVE2")] == original[
        original.index(":APFIN"):original.index(":PSAVE2")]
    for thread in ("LAW1", "AMBULA", "PSAVE2"):
        start = lines.index(f"script_name '{thread}'")
        guard = lines.index("  is_int_var_greater_than_int_var $10174 > $onmission", start)
        assert lines[guard - 1] == ("if and" if thread == "AMBULA" else "if ")
    for thread in gates.SHOP_THREADS:
        start = lines.index(f"script_name '{thread}'")
        assert lines[start + 1:start + 3] == ["if and", "  $10174 == 1"]
        assert f"goto_if_false @{thread}_CLEANUP" in lines
    for number in range(1, 5):
        start = lines.index(f"script_name 'IMPORT{number}'")
        assert lines[start + 3:start + 5] == gates.district_conditions("Little Havana")


@pytest.mark.parametrize("invalid", ["or", "missing_shop", "already_gated"])
def test_unsupported_entry_shapes_fail_without_partial_changes(invalid):
    lines = interaction_source()
    if invalid == "or":
        lines[lines.index("if ")] = "if or"
    elif invalid == "missing_shop":
        lines.remove("script_name 'AMMU1'")
    else:
        gates.gate_interaction_entries(lines)
    original = lines.copy()
    with pytest.raises(AssertionError):
        gates.gate_interaction_entries(lines)
    assert lines == original


@pytest.mark.parametrize("permission,onmission", [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_single_opcode_entry_guard_requires_permission_and_idle(permission, onmission):
    assert (permission > onmission) == bool(permission and not onmission)


def test_remote_markers_use_their_giver_island_instead_of_the_player_island():
    assert gates.marker_gate_lines("HAT1", "HIDE") == [
        "if or", "  $10173 == 1", "  $10173 == 3", "goto_if_false @HIDE"]
    assert gates.marker_gate_lines("BAR1", "HIDE") == ["if ", "  $10173 >= 2", "goto_if_false @HIDE"]
    assert gates.marker_gate_lines("LAW1", "HIDE") == []
    assert gates.marker_gate_lines("PORN1", "HIDE") == []


def emergency_source():
    lines = []
    for number, (thread, checks) in enumerate((("COK2", 1), ("TAXI", 0), ("AMBULAN", 1),
                                               ("FIRETRU", 2), ("COPCAR", 2), ("PIZZA", 0))):
        lines += [f"//-------------Mission {number}---------------", f"script_name '{thread}'"]
        for check in range(checks):
            lines += ["if ", "  $passed_COK2_Phnom_Penh_86 == 0",
                      f"goto_if_false @{thread}_SPAWN_{check}", "wait 0", f":{thread}_SPAWN_{check}"]
        lines += ["terminate_this_script "]
    return lines


@pytest.mark.parametrize("mainland_open,mission_passed", [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_emergency_spawns_follow_ap_mainland_access_independently_of_story(mainland_open, mission_passed):
    lines = emergency_source()
    original = lines.copy()
    gates.redirect_emergency_mainland_checks(lines)
    changed = [index for index, line in enumerate(lines) if line != original[index]]
    assert len(changed) == 5
    values = {"$847": mainland_open, "$passed_COK2_Phnom_Penh_86": mission_passed}
    for index in changed:
        variable, comparison, expected = lines[index].split()
        assert comparison == "=="
        assert (values[variable] == int(expected)) == (not mainland_open)
    # only the five emergency guards change. story checks, Taxi and Pizza stay intact.
    assert lines.count("  $passed_COK2_Phnom_Penh_86 == 0") == 1
    for index in changed:
        lines[index] = original[index]
    assert lines == original


@pytest.mark.parametrize("change", ["missing", "extra", "already_redirected"])
def test_emergency_spawn_guard_drift_fails_before_mutation(change):
    lines = emergency_source()
    index = lines.index("script_name 'COPCAR'") + 2
    if change == "missing":
        del lines[index]
    elif change == "extra":
        lines.insert(index, lines[index])
    else:
        gates.redirect_emergency_mainland_checks(lines)
    original = lines.copy()
    with pytest.raises(AssertionError, match="emergency mainland"):
        gates.redirect_emergency_mainland_checks(lines)
    assert lines == original
