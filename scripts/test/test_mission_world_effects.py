"""World-effect extraction preserves actions and refuses unsafe source changes."""

import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "mod/scm/mission_world_effects.py"
specification = importlib.util.spec_from_file_location("mission_world_effects", SOURCE)
effects = importlib.util.module_from_spec(specification)
specification.loader.exec_module(effects)


def source_lines():
    # Synthetic instructions only; the actual game body is extracted locally.
    body = []
    for index, thread in enumerate(effects.BUSINESS_BUY_THREADS):
        pickup = "$Print_Works_asset" if index == 0 else f"$asset{index}"
        body += [f"remove_pickup {pickup}",
                 f"add_short_range_sprite_blip_for_contact_point $blip{index} = marker",
                 f"change_blip_display $blip{index} display 2",
                 f"create_forsale_property_pickup {pickup} = available",
                 f"start_new_script @{thread} "]
    return ["goto @MAIN_LOOP", "", ":GEN1", "terminate_this_script ",
            "script_name 'PROTEC1'", *body, "return ", "script_name 'PROTEC2'"]


def test_extraction_preserves_the_exact_business_actions_and_original_call_site():
    lines = source_lines()
    original = lines.copy()
    actions = original[5:-2]
    effects.extract_shakedown_business_opening(lines)
    entry = lines.index(f":{effects.BUSINESS_OPEN_LABEL}")
    assert lines[entry + 1:entry + 1 + len(actions)] == actions
    assert lines[entry + 1 + len(actions)] == "return "
    assert entry < lines.index(":GEN1")
    mission = lines.index("script_name 'PROTEC1'")
    assert lines[mission + 1:mission + 3] == [f"gosub @{effects.BUSINESS_OPEN_LABEL}", "return "]
    # Inline the sole call and remove its routine: the entire input is restored.
    restored = lines.copy()
    restored[mission + 1:mission + 2] = actions
    del restored[entry:entry + len(actions) + 3]
    assert restored == original


@pytest.mark.parametrize("change", ["duplicate", "missing", "wait", "local", "branch",
                                    "thread", "fallthrough", "owner", "already_extracted"])
def test_unsafe_source_is_rejected_without_mutation(change):
    lines = source_lines()
    if change == "duplicate":
        lines.append("remove_pickup $Print_Works_asset")
    elif change == "missing":
        lines.remove("start_new_script @STRPBUY ")
    elif change in {"wait", "local", "branch"}:
        lines.insert(6, {"wait": "wait 0", "local": "remove_pickup 0@",
                         "branch": "goto @OTHER"}[change])
    elif change == "thread":
        lines[lines.index("start_new_script @CARBUY ")] = "start_new_script @WRONG "
    elif change == "fallthrough":
        lines[0] = "$test = 0"
    elif change == "owner":
        lines.remove("script_name 'PROTEC1'")
        lines.append("script_name 'PROTEC1'")
    else:
        effects.extract_shakedown_business_opening(lines)
    original = lines.copy()
    with pytest.raises(AssertionError, match="business opening"):
        effects.extract_shakedown_business_opening(lines)
    assert lines == original
