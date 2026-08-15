"""Dump each mission's suppressed cash reward from a clean VC decompile.

The reward mirror in the apworld pays out, as filler, the cash each mission
would have paid in vanilla. That is the same amount build_scm.py strips or
gates on a mission pass. This scanner reuses the same detection so the
mirrored amounts match what the mod suppresses: within each mission block
(the decompile's Mission N headers), every `M_PASS $N` banner names a pass
reward, and the matching-amount `add_score` lines are its cash, wherever the
pass block scatters them.

The decompile is the player's own, generated locally and never committed, so
run this against the clean.txt produced for the SCM build. Read-only.

Usage:
    python scripts/dump_mission_rewards.py path/to/clean.txt
"""

from __future__ import annotations

import re
import sys

MISSION_HEADER = re.compile(r"^//-------------Mission (\d+)---------------$")
MISSION_TITLE = re.compile(r"^// Originally: (.+?)\s*$")
PASS_BANNER = re.compile(r"^print_with_number_big 'M_PASS' number (\d+) time \d+ style 1$")
CASH_ADD = re.compile(r"^add_score \$player_char money \+= (\d+)$")


def main(source_path: str) -> int:
    with open(source_path, "rb") as handle:
        raw = handle.read()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    lines = raw.decode("latin-1").split(newline)

    headers = [(int(MISSION_HEADER.match(line).group(1)), index)
               for index, line in enumerate(lines) if MISSION_HEADER.match(line)]
    for position, (number, start) in enumerate(headers):
        end = headers[position + 1][1] if position + 1 < len(headers) else len(lines)
        title_match = MISSION_TITLE.match(lines[start + 1]) if start + 1 < end else None
        title = title_match.group(1) if title_match else f"Mission {number}"
        banner_amounts = [PASS_BANNER.match(line).group(1)
                          for line in lines[start:end] if PASS_BANNER.match(line)]
        cash_amounts = [CASH_ADD.match(line).group(1)
                        for line in lines[start:end]
                        if CASH_ADD.match(line) and CASH_ADD.match(line).group(1) in banner_amounts]
        amount = sum(int(value) for value in cash_amounts)
        detail = ""
        if sorted(banner_amounts) != sorted(cash_amounts):
            detail = f"  (banners {banner_amounts}, cash {cash_amounts})"
        print(f"{number}\t{title}\t${amount}{detail}")

    print(f"# {len(headers)} mission blocks scanned", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
