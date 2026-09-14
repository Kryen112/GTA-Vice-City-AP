"""Execute emitted integer gates, mission selection and activity checks."""

import ast
import importlib.util
import itertools
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
specification = importlib.util.spec_from_file_location(
    "mission_order", ROOT / "apworld/gta_vice_city/mission_order.py")
mission_order = importlib.util.module_from_spec(specification)
specification.loader.exec_module(mission_order)


def run_lines(lines, values):
    labels = {line[1:]: index for index, line in enumerate(lines) if line.startswith(":")}
    position = 0
    condition = True
    started = []

    def value(token):
        return values[token] if token.startswith("$") else int(token)

    while position < len(lines):
        line = lines[position]
        position += 1
        tokens = line.split()
        if line.startswith("goto ") or (line.startswith("goto_if_false ") and not condition):
            position = labels[tokens[-1][1:]]
        elif line.startswith("start_new_script "):
            started.append(tokens[-1][1:])
        elif line.startswith("set_var_int_to_var_int "):
            values[tokens[1]] = value(tokens[3])
        elif line.startswith("div_int_var_by_int_var "):
            values[tokens[1]] //= value(tokens[3])
        elif line.startswith("  $"):
            left, operator, right = tokens
            condition = {">": value(left) > value(right), ">=": value(left) >= value(right),
                         "==": value(left) == value(right)}[operator]
        elif line.startswith("$"):
            left, operator, right = tokens
            operand = value(right)
            if operator == "=":
                values[left] = operand
            elif operator == "+=":
                values[left] += operand
            elif operator == "-=":
                values[left] -= operand
            elif operator == "*=":
                values[left] *= operand
            elif operator == "/=":
                values[left] //= operand
            else:
                raise AssertionError(line)
    return started


def test_taxi_watcher_checks_each_configured_fare_milestone():
    source = ROOT / "mod/scm/build_scm.py"
    tree = ast.parse(source.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {"taxi_milestone_lines", "add_stat_watcher"}]
    bodies = []
    scope = {"TAXI_MILESTONE_SPACING": 10169, "TAXI_MILESTONE_COUNT": 10170, "TAXI_EXTRA_COMPLETION_BASE": 9550,
             "insert_before": lambda anchor, body, reason: bodies.append(body),
             "insert_after": lambda *arguments: None}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), scope)
    scope["add_stat_watcher"]()
    # Run the final CLEO output, after the marker pass removes APSTAT from MAIN.
    marker_source = ROOT / "mod/scm/add_markers.py"
    marker_tree = ast.parse(marker_source.read_text())
    remove = next(node for node in marker_tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "remove_thread")
    scope.update(re=re, lines=[*bodies[0], "", ":GEN1"])
    exec(compile(ast.Module(body=[remove], type_ignores=[]), str(marker_source), "exec"), scope)
    scope["stat_body"] = scope["remove_thread"]("APSTAT")
    assert scope["lines"] == ["", ":GEN1"]
    start = next(index for index, node in enumerate(marker_tree.body)
                 if isinstance(node, ast.Assign) and any(
                     isinstance(target, ast.Name) and target.id == "cleo" for target in node.targets))
    end = next(index for index, node in enumerate(marker_tree.body[start:], start)
               if isinstance(node, ast.AugAssign) and isinstance(node.value, ast.List)
               and any(isinstance(value, ast.Constant) and value.value == "goto @AW_LOOP"
                       for value in node.value.elts))
    exec(compile(ast.Module(body=marker_tree.body[start:end + 1], type_ignores=[]),
                 str(marker_source), "exec"), scope)
    # One polling iteration; omit the final loop jump and trailing blank line.
    lines = scope["cleo"][:-2]
    for spacing in (0, 1, 5, 10, 100):
        actual_spacing = spacing or 10
        for fares in range(102):
            values = defaultdict(int, {"$10169": spacing, "$369": fares})
            run_lines(lines, values)
            checked = [level for level in range(1, 101)
                       if values[f"${9308 + level if level <= 10 else 9550 + level - 11}"]]
            assert checked == list(range(1, min(fares // actual_spacing, 100) + 1))


def test_every_five_mission_order_selects_only_the_next_received_mission():
    source = ROOT / "mod/scm/add_markers.py"
    tree = ast.parse(source.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "strand_block")
    scope = {"mission_order": mission_order, "MAINLAND_ANY": "any mainland crossing",
             "MISSION_PASSED": "mission passed"}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), scope)
    missions = [{"ordinal": index, "launcher": f"GEN{index + 1}", "passed": f"$passed{index}",
                 "shown": 11000 + index, "started": 11010 + index, "handle": 11020 + index,
                 "gate": [(9011, index + 1)], "sprite": 1, "coords": [0, 0, 0]}
                for index in range(5)]
    lines = scope["strand_block"]("Cortez", missions)
    for order in itertools.permutations(range(5)):
        encoded = sum((order.index(index) + 1) * 10 ** index for index in range(5))
        for completed in range(5):
            for received in (completed, completed + 1, 5):
                values = defaultdict(int, {"$9037": encoded, "$9011": received})
                values.update({f"$passed{index}": 1 for index in order[:completed]})
                expected = [f"GEN{order[completed] + 1}"] if received > completed else []
                assert run_lines(lines, values) == expected
    for completed in range(5):
        values = defaultdict(int, {"$9011": 5})
        values.update({f"$passed{index}": 1 for index in range(completed)})
        assert run_lines(lines, values) == [f"GEN{completed + 1}"]
