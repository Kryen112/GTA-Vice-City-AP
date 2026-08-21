"""Proves the finale warp's build guards refuse a decompile they cannot account for.

The SCM layer has no test in `scripts/run_tests.py` and cannot have one: its
input is the player's own decompile, which is Rockstar-derived and never lives in
the repo. What stands in for a test is the set of assertions `build_scm.py` makes
while it inserts the hunt-goal finale warp, and those assertions are only worth
anything if they actually fire. This mutates a real decompile four ways, each
breaking one assumption the warp rests on, and fails unless every mutant is
refused by a finale warp guard rather than by something else.

    python scripts/check_finale_warp_guards.py <decompile.txt> [work_dir]

The decompile is a Sanny `--decompile` of a vanilla 1.0 `main.scm`. The work
directory holds the mutants and their build output and defaults to a temporary
directory; nothing is written next to the decompile.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD_SCM = REPOSITORY_ROOT / "mod" / "scm" / "build_scm.py"


def anchors(lines: list[str]) -> dict[str, int]:
    """The lines the warp is anchored on, found the way build_scm finds them."""
    start = next(index for index, line in enumerate(lines)
                 if line.startswith("//-------------Mission 52"))
    end = next(index for index, line in enumerate(lines)
               if line.startswith("//-------------Mission 53"))
    cutscene = next(index for index in range(start, end)
                    if lines[index].rstrip("\r") == "load_cutscene 'FINALE'")
    entry = max(index for index in range(start, cutscene)
                if lines[index].startswith("make_player_safe_for_cutscene "))
    branch = next(index for index in range(start, entry)
                  if lines[index].startswith("load_special_character "))
    # A handle released at one site only, so dropping that line really does take
    # it out of the set the transform accounts for.
    single_site_release = next(index for index in range(entry, end)
                               if lines[index].startswith("remove_pickup $4980"))
    known_release = next(index for index in range(entry, end)
                         if lines[index].startswith("remove_blip $4982"))
    return {"branch": branch, "single_site_release": single_site_release,
            "known_release": known_release}


def carriage(line: str) -> str:
    return "\r" if line.endswith("\r") else ""


def mutants(lines: list[str], at: dict[str, int]) -> dict[str, list[str]]:
    """One mutant per assumption, named for the guard that must refuse it."""
    cases: dict[str, list[str]] = {}

    unknown_verb = list(lines)
    unknown_verb[at["known_release"]] = "delete_car $4982" + carriage(lines[at["known_release"]])
    cases["unknown_verb"] = unknown_verb

    handle_count = list(lines)
    handle_count[at["single_site_release"]] = "wait 0" + carriage(lines[at["single_site_release"]])
    cases["handle_count"] = handle_count

    nested_branch = list(lines)
    nested_branch.insert(at["branch"], "gosub @HELP_2883" + carriage(lines[at["branch"]]))
    cases["nested_branch"] = nested_branch

    renamed_condition = [line.replace("can_player_start_mission", "can_player_begin_mission")
                         for line in lines]
    cases["renamed_condition"] = renamed_condition

    return cases


def refused_for_the_finale(work: pathlib.Path, name: str, lines: list[str]) -> str | None:
    """Builds one mutant. Returns a complaint, or None when the guard bit."""
    source = work / f"mutant_{name}.txt"
    source.write_text("\n".join(lines), encoding="latin-1")
    completed = subprocess.run(
        [sys.executable, str(BUILD_SCM), str(source), str(work / f"out_{name}.txt")],
        capture_output=True, text=True, check=False,
    )
    if completed.returncode == 0:
        return f"{name}: the build SUCCEEDED, so the guard did not bite"
    message = (completed.stderr or "").strip().splitlines()
    if "finale" not in " ".join(message):
        reason = next((line for line in reversed(message) if "Error" in line), "")
        return f"{name}: refused for another reason: {reason[:200]}"
    reason = next((line for line in reversed(message) if "finale" in line), "")
    print(f"  {name}: refused, {reason[:140]}")
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    decompile = pathlib.Path(sys.argv[1])
    if decompile.is_dir():
        decompile = decompile / "clean.txt"
    if not decompile.is_file():
        print(f"No decompile at {decompile}. Produce one with Sanny --decompile first.")
        return 1
    lines = decompile.read_text(encoding="latin-1").split("\n")
    at = anchors(lines)

    with tempfile.TemporaryDirectory() as temporary:
        work = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path(temporary)
        work.mkdir(parents=True, exist_ok=True)
        complaints = [complaint for name, mutant in mutants(lines, at).items()
                      if (complaint := refused_for_the_finale(work, name, mutant)) is not None]

    if complaints:
        print("\nA finale warp guard failed to bite:")
        for complaint in complaints:
            print(f"  {complaint}")
        return 1
    print("\nEvery mutation was refused by a finale warp guard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
