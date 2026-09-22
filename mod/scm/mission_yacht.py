"""Keep mission yacht scenes independent of Cortez's permanent departure."""

import re

YACHT_DEPARTED = 10464
# Zero is absent, two is construction interrupted at a wait, one is complete.
YACHT_PRESENT = 10465
YACHT_MISSIONS = (3, 7, 8, 9, 10, 11)


def yacht_event_lines(trigger_global: int) -> list[str]:
    return ["if ", f"  ${trigger_global} == 11", "goto_if_false @AP_YACHT_EVENT_DONE",
            f"${YACHT_DEPARTED} = 1", "gosub @AP_YACHT_REMOVE", ":AP_YACHT_EVENT_DONE"]


def yacht_changes(source: list[str]) -> tuple[list[tuple[int, int, list[str]]], list[str]]:
    """Extract the boot scene and restore it before mission cleanup releases control."""
    def unique(text):
        matches = [index for index, line in enumerate(source) if line == text]
        assert len(matches) == 1, f"yacht: expected one {text!r}"
        return matches[0]

    start = unique("initialise_object_path $722 = scripted_path_file 0 width 90.0")
    end = unique("load_and_launch_mission_internal 1")
    assert start < end < unique(":GEN1"), "yacht: boot scene ownership"
    body = source[start:end]
    models = [match.group(1) for line in body if
              (match := re.search(r"init_object (#\w+)", line))]
    assert len(models) == len(set(models)) == 7, "yacht: expected seven boot objects"
    assert sum(line == "wait 0" for line in body) == 2, "yacht: path initialization waits"
    assert not any(re.search(r"\b\d+@", line) or line.startswith((":", "goto", "gosub"))
                   for line in body), "yacht: unsafe boot scene"
    # Path processing supplies the object's real dock position before the gangplank.
    plank = next(index for index, line in enumerate(body) if "init_object #YACHT_CHUNK_KB" in line)
    body = [body[0], f"${YACHT_PRESENT} = 2", *body[1:plank],
            "$448, $449, $450 = get_object_coordinates $714", *body[plank:]]
    changes = [(start, end - start, ["gosub @AP_YACHT_CREATE"])]
    headers = [(int(match.group(1)), index) for index, line in enumerate(source)
               if (match := re.fullmatch(r"//-------------Mission (\d+)---------------", line))]
    spans = {number: (index, headers[position + 1][1] if position + 1 < len(headers) else len(source))
             for position, (number, index) in enumerate(headers)}
    for number in YACHT_MISSIONS:
        first, last = spans[number]
        enter = [index for index in range(first, last) if source[index] == "$onmission = 1"]
        leave = [index for index in range(first, last) if source[index] == "$onmission = 0"]
        assert len(enter) == len(leave) == 1, f"yacht: mission {number} lifecycle"
        changes += [(enter[0] + 1, 0, ["gosub @AP_YACHT_CREATE"]),
                    (leave[0], 0, ["gosub @AP_YACHT_RESTORE"])]
    # All Hands removes three dock objects during departure and the tender at the ending.
    for anchor in (":COL_5_1765", ":COL_5_27542"):
        unique(anchor)
    ending = unique(":COL_5_27542")
    clear = unique("clear_object_path $722")
    assert source[clear - 8:clear] == [f"delete_object ${number}" for number in range(714, 722)]
    assert ending < clear < unique(":COL_5_27598"), "yacht: success deletion ownership"
    changes.append((clear - 8, 9, ["gosub @AP_YACHT_REMOVE"]))
    # Cleared handles cannot delete an unrelated object if the engine reuses its slot.
    for index, line in enumerate(source):
        if line in {"delete_object $716", "delete_object $718", "delete_object $720", "delete_object $721"}:
            if not clear - 8 <= index <= clear:
                changes.append((index + 1, 0, [f"{line.split()[1]} = -1"]))
    routines = [":AP_YACHT_CREATE", "if ", f"  ${YACHT_PRESENT} == 1",
                "goto_if_false @AP_YACHT_BUILD", "return", ":AP_YACHT_BUILD",
                "gosub @AP_YACHT_REMOVE", *[f"${number} = -1" for number in range(714, 722)],
                *[f"request_model {model}" for model in models], "load_all_models_now",
                *body, f"${YACHT_PRESENT} = 1", "$716 = -1",
                *[f"mark_model_as_no_longer_needed {model}" for model in models], "return",
                ":AP_YACHT_RESTORE", "if ", f"  ${YACHT_DEPARTED} == 0",
                "goto_if_false @AP_YACHT_REMOVE", "gosub @AP_YACHT_CREATE", "return",
                ":AP_YACHT_REMOVE", "if ", f"  ${YACHT_PRESENT} > 0",
                "goto_if_false @AP_YACHT_REMOVED"]
    for number in range(714, 722):
        routines += ["if ", f"  does_object_exist ${number}",
                     f"goto_if_false @AP_YACHT_OBJECT_{number}", f"delete_object ${number}",
                     f":AP_YACHT_OBJECT_{number}", f"${number} = -1"]
    routines += ["clear_object_path $722", f"${YACHT_PRESENT} = 0",
                 *[f"mark_model_as_no_longer_needed {model}" for model in models],
                 ":AP_YACHT_REMOVED", "return"]
    return changes, routines
