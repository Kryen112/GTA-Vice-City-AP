"""Every jump in a compiled CLEO script must point inside itself.

    python scripts/check_cleo_jumps.py <compiled.cs> [...]

A CLEO script addresses its own labels with NEGATIVE offsets, so a non-negative
operand on a jump means the label was not local to the file. That is what a
relocated thread looks like when part of it stayed behind, and it is the one
mistake nothing else catches: Sanny resolves a name it cannot see to offset zero
and still exits zero, with no diagnostic. A thread whose gosub lands on zero
either leaves for another script entirely or recurses until the interpreter's
gosub stack overflows, so the failure is a crash or a dead gate rather than a
build error.

add_markers.py already refuses to carry a thread that references a label it
left, which catches this at the source level. This is the same question asked of
the bytes, after the compile.

Exits non-zero if any jump leaves its script.
"""

from __future__ import annotations

import pathlib
import struct
import sys

# The jump opcodes that take an immediate int32 operand.
JUMPS = {0x0002: "goto", 0x004D: "goto_if_false", 0x0050: "gosub",
         0x004F: "start_new_script"}
IMMEDIATE_INT32 = 0x01


def non_local_jumps(payload: bytes) -> tuple[int, list[tuple[int, str, int]]]:
    """Every jump in the script, and the ones that leave it."""
    found: list[tuple[int, str, int]] = []
    total = 0
    for offset in range(len(payload) - 7):
        opcode = struct.unpack_from("<H", payload, offset)[0]
        if opcode not in JUMPS or payload[offset + 2] != IMMEDIATE_INT32:
            continue
        target = struct.unpack_from("<i", payload, offset + 3)[0]
        total += 1
        if target >= 0:
            found.append((offset, JUMPS[opcode], target))
    return total, found


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    problems = 0
    for name in sys.argv[1:]:
        path = pathlib.Path(name)
        total, found = non_local_jumps(path.read_bytes())
        verdict = "ok" if not found else f"{len(found)} LEAVE THE SCRIPT"
        print(f"{path.name:18} {total:4} jumps  {verdict}")
        for offset, kind, target in found:
            print(f"    at {offset}: {kind} -> {target}")
        problems += len(found)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
