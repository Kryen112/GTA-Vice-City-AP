"""Seed-configured dispatch over the audited mission scene adapters."""

import re

from mission_dispatch import ACTIVE_MISSION, ACTIVE_SLOT, SLOT_BASE
from mission_layout import ASSIGNMENT_BASE, BUILD_VERSION, BUILD_VERSION_GLOBAL, EVENT_TIMING_GLOBAL, FULL_MODE_GLOBAL
from mission_returns import EXTERIOR_RESET, PHONE_RETURN_POSITION, return_lines


def configure_runtime_dispatch(lines, source, managed, points, titles, travel_open, travel_close):
    """Replace fixed test choices with validated seed globals and shared slot commits."""
    configure_launcher_gates(lines, source, managed)
    numbers = sorted(points)
    # Full seeds stamp the validated mapping together with their mode flag.
    for number in numbers:
        launch = f"${ACTIVE_MISSION} = {number}"
        hits = [i for i, line in enumerate(lines) if line == launch]
        # APFIN uses an independent ending request, handled below.
        for index in reversed(hits):
            lines[index:index + 1] = seed_launch_lines(number, points[number], f"{number}_{index}")
        label = f"AP_RETURN_PAYLOAD_{number}"
        start = lines.index(f":{label}")
        end = lines.index(f":AP_TRAVEL_BEGIN_{number}", start)
        body = return_lines({number: tuple(f"${PHONE_RETURN_POSITION + i}" for i in range(4))},
                            ACTIVE_MISSION, ACTIVE_MISSION, force=True)
        body = [line.replace("AP_RETURN", label) for line in body]
        body[1:1] = ["if ", f"  ${FULL_MODE_GLOBAL} == 1", f"goto_if_false @{label}_DONE"]
        lines[start:end] = body
        for direction in ("BEGIN", "END"):
            start = lines.index(f":AP_TRAVEL_{direction}_{number}")
            end = lines.index("return", start)
            lines[end:end] = [f":AP_TRAVEL_{direction}_{number}_DONE"]
            lines[start + 1:start + 1] = ["if ", f"  ${FULL_MODE_GLOBAL} == 1",
                                          f"goto_if_false @AP_TRAVEL_{direction}_{number}_DONE"]

    # The fragment goal requests the original ending, independently of slot assignments.
    start = lines.index(":APFIN")
    launch = next(i for i in range(start, len(lines)) if lines[i].startswith(f"${ACTIVE_SLOT} = "))
    end = lines.index("gosub @AP_DISPATCH", launch) + 1
    lines[launch:end] = [
        (f"get_player_coordinates $player_char position_to ${PHONE_RETURN_POSITION} "
         f"${PHONE_RETURN_POSITION + 1} ${PHONE_RETURN_POSITION + 2}"),
        f"get_player_heading ${PHONE_RETURN_POSITION + 3} = player $player_char",
        f"${ACTIVE_SLOT} = 0", f"${ACTIVE_MISSION} = 52", "$10359 = 0", "gosub @AP_DISPATCH"]

    # Commit the accepted slot, never the payload's original slot.
    for index, line in enumerate(lines):
        if re.fullmatch(rf"\$({ '|'.join(str(SLOT_BASE+n) for n in numbers) }) = 1", line):
            lines[index] = "gosub @AP_COMMIT_SLOT"
    # Share the exterior reset across every mission return to fit MAIN's buffer.
    for index in range(len(lines) - len(EXTERIOR_RESET), -1, -1):
        if lines[index:index + len(EXTERIOR_RESET)] == EXTERIOR_RESET:
            lines[index:index + len(EXTERIOR_RESET)] = ["gosub @AP_RETURN_EXTERIOR"]
    commit = [":AP_RETURN_EXTERIOR", *EXTERIOR_RESET, "return", ":AP_COMMIT_SLOT"]
    for number in numbers:
        commit += ["if ", f"  ${ACTIVE_SLOT} == {number}", f"goto_if_false @AP_COMMIT_NEXT_{number}",
                   f"${SLOT_BASE + number} = 1", "return", f":AP_COMMIT_NEXT_{number}"]
    commit += ["return"]
    at = lines.index(":AP_DISPATCH")
    lines[at:at] = commit
    # Default modes retain payload-based effects. Full mode chooses its policy.
    at = lines.index(":AP_DISPATCH_FINISH")
    trigger = 10569
    event_start = next(i for i in range(at, len(lines)) if lines[i] == f"  ${ACTIVE_SLOT} == 31")
    event_end = lines.index(":AP_DISPATCH_CLEAR", event_start)
    for i in range(event_start, event_end):
        lines[i] = lines[i].replace(f"${ACTIVE_SLOT}", f"${trigger}")
    lines[event_start - 1:event_start - 1] = [
        f"set_var_int_to_var_int ${trigger} = ${ACTIVE_MISSION}", "if and",
        f"  ${FULL_MODE_GLOBAL} == 1", f"  ${EVENT_TIMING_GLOBAL} == 0",
        "goto_if_false @AP_EVENT_TRIGGER_READY", f"set_var_int_to_var_int ${trigger} = ${ACTIVE_SLOT}",
        ":AP_EVENT_TRIGGER_READY"]
    # Titles belong to the launched payload in every shuffle mode.
    header = next(i for i, line in enumerate(lines) if line.startswith("//-------------Mission "))
    for number in numbers:
        title = titles[number]
        for index in reversed([i for i in range(header) if lines[i] == title]):
            lines[index:index + 1] = []
        start = next(i for i, line in enumerate(lines) if line == f"//-------------Mission {number}---------------")
        entry = next(i for i in range(start, len(lines)) if lines[i].startswith("script_name "))
        lines[entry + 1:entry + 1] = [title]
        header = next(i for i, line in enumerate(lines) if line.startswith("//-------------Mission "))
    # Reserve the contract and scratch words; stamp only the immutable build identity.
    at = lines.index("script_name 'HOT'") + 1
    lines[at:at] = [f"${trigger} = 0", f"${BUILD_VERSION_GLOBAL} = {BUILD_VERSION}"]


def compact_rank_reads(lines):
    """Share repeated rank arithmetic while preserving each caller's default rank."""
    import mission_order

    scratch = 10570
    changes = []
    counts = set()
    for index, line in enumerate(lines):
        match = re.fullmatch(r"\$10166 = ([1-9])", line)
        if not match or index + 3 >= len(lines):
            continue
        count = int(match.group(1))
        order = re.fullmatch(r"  \$(\d+) > 0", lines[index + 2])
        jump = re.fullmatch(r"goto_if_false @(\w+)", lines[index + 3])
        if not order or not jump:
            continue
        unlock = int(order.group(1)) - mission_order.ORDER_BASE + mission_order.UNLOCK_FIRST
        expected = mission_order.rank_lines(unlock, count, jump.group(1))
        if lines[index:index + len(expected)] != expected:
            continue
        changes.append((index, len(expected), [f"$10166 = {count}",
                        f"set_var_int_to_var_int ${scratch} = ${order.group(1)}",
                        f"gosub @AP_SHARED_RANK_{count}"]))
        counts.add(count)
    for index, size, replacement in reversed(changes):
        lines[index:index + size] = replacement
    body = []
    for count in sorted(counts):
        body += [f":AP_SHARED_RANK_{count}", "if ", f"  ${scratch} > 0",
                 f"goto_if_false @AP_SHARED_RANK_{count}_DONE",
                 f"set_var_int_to_var_int $10166 = ${scratch}", f"$10166 /= {10 ** (count - 1)}",
                 "set_var_int_to_var_int $10167 = $10166", "$10167 /= 10", "$10167 *= 10",
                 "sub_int_var_from_int_var $10166 -= $10167", f":AP_SHARED_RANK_{count}_DONE", "return"]
    at = lines.index(":AP_DISPATCH")
    lines[at:at] = body


SLOT_PREREQUISITES = {
    "KEN1": (10, 15), "BAR5": (17,), "ROC3": (55,), "CUB4": (62,),
    "FIN2": (51,),
}


def slot_gate_lines(launcher, target):
    prerequisites = SLOT_PREREQUISITES.get(launcher, ())
    if not prerequisites:
        return []
    done = f"AP_SLOT_READY_{target}"
    return ["if ", f"  ${FULL_MODE_GLOBAL} == 1", f"goto_if_false @{done}",
            *[line for number in prerequisites for line in
              ("if ", f"  ${SLOT_BASE + number} == 1", f"goto_if_false @{target}")], f":{done}"]


def configure_launcher_gates(lines, source, managed):
    """Keep slot prerequisites separate from the assigned payload's scene."""
    import mission_order

    changes = []
    for marker in managed:
        launcher = marker["launcher"]
        start = lines.index(f":{launcher}")
        end = next(i for i in range(start + 2, len(lines)) if lines[i].startswith("script_name '"))
        if launcher == "FIN2":
            for index in range(start, end):
                if lines[index] == "  $passed_ASS1_Rub_Out == 1":
                    lines[index] = "  $10462 == 1"
        own_unlock = marker["gate"][0][0]
        # The native launcher loop's player check follows its AP entry gates.
        check = next(i for i in range(start, end) if lines[i].strip() == "is_player_playing $player_char")
        target = lines[check + 1].split("@", 1)[1]
        changes.append((check - 1, 0, slot_gate_lines(launcher, target)))
        launch = next(line for line in source[source.index(f":{launcher}"):]
                      if line.startswith("load_and_launch_mission_internal "))
        number = int(launch.split()[-1])
        for index in range(start, end):
            line = lines[index]
            if line in ("gosub @HELP_2883", "make_player_safe_for_cutscene $player_char"):
                label = "AP_INPUT_HELP" if line.startswith("gosub") else "AP_INPUT_DIRECT"
                changes.append((index, 1, [f"set_var_int_to_var_int $10571 = ${ASSIGNMENT_BASE + number}",
                                          f"gosub @{label}"]))
            match = re.fullmatch(r"\$10166 = ([1-9])", line)
            if not match or index + 3 >= end:
                continue
            order = re.fullmatch(r"  \$(\d+) > 0", lines[index + 2])
            jump = re.fullmatch(r"goto_if_false @(\w+)", lines[index + 3])
            if not order or not jump:
                continue
            unlock = int(order.group(1)) - mission_order.ORDER_BASE + mission_order.UNLOCK_FIRST
            if unlock == own_unlock:
                continue
            expected = mission_order.rank_lines(unlock, int(match.group(1)), jump.group(1))
            size = len(expected) + 3
            label = f"AP_ORIGINAL_REQUIREMENT_{launcher}_{index}"
            changes.append((index, size, ["if ", f"  ${FULL_MODE_GLOBAL} == 0", f"goto_if_false @{label}",
                                          *lines[index:index + size], f":{label}"]))
        # Extra payload travel requirements do not bind an accessible full-shuffle slot.
        for index in range(start, end - 6):
            if lines[index] == "if or" and lines[index + 1:index + 6] == [
                    f"  ${global_index} >= 1" for global_index in (9030, 9032, 9033, 9034, 9035)]:
                label = f"AP_ORIGINAL_TRAVEL_{launcher}_{index}"
                changes.append((index, 7, ["if ", f"  ${FULL_MODE_GLOBAL} == 0", f"goto_if_false @{label}",
                                           *lines[index:index + 7], f":{label}"]))
    for index, size, replacement in sorted(changes, reverse=True):
        lines[index:index + size] = replacement

    helpers = []
    for label, native in (("AP_INPUT_HELP", "gosub @HELP_2883"),
                          ("AP_INPUT_DIRECT", "make_player_safe_for_cutscene $player_char")):
        helpers += [f":{label}", "if and", f"  ${FULL_MODE_GLOBAL} == 1",
                    "  $10571 >= 67", "  74 >= $10571", f"goto_if_false @{label}_NATIVE",
                    "set_player_control $player_char can_move False", "return",
                    f":{label}_NATIVE", native, "return"]
    helpers += [":AP_PAYLOAD_READY", "$10572 = 1", "if and", f"  ${FULL_MODE_GLOBAL} == 1",
                "  $10571 == 51", "goto_if_false @AP_PAYLOAD_READY_DONE", "if ",
                "  $10575 >= 1", "goto_if_false @AP_PAYLOAD_BLOCKED",
                "return", ":AP_PAYLOAD_BLOCKED", "$10572 = 0", ":AP_PAYLOAD_READY_DONE", "return"]
    at = lines.index(":AP_DISPATCH")
    lines[at:at] = helpers


def payload_gate_lines(launcher, source, target):
    launch = next(line for line in source[source.index(f":{launcher}"):]
                  if line.startswith("load_and_launch_mission_internal "))
    number = int(launch.split()[-1])
    return [f"set_var_int_to_var_int $10571 = ${ASSIGNMENT_BASE + number}",
            "gosub @AP_PAYLOAD_READY", "if ", "  $10572 == 1", f"goto_if_false @{target}"]


def seed_launch_lines(number, point, label=None):
    """Select the payload without changing the source slot or its return point."""
    label = number if label is None else label
    result = [f"${ACTIVE_MISSION} = {number}", "if ", f"  ${FULL_MODE_GLOBAL} == 1",
              f"goto_if_false @AP_SEED_LAUNCH_{label}",
              f"set_var_int_to_var_int ${ACTIVE_MISSION} = ${ASSIGNMENT_BASE + number}",
              f":AP_SEED_LAUNCH_{label}"]
    if point != tuple(f"${PHONE_RETURN_POSITION + i}" for i in range(4)):
        result[:0] = [f"${PHONE_RETURN_POSITION + i} = {value}" for i, value in enumerate(point)]
    return result


def finale_asset_count_lines():
    """Count purchased, owned income assets without granting their world rewards."""
    from mission_layout import (
        FINALE_ASSETS_COUNT_GLOBAL,
        FINALE_ASSETS_READY_GLOBAL,
        FINALE_ASSETS_REQUIRED_GLOBAL,
        FINALE_MANDATORY_ASSETS_GLOBAL,
    )
    count = FINALE_ASSETS_COUNT_GLOBAL
    ready = FINALE_ASSETS_READY_GLOBAL
    completed = (9382, 9388, 9380, 612, 9385, 9376, 9387, 1096)
    groups = [(9358 + index, 9880 + index, flag) for index, flag in enumerate(completed)]
    groups.append((10462, 268))
    lines = [f"${count} = 0", f"${ready} = 0"]
    for index, group in enumerate(groups):
        for flag in group:
            lines += ["if ", f"  ${flag} >= 1", f"goto_if_false @AP_ASSET_NEXT_{index}"]
        lines += [f"${count} += 1", f":AP_ASSET_NEXT_{index}"]
    lines += ["if ", f"  is_int_var_greater_or_equal_to_int_var ${count} >= ${FINALE_ASSETS_REQUIRED_GLOBAL}",
              "goto_if_false @AP_ASSET_COUNT_DONE", "if ",
              f"  ${FINALE_MANDATORY_ASSETS_GLOBAL} == 1", "goto_if_false @AP_ASSET_COUNT_READY"]
    for required, group in enumerate((groups[0], groups[-1]), start=1):
        lines += ["if ", f"  ${FINALE_ASSETS_REQUIRED_GLOBAL} >= {required}",
                  "goto_if_false @AP_ASSET_COUNT_READY"]
        for flag in group:
            lines += ["if ", f"  ${flag} >= 1", "goto_if_false @AP_ASSET_COUNT_DONE"]
    lines += [":AP_ASSET_COUNT_READY", f"${ready} = 1", ":AP_ASSET_COUNT_DONE"]
    return lines


def prepare_cap_targets(lines):
    """Give collectors outdoor targets when no income business is available."""
    start = lines.index("script_name 'CAP_1'")
    end = next(index for index in range(start + 1, len(lines))
               if lines[index].startswith("//-------------Mission "))
    targets = (4917, 4918, 4920, 4921)
    blips = (4912, 4913, 4910, 4911)
    body = []
    for target in range(4916, 4922):
        body += ["if ", f"  ${target} == 2", "goto_if_false @AP_CAP_TARGETS_READY"]
    for target, blip in zip(targets, blips, strict=True):
        matches = [line for line in lines[start:end]
                   if line.startswith(f"add_short_range_sprite_blip_for_coord ${blip} =")]
        assert len(matches) == 1, f"Cap target blip {blip} is ambiguous"
        body += [f"${target} = 0", matches[0]]
    body += [":AP_CAP_TARGETS_READY"]
    changes = [(lines.index(":CAP_1_2342") + 1, 0, body)]
    income = {611: 612, 622: 623, 606: 607, 641: 642, 627: 628, 632: 633}
    for index in range(start, end):
        match = re.match(r"(?:remove_pickup|create_protection_pickup) \$(\d+)(?: |$)", lines[index])
        if match and int(match[1]) in income:
            flag = income[int(match[1])]
            label = f"AP_CAP_INCOME_{index}"
            changes.append((index, 1, ["if ", f"  ${flag} == 1", f"goto_if_false @{label}",
                                       lines[index], f":{label}"]))
    assert len(changes) == 25, f"Cap income pickup sites changed: {len(changes)}"
    for index, size, replacement in sorted(changes, reverse=True):
        lines[index:index + size] = replacement
