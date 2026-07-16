"""Dump each mission's suppressed cash reward from a clean VC decompile.

The reward mirror in the apworld pays out, as filler, the cash each mission
would have paid in vanilla. That is the same amount build_scm.py strips on a
mission pass: the `add_score $player_char money += N` line near the mission's
passed-flag assignment (with its `M_PASS $N` banner). This scanner reuses the
same detection so the mirrored amounts match what the mod suppresses, and prints
them for transcription into data.MISSION_REWARDS.

The decompile is the player's own, generated locally and never committed, so run
this against the clean.txt produced for the SCM build. Read-only.

Usage:
    python scripts/dump_mission_rewards.py path/to/clean.txt
"""

from __future__ import annotations

import re
import sys

# The scan window and patterns mirror build_scm.py's reward suppression: for each
# passed-flag assignment, look ahead up to eighteen lines for the cash add and
# the on-screen banner.
SCAN_AHEAD = 18
PASSED_FLAG = re.compile(r"^\$(passed_\S+) = 1$")
CASH_ADD = re.compile(r"^add_score \$player_char money \+= (\d+)$")
PASS_BANNER = re.compile(r"^print_with_number_big 'M_PASS' number (\d+) ")


def main(source_path: str) -> int:
    with open(source_path, "rb") as handle:
        raw = handle.read()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    lines = raw.decode("latin-1").split(newline)

    found = 0
    for index, line in enumerate(lines):
        flag_match = PASSED_FLAG.match(line)
        if flag_match is None:
            continue
        cash: int | None = None
        banner: int | None = None
        for ahead in range(index + 1, min(index + 1 + SCAN_AHEAD, len(lines))):
            cash_match = CASH_ADD.match(lines[ahead])
            if cash_match is not None:
                cash = int(cash_match.group(1))
            banner_match = PASS_BANNER.match(lines[ahead])
            if banner_match is not None:
                banner = int(banner_match.group(1))
        amount = cash if cash is not None else 0
        mismatch = "" if banner in (None, amount) else f"  (banner ${banner})"
        print(f"{flag_match.group(1)}\t${amount}{mismatch}")
        found += 1

    print(f"# {found} mission passed-flags scanned", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
