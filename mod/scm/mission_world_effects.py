"""Extract world effects from the player decomp"""

import re

BUSINESS_OPEN_LABEL = "AP_OPEN_BUSINESSES"
BUSINESS_SALES_APPLIED = 10461
WORLD_EVENT_TIMINGS = ("quest_giver_progress", "mission_completion")
BUSINESS_BUY_THREADS = (
    "COUBUY", "CARBUY", "PORNBUY", "ICEBUY", "TAXIBUY", "BANKBUY", "BOATBUY", "STRPBUY",
)


def business_event_lines(trigger_global: int) -> list[str]:
    """Apply the sale event once after its successful dispatch finishes cleanup."""
    done = "AP_BUSINESS_EVENT_DONE"
    return ["if ", f"  ${trigger_global} == 31", f"goto_if_false @{done}",
            "if ", f"  ${BUSINESS_SALES_APPLIED} == 0", f"goto_if_false @{done}",
            f"gosub @{BUSINESS_OPEN_LABEL}", f"${BUSINESS_SALES_APPLIED} = 1", f":{done}"]


def shakedown_event_changes(source: list[str], timing: str) -> list[tuple[int, int, list[str]]]:
    """Detach only business availability."""
    assert timing in WORLD_EVENT_TIMINGS, "unknown world event timing"
    calls = [index for index, line in enumerate(source) if line == f"gosub @{BUSINESS_OPEN_LABEL}"]
    assert len(calls) == 1, "business event: expected one original opening call"
    mission = source.index("script_name 'PROTEC1'")
    next_mission = source.index("script_name 'PROTEC2'")
    assert source.index(f":{BUSINESS_OPEN_LABEL}") < mission < calls[0] < next_mission, (
        "business event: unexpected call ownership")
    restoration = source.index(":PROTEC1_6843")
    assert calls[0] < restoration < next_mission, "business event: missing success restoration"
    assert source[restoration + 1] == "set_car_density_multiplier 1.0", (
        "business event: unexpected success restoration")
    # The giver policy skips the sale showcase, whose text claims sales opened.
    replacement = ["goto @PROTEC1_6843"] if timing == "quest_giver_progress" else []
    return [(calls[0], 1, replacement)]


def extract_shakedown_business_opening(lines: list[str]) -> None:
    """Move Shakedown's grants into MAIN, so it can be called by any script."""
    def unique(anchor: str) -> int:
        hits = [index for index, line in enumerate(lines) if line.rstrip() == anchor]
        assert len(hits) == 1, f"business opening: {anchor!r} matched {len(hits)}, expected one"
        return hits[0]

    start = unique("remove_pickup $Print_Works_asset")
    end = unique("start_new_script @STRPBUY") + 1
    main = unique(":GEN1")
    mission = unique("script_name 'PROTEC1'")
    next_mission = unique("script_name 'PROTEC2'")
    assert main < mission < start < end < next_mission, "business opening: unexpected script ownership"
    assert not any(BUSINESS_OPEN_LABEL in line for line in lines), "business opening: already extracted"
    previous = next(line.strip() for line in reversed(lines[:main]) if line.strip())
    assert previous.startswith(("goto @", "return", "terminate_this_script")), (
        "business opening: MAIN insertion would allow fallthrough")

    body = lines[start:end]
    allowed = {
        "remove_pickup", "add_short_range_sprite_blip_for_contact_point",
        "change_blip_display", "create_forsale_property_pickup", "start_new_script",
    }
    assert all(line.split() and line.split()[0] in allowed for line in body), (
        "business opening: expected straight-line grants without waits or control flow")
    assert not any(re.search(r"\b\d+@", line) for line in body), (
        "business opening: local variables cannot move to a shared routine")
    starts = [line.split()[1] for line in body if line.startswith("start_new_script ")]
    assert starts == [f"@{thread}" for thread in BUSINESS_BUY_THREADS], (
        "business opening: expected the eight business purchase threads")
    for opcode in allowed - {"start_new_script"}:
        assert sum(line.startswith(f"{opcode} ") for line in body) == 8, (
            f"business opening: expected eight {opcode} instructions")

    # Both slices are validated before mutation. Replace the later slice first.
    lines[start:end] = [f"gosub @{BUSINESS_OPEN_LABEL}"]
    lines[main:main] = [f":{BUSINESS_OPEN_LABEL}", *body, "return ", ""]
