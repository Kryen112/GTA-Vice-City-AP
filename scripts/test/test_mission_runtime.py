"""Execute production seed dispatch and shared rank arithmetic."""

import itertools
import sys
from collections import defaultdict
from pathlib import Path

from test_mission_dispatch import dispatch
from test_mission_order import mission_order, run_lines

sys.path.append(str(Path(__file__).resolve().parents[2] / "apworld/gta_vice_city"))
from mission_layout import ASSIGNMENT_BASE, FULL_MODE_GLOBAL
from mission_runtime import compact_rank_reads, seed_launch_lines, slot_gate_lines


def test_seed_dispatch_and_phone_return_position_survive():
    for full in (0, 1):
        values = defaultdict(int, {f"${FULL_MODE_GLOBAL}": full, f"${ASSIGNMENT_BASE + 3}": 73,
                                   f"${dispatch.ACTIVE_SLOT}": 3, "$10353": 123})
        body = seed_launch_lines(3, tuple(f"${10353 + i}" for i in range(4)))
        started = run_lines([*body, f"load_and_launch_mission_internal ${dispatch.ACTIVE_MISSION}",
                             "terminate_this_script"], values)
        assert started == [73 if full else 3]
        assert values[f"${dispatch.ACTIVE_SLOT}"] == 3
        assert values["$10353"] == 123


def test_shared_rank_arithmetic_matches_inline_for_every_order():
    for permutation in itertools.permutations(range(1, 6)):
        encoded = sum(rank * 10 ** index for index, rank in enumerate(permutation))
        for order in (0, encoded):
            body = []
            for count in range(1, 6):
                body += [*mission_order.rank_lines(9011, count, f"RANK_{count}"),
                         f"set_var_int_to_var_int ${11000 + count} = $10166"]
            body += ["terminate_this_script", ":AP_DISPATCH", "return"]
            original = defaultdict(int, {"$9037": order})
            compacted = original.copy()
            run_lines(body, original)
            compact_rank_reads(body)
            run_lines(body, compacted)
            assert [original[f"${11000 + count}"] for count in range(1, 6)] == [
                compacted[f"${11000 + count}"] for count in range(1, 6)]


def test_death_row_waits_for_both_source_slots_only_in_full_mode():
    for full, cortez, diaz in itertools.product((0, 1), repeat=3):
        values = defaultdict(int, {f"${FULL_MODE_GLOBAL}": full, "$10370": cortez, "$10375": diaz})
        body = [*slot_gate_lines("KEN1", "BLOCKED"), "start_new_script @KEN1",
                ":BLOCKED", "terminate_this_script"]
        assert run_lines(body, values) == (["KEN1"] if not full or (cortez and diaz) else [])

def test_watcher_output_cannot_overwrite_pickup_script(tmp_path):
    import subprocess

    output = tmp_path / "appickup.txt"
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[2] / "mod/scm/add_markers.py"),
                             str(tmp_path / "missing-source.txt"), str(tmp_path / "main.txt"), str(output)],
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "general watcher (apwatchers.txt)" in result.stderr
    assert not output.exists()


def test_finale_asset_count_requires_purchase_ownership_and_completion():
    from mission_layout import FINALE_ASSETS_COUNT_GLOBAL, FINALE_ASSETS_READY_GLOBAL, FINALE_ASSETS_REQUIRED_GLOBAL
    from mission_runtime import finale_asset_count_lines
    body = finale_asset_count_lines()
    groups = [(9358 + index, 9880 + index, flag)
              for index, flag in enumerate((9382, 9388, 9380, 612, 9385, 9376, 9387, 1096))]
    groups.append((10462, 268))
    for required in range(10):
        for total in range(10):
            values = defaultdict(int, {f"${FINALE_ASSETS_REQUIRED_GLOBAL}": required})
            for group in groups[:total]:
                values.update({f"${flag}": 1 for flag in group})
            run_lines(body, values)
            assert values[f"${FINALE_ASSETS_COUNT_GLOBAL}"] == total
            assert values[f"${FINALE_ASSETS_READY_GLOBAL}"] == (total >= required)
    for group in groups:
        for missing in group:
            values = defaultdict(int, {f"${flag}": 1 for flags in groups for flag in flags})
            values[f"${missing}"] = 0
            run_lines(body, values)
            assert values[f"${FINALE_ASSETS_COUNT_GLOBAL}"] == 8


def test_cap_fallback_targets_do_not_grant_income():
    from mission_runtime import prepare_cap_targets
    income = {611: 612, 622: 623, 606: 607, 641: 642, 627: 628, 632: 633}
    lines = ["script_name 'CAP_1'"]
    lines += [f"add_short_range_sprite_blip_for_coord ${blip} = test" for blip in (4912, 4913, 4910, 4911)]
    lines += [":CAP_1_2342", "terminate_this_script"]
    for handle in income:
        lines += [f"remove_pickup ${handle}", f"create_protection_pickup ${handle} = test"] * 2
    lines += ["//-------------Mission 52---------------"]
    prepare_cap_targets(lines)
    start = lines.index(":CAP_1_2342") + 1
    stop = lines.index("terminate_this_script")
    for existing in (False, True):
        values = defaultdict(int, {f"${flag}": 2 for flag in range(4916, 4922)})
        if existing:
            values["$4916"] = 0
        run_lines(lines[start:stop], values)
        assert [flag for flag in range(4916, 4922) if values[f"${flag}"] == 0] == (
            [4916] if existing else [4917, 4918, 4920, 4921])
    for owned in (0, 1):
        values = defaultdict(int, {f"${flag}": owned for flag in income.values()})
        executed = []
        run_lines(lines[stop + 1:-1], values, executed=executed)
        pickups = [line for line in executed if line.startswith(("remove_pickup", "create_protection_pickup"))]
        assert len(pickups) == (24 if owned else 0)
        assert all(values[f"${flag}"] == owned for flag in income.values())


def test_mandatory_assets_use_the_first_two_places_only():
    from mission_runtime import finale_asset_count_lines
    body = finale_asset_count_lines()
    groups = [(9358 + index, 9880 + index, flag)
              for index, flag in enumerate((9382, 9388, 9380, 612, 9385, 9376, 9387, 1096))]
    groups.append((10462, 268))
    for required, mandatory, printworks, estate, others in itertools.product(
            range(10), (0, 1), (0, 1), (0, 1), (0, 1, 7)):
        values = defaultdict(int, {"$10573": required, "$10576": mandatory})
        for group in groups[1:1 + others]:
            values.update({f"${flag}": 1 for flag in group})
        values.update({f"${flag}": printworks for flag in groups[0]})
        values.update({f"${flag}": estate for flag in groups[-1]})
        run_lines(body, values)
        expected = (others + printworks + estate >= required
                    and (not mandatory or required == 0 or printworks)
                    and (not mandatory or required < 2 or estate))
        assert values["$10575"] == bool(expected), (required, mandatory, printworks, estate, others)
