"""Audited ending relocations and source-derived outdoor giver return points."""

import re

RETURN_PENDING = 10460
PHONE_RETURN_POSITION = 10353

# Labels identify ending scenes or cleanup, not intro and gameplay teleports.
# Empty entries explicitly describe missions that finish without relocating.
ENDING_RELOCATIONS = {
    3: (), 4: (), 5: (), 6: (), 7: (), 10: (), 18: (), 31: (),
    8: (("COL2_9775", "set_player_coordinates"),),
    9: (("GENERL3_23795", "set_player_coordinates"),),
    11: (("COL_5_27353", "warp_player_into_car"),
         ("COL_5_27476", "warp_player_from_car_to_coord"),
         ("COL_5_30415", "set_player_coordinates"),
         ("COL_5_30789", "warp_player_from_car_to_coord")),
    13: (("BARON2_13817", "set_player_coordinates"),),
    14: (("BARON3_7446", "warp_player_from_car_to_coord"),
         ("BARON3_7544", "set_player_coordinates")),
    15: (("BARON4_9536", "set_player_coordinates"),),
    16: (("BARON5_12204", "set_player_coordinates"), ("BARON5_12454", "set_player_coordinates")),
    24: (("BANKJO4_23867", "warp_player_from_car_to_coord"),
         ("BANKJO4_23951", "set_player_coordinates"),
         ("BANKJO4_22302", "gosub @BANKJO4_24234")),
    26: (("PHIL2_5606", "set_car_coordinates $4342 at -1183.0 -664.2 10.5"),),
    12: (), 17: (), 19: (), 20: (), 25: (), 32: (), 53: (), 54: (), 55: (),
    59: (), 63: (), 64: (), 71: (),
    29: (("PORNO3_9317", "set_player_coordinates"), ("PORNO3_9782", "set_player_coordinates")),
    30: (("PORNO4_11196", "set_player_coordinates"),),
    33: (("PROTEC3_11131", "set_player_coordinates"),),
    34: (("COUNT1_6427", "set_player_coordinates"),),
    35: (("COUNT2_19197", "set_player_coordinates"),),
    52: (("FIN_1_26913", "set_player_coordinates"),),
    51: (), 74: (), 83: (), 96: (),
    56: (("CUBAN1_9893", "warp_player_from_car_to_coord"),),
    58: (("CUBAN3_10982", "set_player_coordinates"),),
    60: (("HAIT1_5407", "set_player_coordinates"),),
    65: (("ROCKB3_9010", "set_player_coordinates"), ("ROCKB3_9336", "set_player_coordinates")),
}


def ending_relocations(source: list[str], spans: dict[int, tuple[int, int]], number: int) -> list[int]:
    assert number in ENDING_RELOCATIONS, f"mission {number}: ending relocations need an audit"
    start, end = spans[number]
    result = []
    for label, opcode in ENDING_RELOCATIONS[number]:
        labels = [index for index in range(start, end) if source[index] == f":{label}"]
        assert len(labels) == 1, f"mission {number}: missing or ambiguous ending {label}"
        block_end = next((index for index in range(labels[0] + 1, end)
                          if source[index].startswith(":")), end)
        matches = [index for index in range(labels[0] + 1, block_end)
                   if (source[index] == opcode if opcode.startswith(("gosub @", "set_car_coordinates "))
                       else source[index].startswith(f"{opcode} $player_char "))]
        assert len(matches) == 1, f"mission {number}: ambiguous relocation in {label}"
        result.append(matches[0])
    return result


def giver_return_point(source: list[str], span: tuple[int, int], launcher: str) -> tuple[str, ...]:
    """Use the native taxi arrival or the captured position at a payphone launch."""
    points = [line.split()[1:] for line in source[span[0]:span[1]]
              if line.startswith("set_shortcut_dropoff_point_for_mission ")]
    if not points and launcher.startswith("ASSIN_"):
        return tuple(f"${PHONE_RETURN_POSITION + index}" for index in range(4))
    assert len(points) == 1 and len(points[0]) == 4, f"{launcher}: no unique vanilla return point"
    point = tuple(points[0])
    position = tuple(float(value) for value in point[:3])
    start = source.index(f":{launcher}")
    end = next(index for index in range(start + 2, span[0]) if source[index].startswith("script_name '"))
    triggers = [match.groups() for line in source[start:end]
                if (match := re.fullmatch(
                    r"  locate_player_\w+_3d \$player_char \S+ (\S+) (\S+) (\S+) radius (\S+) (\S+) (\S+)", line))]
    assert triggers, f"{launcher}: no entry trigger to validate the return point"

    def scalar(token: str) -> float:
        if not token.startswith("$"):
            return float(token)
        values = {float(line.split(" = ")[1]) for line in source
                  if re.fullmatch(re.escape(token) + r" = -?\d+(?:\.\d+)?", line)}
        assert len(values) == 1, f"{launcher}: trigger coordinate {token} is not constant"
        return values.pop()

    for trigger in triggers:
        centre, radius = trigger[:3], trigger[3:]
        assert any(abs(position[axis] - scalar(centre[axis])) > scalar(radius[axis]) for axis in range(2)), (
            f"{launcher}: vanilla return point overlaps the mission trigger")
    return point


# Vanilla SHIT_16363 clears these interior occupancy flags on death/arrest.
# A custom exterior return bypasses those door/death transitions.
EXTERIOR_RESET = ["clear_extra_colours 0", "set_area_visible 0",
                  *[f"${flag} = 0" for flag in (989, 986, 1002, 1003, 1088, 987, 988, 990, 991)]]


def return_lines(points: dict[int, tuple[str, ...]], active_slot: int, active_mission: int,
                 *, force: bool = False) -> list[str]:
    """Return after relocation or temporary travel, holding entry gates during resync."""
    done = "AP_RETURN_DONE"
    result = [":AP_RETURN"]
    if not force:
        result += ["if ", f"  ${RETURN_PENDING} == 1", f"goto_if_false @{done}",
                   "if ", f"  is_int_var_equal_to_int_var ${active_slot} == ${active_mission}",
                   "goto_if_false @AP_RETURN_SHUFFLED", f"goto @{done}", ":AP_RETURN_SHUFFLED"]
    result += ["if ", "  is_player_playing $player_char", f"goto_if_false @{done}",
               "if ", "  not has_deatharrest_been_executed", f"goto_if_false @{done}"]
    for slot, (x, y, z, heading) in points.items():
        result += ["if ", f"  ${active_slot} == {slot}", f"goto_if_false @AP_RETURN_NEXT_{slot}",
                   "$onmission = 1", "set_player_control $player_char can_move False", "do_fade 0 0",
                   *EXTERIOR_RESET, f"request_collision {x} {y}",
                   f"load_scene {x} {y} {z}", f"clear_area 1 at {x} {y} {z} range 1.0",
                   "if ", "  not is_player_in_any_car $player_char", f"goto_if_false @AP_RETURN_CAR_{slot}",
                   f"set_player_coordinates $player_char at {x} {y} {z}", f"goto @AP_RETURN_CAMERA_{slot}",
                   f":AP_RETURN_CAR_{slot}", f"warp_player_from_car_to_coord $player_char at {x} {y} {z}",
                   f":AP_RETURN_CAMERA_{slot}", f"set_player_heading $player_char z_angle_to {heading}",
                   "set_camera_behind_player", "restore_camera_jumpcut",
                   # Custom movement reloads its position across disabled-control updates.
                   "wait 0", "wait 0",
                   "set_player_control $player_char can_move True", "$onmission = 0",
                   "if ", "  is_player_playing $player_char", f"goto_if_false @{done}",
                   "if ", "  not has_deatharrest_been_executed", f"goto_if_false @{done}",
                   "do_fade 1 500",
                   f"goto @{done}", f":AP_RETURN_NEXT_{slot}"]
    return [*result, f":{done}", "return"]

