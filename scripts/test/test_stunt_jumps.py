"""Completed jumps skip the camera; failed attempts remain retryable."""

import ast
from pathlib import Path


def test_stunt_takeoffs_require_unfinished_jump():
    source = Path(__file__).resolve().parents[2] / "mod/scm/build_scm.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    gate = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "gate_stunt_jumps")
    ids = [*range(1, 37), 25, 26]
    lines = []
    for identifier in ids:
        lines += ["if ", "  locate_player_in_car_3d $player_char 0 1.0 2.0 3.0 radius 1.0 1.0 1.0",
                  f"goto_if_false @USJ_NEXT_{identifier}", f"$792 = {identifier}"]
    scope = {"lines": lines, "edits": [], "STUNT_JUMPS_CLASS": 2,
             "STUNT_JUMP_DISTRICTS": [0] * 36,
             "_hold_condition": lambda *_: "  $9999 >= 1",
             "district_conditions": lambda *_: [],
             "re": __import__("re")}
    exec(compile(ast.Module(body=[gate], type_ignores=[]), str(source), "exec"), scope)
    scope["gate_stunt_jumps"]()
    for index, line in enumerate(lines):
        if not line.startswith("$792 = "):
            continue
        identifier = int(line.split(" = ")[1])
        assert lines[index - 6:index - 2] == [
            "if and", "  $9999 >= 1", f"  ${794 + identifier} == 0",
            f"  ${9236 + identifier} == 0",
        ]
        conditions = lines[index - 5:index - 2]
        for unlocked, vanilla_done, ap_done in [(1, 0, 0), (0, 0, 0), (1, 1, 0), (1, 0, 1)]:
            values = {9999: unlocked, 794 + identifier: vanilla_done, 9236 + identifier: ap_done}
            allowed = []
            for condition in conditions:
                global_id, operator, number = condition.split()
                value = values[int(global_id[1:])]
                allowed.append(value >= int(number) if operator == ">=" else value == int(number))
            assert all(allowed) == bool(unlocked and not vanilla_done and not ap_done)
