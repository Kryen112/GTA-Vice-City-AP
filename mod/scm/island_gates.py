"""SCM entry gates using the island permissions."""

import re

ISLAND_CONTENT_LOCKS = 10172
ISLAND_ACCESS_MASK = 10173
PLAYER_ISLAND_ALLOWED = 10174

MAINLAND_DISTRICTS = {"Downtown", "Little Haiti", "Little Havana", "Viceport", "Escobar International", "Junk Yard"}
MAINLAND_LAUNCHERS = {
    "PHI1", "PHI2", "BIK1", "BIK2", "BIK3", "CUB1", "CUB2", "CUB3", "CUB4",
    "HAT1", "HAT2", "HAT3", "ROC1", "ROC2", "ROC3", "COU1", "COU2",
    "TWAR1", "TWAR2", "TWAR3", "ASSIN_4", "ASSIN_5", "FIN1",
}
STARFISH_LAUNCHERS = {"BAR1", "BAR2", "BAR3", "BAR4", "BAR5", "PRO1", "PRO2", "PRO3", "FIN2"}
SHOP_THREADS = {"AMMU1", "AMMU2", "AMMU3", "HARD1", "HARD2", "HARD3"}


def district_conditions(district: str) -> list[str]:
    """Conditions to append to an AND block; disabled locks resolve to mask 3."""
    if district in MAINLAND_DISTRICTS:
        return [f"  ${ISLAND_ACCESS_MASK} >= 1", f"  ${ISLAND_ACCESS_MASK} <> 2"]
    if district == "Starfish Island":
        return [f"  ${ISLAND_ACCESS_MASK} >= 2"]
    return []


def marker_gate_lines(launcher: str, failure: str) -> list[str]:
    if launcher in MAINLAND_LAUNCHERS:
        return ["if or", f"  ${ISLAND_ACCESS_MASK} == 1", f"  ${ISLAND_ACCESS_MASK} == 3",
                f"goto_if_false @{failure}"]
    if launcher in STARFISH_LAUNCHERS:
        return ["if ", f"  ${ISLAND_ACCESS_MASK} >= 2", f"goto_if_false @{failure}"]
    return []


def gate_interaction_entries(lines: list[str]) -> dict[str, int]:
    """Gate free-roam entries without changing active mission payloads or cleanup."""
    end = next(index for index, line in enumerate(lines) if line.startswith("//-------------Mission "))
    starts = [(index, match.group(1)) for index, line in enumerate(lines[:end])
              if (match := re.fullmatch(r"script_name '(\w+)'", line))]
    edits = []
    counts = {"launchers": 0, "shops": 0, "imports": 0, "saves": 0}

    def extend_condition(index: int, conditions: list[str]) -> None:
        header = index - 1
        while lines[header].startswith("  "):
            header -= 1
        assert lines[header] in ("if ", "if", "if and"), f"island gate: unsupported condition at {index}"
        branch = next(position for position in range(index + 1, end)
                      if not lines[position].startswith("  "))
        assert lines[branch].startswith("goto_if_false @"), f"island gate: missing branch at {index}"
        assert branch - header - 1 + len(conditions) <= 8, "island gate exceeds the SCM condition limit"
        assert all(condition not in lines[header:branch] for condition in conditions), "island gate already installed"
        edits.extend([(header, 1, ["if and"]), (index, 0, conditions)])

    for order, (start, thread) in enumerate(starts):
        stop = starts[order + 1][0] if order + 1 < len(starts) else end
        body = lines[start:stop]
        launcher = any(line.startswith("load_and_launch_mission_internal ") for line in body)
        save = re.fullmatch(r"P?SAVE\d+", thread) is not None
        if (launcher and thread not in {"MAIN", "APFIN"}) or save:
            guards = [index for index in range(start, stop) if lines[index] == "  $onmission == 0"]
            assert guards, f"island gate: {thread} has no free-roam entry guard"
            for index in guards:
                assert lines[index - 1] in ("if ", "if", "if and"), f"island gate: {thread} has an unsupported entry"
                # Permission is 0 or 1 and onmission is 0 or 1: greater means
                # permission granted AND no mission running (in one opcode).
                edits.append((index, 1, [f"  is_int_var_greater_than_int_var ${PLAYER_ISLAND_ALLOWED} > $onmission"]))
            counts["saves" if save else "launchers"] += len(guards)
        if thread in SHOP_THREADS:
            entries = [index for index in range(start, stop)
                       if lines[index].startswith("  locate_stopped_player_on_foot_3d $player_char ")]
            assert len(entries) == 1, f"island gate: {thread} has an ambiguous shop counter"
            extend_condition(entries[0], [f"  ${PLAYER_ISLAND_ALLOWED} == 1"])
            counts["shops"] += 1
        if re.fullmatch(r"IMPORT[1-4]", thread):
            entry = next(index for index in range(start, stop) if lines[index] == "  is_player_playing $player_char")
            extend_condition(entry, district_conditions("Little Havana"))
            counts["imports"] += 1
    assert counts["shops"] == 6 and counts["imports"] == 4, "island gate: missing shops or import lists"
    for index, removed, replacement in sorted(edits, reverse=True):
        lines[index:index + removed] = replacement
    return counts
