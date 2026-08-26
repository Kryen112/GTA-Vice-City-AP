"""Checks the hand-written mirrors of the reserved global layout.

scm.py derives the whole block: each base is the one below it plus its size, so
adding a location moves everything above the completion block at once. The
main.scm builder, the marker pass and the ASI cannot import scm.py, so each holds
the numbers by hand. Nothing compared them until this script, which is how a
shift stayed silent: the world moved, the mirrors did not, and the failure lands
in game as the ASI writing over live marker handles rather than as a test.

Mirrors are read by regex rather than by import, since add_markers.py opens the
main.scm source at import time and build_scm.py builds.

Coverage is the named constants, the compiled CLEO scripts, and two tables whose
globals are written as bare literals inside them. It is NOT every literal in the
two mod scripts: both also spell completion globals out one per launcher, and a
literal that fails to move lands inside the completion block, which is a range
those files legitimately use, so no range check can tell it apart. Those are
covered by the world tests pinning the bases instead. What is checked here is
every mirror whose drift a range or a band CAN see.

    python scripts/check_scm_mirrors.py
"""

from __future__ import annotations

import pathlib
import re
import struct
import sys
import types

from ap_env import archipelago_root, link_world

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent

# The compiled CLEO scripts this script judges, and the number of bare-literal
# sites _literal_table_problems checks. The success line reports both, so they
# are declared once here rather than written down again in the message, where
# they went stale the moment a site was added.
CLEO_SCRIPTS = ("aprewd.cs", "apradio.cs", "apwatchers.cs", "aparea.cs",
                "appickup.cs")

# The bare-literal sites, by the name each is reported under. The success line
# counts these and _literal_table_problems asserts it visited exactly them, so a
# site added to one and not the other cannot go unreported the way a hand
# declared number could.
LITERAL_SITES = ("PACKAGE_REWARD_APPLY", "booleans", "add_reward_applier",
                 "venue gates")


def _constants(path: pathlib.Path, pattern: str) -> dict[str, int]:
    """Every `name = 1234` or `name = 1234;` the pattern names, by name."""
    text = path.read_text(encoding="utf-8")
    found: dict[str, int] = {}
    for match in re.finditer(pattern, text, re.MULTILINE):
        found[match.group("name")] = int(match.group("value"))
    # One pair is written on a single line, so the single-name pattern misses it.
    # A mirror this script cannot see is reported as unchecked rather than passed,
    # so the paired form is read here instead of being left to that report.
    for match in re.finditer(
            r"^(?P<first>[A-Z_]+), (?P<second>[A-Z_]+) = (?P<one>\d+), (?P<two>\d+)$",
            text, re.MULTILINE):
        found[match.group("first")] = int(match.group("one"))
        found[match.group("second")] = int(match.group("two"))
    return found


def _decode_reserved(raw: bytes) -> set[int]:
    """Every reserved global a compiled script's bytes name. See the caller."""
    found: set[int] = set()
    for position in range(len(raw) - 2):
        if raw[position] != 0x02:
            continue
        offset = struct.unpack_from("<H", raw, position + 1)[0]
        if offset % 4:
            continue
        index = offset // 4
        if index >= 9000:
            found.add(index)
    return found


def _reserved_references(path: pathlib.Path) -> set[int]:
    """Every reserved global a compiled CLEO script reads or writes.

    In a compiled script a global variable parameter is the byte 0x02 followed by
    a little endian two byte offset into script space, which is the index times
    four. Scanning for that pattern reads more than the real parameters, since any
    two bytes can look like one. An extra index inside the expected band changes
    nothing, but one outside it reads as a stale artefact when it may be a byte
    pair that only looks like a parameter, so the failure says both.
    """
    return _decode_reserved(path.read_bytes())


def _enum_terminator(source: str, opening: str, terminator: str) -> int | None:
    """The value of an enum's trailing count member, or None if it is absent.

    kContentCount and kAbilityCount size the blocks the district and ability
    globals are addressed with, but they are written as the last member of an
    enum rather than as a constant, so the constant scan cannot see them. An
    unreadable mirror reported as nothing checked is the failure this script
    exists to avoid, so they are counted here instead.
    """
    start = source.find(opening)
    if start < 0:
        return None
    end = source.find("}", start)
    if end < 0:
        return None
    members = []
    for line in source[start + len(opening):end].splitlines():
        body = line.strip().rstrip(",")
        if not body or body.startswith("//"):
            continue
        name, _, assigned = (part.strip() for part in body.partition("="))
        # Counting positions is only the value while the members run from zero
        # with no explicit value of their own. One member set explicitly would
        # make the count silently wrong, so it is reported as unreadable instead,
        # which the caller turns into "nothing was checked" rather than a pass.
        if assigned and not (not members and assigned == "0"):
            return None
        members.append(name)
    if terminator not in members:
        return None
    return members.index(terminator)


def _table_globals(source: str, opening: str) -> list[int] | None:
    """The reserved globals inside one bracketed table, or None if it is absent.

    Line based, so the table ends at the first line whose closing bracket sits at
    the opening line's own indentation.
    """
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if opening not in line:
            continue
        indent = len(line) - len(line.lstrip())
        found: list[int] = []
        for following in lines[index:]:
            stripped = following.strip()
            found += [int(value) for value
                      in re.findall(r'\((\d{4}), "', following)]
            if stripped == "]" and len(following) - len(following.lstrip()) == indent:
                break
        return found
    return None


def _function_body(source: str, signature: str) -> str | None:
    """One function's text, from its signature to the next top level statement."""
    start = source.find(signature)
    if start < 0:
        return None
    lines = source[start:].splitlines()
    body = [lines[0]]
    for line in lines[1:]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return chr(10).join(body)


def _literal_table_problems(scm_dir: pathlib.Path,
                            scm: types.ModuleType) -> list[str]:
    """Checks the four sites that hold reserved globals as bare literals.

    None of them is a `NAME = 1234` the constant scan can see. Two tables pair a
    reward global with the vanilla flag or ability it drives, a third writes two
    more rewards straight into the applier body as strings, and the fourth
    carries a venue's ownership global as the third condition of its gate. All
    four had to be shifted by hand.
    """
    problems: list[str] = []
    visited: list[str] = []
    reward_top = scm.REWARD_BASE + len(scm.REWARD_KEYS) - 1
    build = (scm_dir / "build_scm.py").read_text(encoding="utf-8")

    # Scoped to the two tables by name. The file holds others of the same shape
    # whose globals are COMPLETION globals, a block that did not move, so a scan
    # for the shape alone would read those too and call them strays.
    rewards: list[int] = []
    for name in ("PACKAGE_REWARD_APPLY = [", "booleans = ["):
        found = _table_globals(build, name)
        label = name.split(" =")[0]
        visited.append(label)
        if found is None:
            problems.append(f"build_scm.py: {label} not found, so nothing was "
                            "checked")
            continue
        if not found:
            # Present but parsed to nothing, which a merged total would hide:
            # reformat one table and its globals leave coverage silently while
            # the other keeps the run green.
            problems.append(f"build_scm.py: {label} parsed to no globals, so "
                            "nothing in it was checked")
            continue
        rewards += found
    stray = sorted(value for value in rewards
                   if not scm.REWARD_BASE <= value <= reward_top)
    if stray:
        problems.append(
            f"build_scm.py: the reward tables drive ${stray[0]}"
            + (f" and {len(stray) - 1} more" if len(stray) > 1 else "")
            + f", outside the reward block (${scm.REWARD_BASE}..${reward_top})")

    # The armour and health rewards are written straight into the applier body as
    # string literals, in neither table, so a scan of the tables alone leaves the
    # two of the fifteen that are hardest to notice uncovered. Anything below the
    # completion block in that function is bookkeeping and did not move.
    visited.append("add_reward_applier")
    applier = _function_body(build, "def add_reward_applier():")
    if applier is None:
        problems.append("build_scm.py: add_reward_applier not found, so nothing "
                        "was checked")
    else:
        inline = [int(value) for value in re.findall(r"\$(\d{4})", applier)]
        stray = sorted(value for value in inline
                       if value >= scm.COMPLETION_BASE
                       and not scm.REWARD_BASE <= value <= reward_top)
        if stray:
            problems.append(
                f"build_scm.py: add_reward_applier reads ${stray[0]}"
                + (f" and {len(stray) - 1} more" if len(stray) > 1 else "")
                + f", outside the reward block (${scm.REWARD_BASE}.."
                  f"${reward_top})")

    markers = (scm_dir / "add_markers.py").read_text(encoding="utf-8")
    ownership_top = scm.OWNERSHIP_BASE + len(scm.OWNERSHIP_KEYS) - 1
    # A venue gate is the progressive, the purchase's completion global, and the
    # ownership global its AP item drives, in that order.
    visited.append("venue gates")
    owned = [int(value) for value in re.findall(
        r"\[\(\d+, \d+\), \(\d+, \d+\), \((\d+), 1\)\]", markers)]
    if not owned:
        problems.append("add_markers.py: found no venue gates, so nothing was "
                        "checked")
    stray = sorted(value for value in owned
                   if not scm.OWNERSHIP_BASE <= value <= ownership_top)
    if stray:
        problems.append(
            f"add_markers.py: a venue gate reads ${stray[0]}"
            + (f" and {len(stray) - 1} more" if len(stray) > 1 else "")
            + f", outside the ownership block (${scm.OWNERSHIP_BASE}.."
              f"${ownership_top})")

    # What the success line claims was read has to be what this visited.
    assert visited == list(LITERAL_SITES), visited
    return problems


def _cleo_problems(cleo_dir: pathlib.Path, scm: types.ModuleType,
                   data: types.ModuleType) -> list[str]:
    """Checks the compiled CLEO scripts against the block they were built for.

    These are build artefacts: add_markers.py carves each thread out of the
    main.scm source and Sanny compiles it, so the globals inside are whatever the
    layout was at build time. They are gitignored, so a checkout has none until
    someone builds, and an absent one is nothing to judge; a PRESENT one that
    disagrees with the layout is the failure being caught, and it is silent and
    total, since a stale aprewd.cs reads the completion block where the reward
    block used to be and every persistent reward re-gates on some other
    location's completion flag.

    So each script gets the band its own globals must fall in, rather than an
    exact list, which stays true as the SCM grows and still catches a shift. A
    band cannot catch a shift smaller than its own block, which no shift here has
    been; what it does catch is a block moving out from under a script.
    """
    reward_top = scm.REWARD_BASE + len(scm.REWARD_KEYS) - 1
    # Phil's four stands, which the pickup watcher polls even though the shop
    # class owns them: they are in-shop pickups the engine sells, so no shop
    # thread can reach them. They are the last four rows of shop_data, so they
    # are a contiguous run at the top of the shop block, and appickup.cs is
    # allowed that run as well as the pickup run.
    stand_globals = [
        scm.completion_global(data.shop_data.shop_item_name(item))
        for item in data.shop_data.SHOP_ITEMS
        if item.thread in data.shop_data.SHOP_PICKUP_THREADS
    ]
    # A LIST of runs per script rather than one band, because that watcher writes
    # into two blocks and one band spanning both would admit every shop global
    # between them. A band that wide could not catch a stale script at all: the
    # shift that made this necessary was ten globals and the gap is thirty-two.
    bands: dict[str, tuple[tuple[tuple[int, int], ...], str]] = {
        # The reward globals and the two config flags that sit directly above.
        "aprewd.cs": (((scm.REWARD_BASE, scm.EMERGENCY_SHUFFLED_GLOBAL),),
                      f"the reward block and its config flags "
                      f"(${scm.REWARD_BASE}..${reward_top}, "
                      f"${scm.PACKAGES_SHUFFLED_GLOBAL}, "
                      f"${scm.EMERGENCY_SHUFFLED_GLOBAL})"),
        # The retune request, and the resolve map it is answered from.
        "apradio.cs": (((scm.RADIO_RANDOMIZED_GLOBAL, scm.RADIO_REQUEST_GLOBAL),),
                       f"the radio block "
                       f"(${scm.RADIO_RANDOMIZED_GLOBAL}.."
                       f"${scm.RADIO_REQUEST_GLOBAL})"),
        # Completion globals only: the watchers set checks, they read no rewards.
        "apwatchers.cs": (((scm.COMPLETION_BASE, scm.REWARD_BASE - 1),),
                          "the completion block"),
        # The pickup watcher reads each slot's handle, which is a vanilla global
        # below the reserved block, and writes only the completion global of the
        # slot or stand it polled, so its runs are the pickup run inside the
        # completion block and Phil's four stands at the top of the shop run.
        "appickup.cs": (((scm.completion_global(data.PICKUP_NAMES[0]),
                          scm.completion_global(data.PICKUP_NAMES[-1])),
                         (min(stand_globals), max(stand_globals))),
                        f"the ambient pickup completion globals and Phil's "
                        f"stands (${min(stand_globals)}..${max(stand_globals)})"),
        # The area thread reads unlock globals and bookkeeping, both of which sit
        # below the completion block, so it may reach nothing from there up. Named
        # rather than left out, since a script this cannot see is a script nothing
        # checks.
        "aparea.cs": (((0, scm.COMPLETION_BASE - 1),),
                      "the unlock and bookkeeping globals below the completion "
                      "block"),
    }
    # The success line counts CLEO_SCRIPTS; this is what actually judges them, so
    # a script added to one and not the other is a script reported as read and
    # never looked at.
    assert set(bands) == set(CLEO_SCRIPTS), sorted(set(bands) ^ set(CLEO_SCRIPTS))

    problems: list[str] = []
    for name, (runs, description) in bands.items():
        path = cleo_dir / name
        if not path.is_file():
            # Gitignored, so a checkout or a CI run has none. Nothing to judge.
            continue
        # Anything below the completion block is bookkeeping or an unlock global,
        # and none of those moved, so the band applies from there up.
        stray = sorted(index for index in _reserved_references(path)
                       if index >= scm.COMPLETION_BASE
                       and not any(low <= index <= high for low, high in runs))
        if stray:
            problems.append(
                f"mod/cleo/{name}: reads ${stray[0]}"
                + (f" and {len(stray) - 1} more" if len(stray) > 1 else "")
                + f", outside {description}. Either the compiled script is stale, "
                  "in which case rebuilding main.scm regenerates it, or the scan "
                  "read a byte pair that only looks like a global, which a "
                  "rebuild leaves in place.")
    return problems


def _self_test() -> None:
    """Exercises the five parsers on synthetic input.

    This script gates scripts/run_tests.py, so its parsers block every commit,
    and every one of them is a hand-rolled reader of a file format nothing else
    validates. The mutation checks that proved they catch a stale mirror were run
    by hand and are not repeatable; these are.
    """
    source = chr(10).join([
        "TABLE = [",
        '    (9486, "$1309 = 1"), (9487, "$1310 = 1"),',
        "]",
        "",
        "NEIGHBOUR = [",
        '    (9999, "$1315 = 1"),',
        "]",
        "",
        "EMPTY = [",
        "    'nothing shaped like a global here',",
        "]",
        "",
        "def applier():",
        '    body = ["$9498 >= 1", "$9008 == 0"]',
        "    nested = [",
        '        (9496, "one indented table, the shape the real one has"),',
        "    ]",
        "    return body, nested",
        "",
        "# A comment at column zero ends the body above.",
        "TRAILING = 1",
    ])
    # Bounded at the closing bracket: the table that follows is global-shaped
    # too, so reading past the end would pick 9999 up. This is what makes the
    # bracket scan load bearing rather than decorative.
    assert _table_globals(source, "TABLE = [") == [9486, 9487]
    # And bounded when the table is indented, which is the case that actually
    # runs: the real `booleans = [` sits inside a function.
    assert _table_globals(source, "nested = [") == [9496]
    # Present but matching nothing is not the same as absent, and the caller
    # reports them differently.
    assert _table_globals(source, "EMPTY = [") == []
    assert _table_globals(source, "MISSING = [") is None

    body = _function_body(source, "def applier():")
    assert body is not None
    assert "$9498" in body
    # Bounded: the column zero comment and what follows are not part of it.
    assert "TRAILING" not in body
    assert _function_body(source, "def absent():") is None

    enum = chr(10).join([
        "enum Thing {",
        "  kThingFirst = 0,",
        "  kThingSecond,",
        "  // a comment that is not a member",
        "  kThingCount,",
        "};",
    ])
    assert _enum_terminator(enum, "enum Thing {", "kThingCount") == 2
    assert _enum_terminator(enum, "enum Thing {", "kAbsent") is None
    assert _enum_terminator(enum, "enum Missing {", "kThingCount") is None
    # A member with a value of its own breaks the position-is-the-value premise,
    # so the count is refused rather than guessed.
    renumbered = enum.replace("  kThingSecond,", "  kThingSecond = 7,")
    assert _enum_terminator(renumbered, "enum Thing {", "kThingCount") is None

    # 0x02 then the index times four, little endian. 9486 * 4 is 0x9438, so the
    # bytes are 02 38 94; the trailing pair is not divisible by four and the
    # leading one decodes below the reserved block, so neither is read.
    assert _decode_reserved(bytes([0x02, 0x38, 0x94])) == {9486}
    assert _decode_reserved(bytes([0x02, 0x01, 0x00])) == set()
    assert _decode_reserved(bytes([0x02, 0x04, 0x00])) == set()

    keys = chr(10).join([
        'SHOP_PENDING_NAME_KEY = "APITEM"',
        'NEIGHBOUR = "APOTHER"',
        '    INDENTED = "NOTMINE"',
        'COMMENTED = "APITEM"  # trailing text ends the line',
    ])
    assert _text_key(keys, "SHOP_PENDING_NAME_KEY") == "APITEM"
    assert _text_key(keys, "NEIGHBOUR") == "APOTHER"
    # Column zero only, so a constant of the same name inside a function or a
    # docstring cannot answer for the module's own.
    assert _text_key(keys, "INDENTED") is None
    # The line has to BE the assignment: a trailing comment means the value read
    # is not the whole line, which is how a stale key would slip through.
    assert _text_key(keys, "COMMENTED") is None
    assert _text_key(keys, "ABSENT") is None


DISTRICT_LIST = re.compile(r"^DISTRICTS = \[\n(.*?)^\]$", re.MULTILINE | re.DOTALL)


def _match_tolerance_problems(asi_dir: pathlib.Path, data) -> list[str]:
    """The one mirror that is a distance rather than a global.

    The ASI matches a layout row to a pool entry by position, and how far it
    looks decides which pickup a row can be paired with. The world holds the same
    number and the two measured bounds it has to sit between, both taken over the
    decompile by dump_pickups.py, so this compares the number and then re-checks
    the bounds against the ASI's own copy: the world asserting them on import
    proves nothing about the value the game actually uses.

    Squared in the header, because that is what the matcher compares, so the
    comparison is done squared too rather than through a square root that would
    have to be spelled to the same precision on both sides.
    """
    header = asi_dir / "scm_pickup_layout.hpp"
    if not header.is_file():
        return [f"ASI: {header.name} is missing, so the match tolerance was "
                f"not checked"]
    text = header.read_text(encoding="utf-8")
    match = re.search(r"kMatchDistanceSquared\s*=\s*(?P<value>[0-9.]+)\s*;", text)
    if match is None:
        return ["ASI: kMatchDistanceSquared not found, so nothing was checked"]
    found = float(match.group("value"))
    wanted = data.PICKUP_MATCH_TOLERANCE ** 2
    problems: list[str] = []
    if abs(found - wanted) > 1e-9:
        problems.append(
            f"ASI: kMatchDistanceSquared is {found}, the world derives {wanted} "
            f"from a tolerance of {data.PICKUP_MATCH_TOLERANCE} units")
    if found >= data.PICKUP_NEAREST_FOREIGN ** 2:
        problems.append(
            f"ASI: kMatchDistanceSquared of {found} reaches the closest pickup "
            f"no table owns, {data.PICKUP_NEAREST_FOREIGN} units from a slot, so "
            f"a slot could be matched to a pickup that is not it")
    if found >= data.PICKUP_CLOSEST_SLOT_PAIR ** 2:
        problems.append(
            f"ASI: kMatchDistanceSquared of {found} reaches from one slot to the "
            f"next, {data.PICKUP_CLOSEST_SLOT_PAIR} units away")
    return problems


def _district_list_problems(scm_dir: pathlib.Path, scm) -> list[str]:
    """build_scm.py's district list against scm.DISTRICT_KEYS, name by name.

    The list fixes which global each per-site gate reads, so a name in the wrong
    place gates the wrong part of town, silently and only in game. Comparing the
    LENGTHS would not see that, which is all the ASI's kDistrictCount can do, and
    this list is no longer a copy of district_data.DISTRICTS either: the Junk
    Yard is a district of the map that holds nothing a content key covers, so it
    has no column here. Two lists that are alike but not identical are exactly
    the pair worth checking by name.
    """
    source = scm_dir / "build_scm.py"
    match = DISTRICT_LIST.search(source.read_text(encoding="utf-8"))
    if match is None:
        return [f"{source.name}: no DISTRICTS list found, so nothing was checked"]
    mirrored = re.findall(r'"([^"]+)"', match.group(1))
    if mirrored == list(scm.DISTRICT_KEYS):
        return []
    return [f"{source.name}: DISTRICTS is {mirrored}, the world derives "
            f"{list(scm.DISTRICT_KEYS)}"]


# The one package whose route in the world is true only because build_scm.py
# edits the map for it, and the mission that route names.
PAD_DOOR_PACKAGE = 25
PAD_DOOR_MISSION = "Treacherous Swine"


def _pad_door_problems(scm_dir: pathlib.Path, data) -> list[str]:
    """Package 25's mission route against the build edit that makes it true.

    Vanilla shuts Gonzalez's pad again when Treacherous Swine tears down, so
    that route is a window inside one mission until build_scm.py leaves the
    pad's door open. Neither file can see the other, and the failure is silent
    in both directions: without the edit the world goes on placing progression
    behind a package a helicopter is the only way back to, and without the route
    the edit opens a door for nothing. They are a pair, so they are checked as
    one.
    """
    source = scm_dir / "build_scm.py"
    build = source.read_text(encoding="utf-8")
    routed = any(data.mission_passed_item_name(PAD_DOOR_MISSION) in route
                 for route in data.PACKAGE_ABILITY_ALTERNATIVES.get(PAD_DOOR_PACKAGE, []))
    edited = ("def open_gonzalez_pad_door():" in build
              and "open_gonzalez_pad_door()" in build.splitlines())
    if routed == edited:
        return []
    if routed:
        return [f"{source.name}: package {PAD_DOOR_PACKAGE} is reached through "
                f"{PAD_DOOR_MISSION}, but open_gonzalez_pad_door is not both "
                "defined and called, so the pad shuts again at that mission's "
                "teardown and the route is a window inside it"]
    return [f"{source.name}: open_gonzalez_pad_door leaves the pad open for a "
            f"route package {PAD_DOOR_PACKAGE} no longer takes"]


# A text table key a mod script prints, as `NAME = "KEY"` at column zero.
TEXT_KEY_CONSTANT = re.compile(r'^(?P<name>[A-Z_]+) = "(?P<key>[^"]*)"$',
                               re.MULTILINE)

# What the format allows a key to be. A key past this, or one add_gxt_key cannot
# encode, makes it raise; patch_text_tables turns that into a log line and
# text_tables_are_patched then reads as never patched, so the client redeploys on
# every launch and the stand prints a raw key forever. Nothing else in the world
# checks either half.
MAXIMUM_TEXT_KEY_BYTES = 8


def _text_key(text: str, name: str) -> str | None:
    """The value of one `NAME = "KEY"` line, or None when the file has none."""
    for match in TEXT_KEY_CONSTANT.finditer(text):
        if match.group("name") == name:
            return match.group("key")
    return None


def _text_key_problems(scm_dir: pathlib.Path, installer) -> list[str]:
    """The text table key a pending shop stand announces itself by, and the
    length every shipped key has to fit in.

    The shop threads print the key and the installer is what puts the string in
    the game's own tables, and neither can see the other. Drift is silent in
    game rather than loud: the game finds no such key and draws the raw name
    back, so a stand wearing the AP marker goes on calling itself a chainsaw,
    which is the exact thing the key exists to stop.
    """
    source = scm_dir / "build_scm.py"
    printed = _text_key(source.read_text(encoding="utf-8"),
                        "SHOP_PENDING_NAME_KEY")
    problems: list[str] = []
    if printed is None:
        problems.append(f"{source.name}: SHOP_PENDING_NAME_KEY not found, so "
                        "the shop stand key was not checked")
    elif printed != installer.SHOP_ITEM_TEXT_KEY:
        problems.append(
            f"{source.name}: the shops print {printed!r} where the installer "
            f"adds {installer.SHOP_ITEM_TEXT_KEY!r}")
    if installer.SHOP_ITEM_TEXT_KEY not in installer.ADDED_TEXT:
        problems.append(
            f"installer.py: {installer.SHOP_ITEM_TEXT_KEY!r} is not in "
            "ADDED_TEXT, so no text table ever gains it")
    for key in installer.ADDED_TEXT:
        # Measured the way add_gxt_key measures it, STRICTLY: an errors handler
        # here would map a character the encoder rejects to a one byte "?" and
        # pass a key that raises on the way into the table.
        try:
            length = len(key.encode("ascii"))
        except UnicodeEncodeError:
            problems.append(
                f"installer.py: ADDED_TEXT carries {key!r}, which add_gxt_key "
                "cannot encode, so it raises inside the handler patch_text_tables "
                "reports and no table is ever patched")
            continue
        if length < 1 or length > MAXIMUM_TEXT_KEY_BYTES:
            problems.append(
                f"installer.py: ADDED_TEXT carries {key!r}, {length} bytes "
                f"where a text table key is 1 to {MAXIMUM_TEXT_KEY_BYTES}, so "
                "no table would ever be patched and the client would redeploy "
                "on every launch")
    return problems


def main() -> int:
    _self_test()
    root = archipelago_root()
    if root is None:
        print("No Archipelago checkout found. Set AP_ROOT or clone 0.6.7 as a sibling.")
        return 1
    if link_world(root) is None:
        return 1
    sys.path.insert(0, str(root))
    from worlds.gta_vice_city import data, installer, scm

    scm_dir = REPOSITORY_ROOT / "mod" / "scm"
    asi_dir = REPOSITORY_ROOT / "mod" / "asi" / "src"

    build = _constants(scm_dir / "build_scm.py",
                       r"^(?P<name>[A-Z_]+) = (?P<value>\d+)$")
    markers = _constants(scm_dir / "add_markers.py",
                         r"^(?P<name>[A-Z_]+) = (?P<value>\d+)$")

    asi: dict[str, int] = {}
    asi_collisions: list[str] = []
    for source in sorted(asi_dir.glob("*.hpp")) + sorted(asi_dir.glob("*.cpp")):
        for name, value in _constants(
                source,
                r"^constexpr int (?P<name>k[A-Za-z]+) = (?P<value>\d+);").items():
            # Merging the files into one table means a name defined twice would
            # resolve to whichever file sorts last, and the mirror it disagrees
            # with would never be compared. None collide today; saying so is the
            # point.
            if name in asi and asi[name] != value:
                asi_collisions.append(
                    f"ASI: {name} is defined twice with different values, "
                    f"{asi[name]} and {value}, so which one is checked depends "
                    "on the file order")
            asi[name] = value

    # The two counts written as enum terminators rather than as constants.
    for enum_opening, terminator in (
            ("enum ContentIndex {", "kContentCount"),
            ("enum AbilityIndex {", "kAbilityCount")):
        # Every file, not the first that answers: an enum defined twice is the
        # same hole the constant scan reports, and stopping at the first match
        # would hide it.
        for source in sorted(asi_dir.glob("*.hpp")):
            counted = _enum_terminator(
                source.read_text(encoding="utf-8"), enum_opening, terminator)
            if counted is None:
                continue
            if terminator in asi and asi[terminator] != counted:
                asi_collisions.append(
                    f"ASI: {terminator} counts {asi[terminator]} in one enum and "
                    f"{counted} in another, so which one is checked depends on "
                    "the file order")
            asi[terminator] = counted

    # Left is the mirror, right is what the world derives. Names differ where the
    # mod side named a global for what it gates rather than for its block.
    expected: list[tuple[str, dict[str, int], str, int]] = [
        ("build_scm.py", build, "UNLOCK_FIRST", scm.UNLOCK_BASE),
        # The unlock block is the progressive strands and then the area items,
        # and build_scm.py names only the strand half here: the area unlocks
        # above it are MAINLAND_UNLOCKS, listed one by one because the gates read
        # them one by one. So this is the last strand, not the top of the block.
        ("build_scm.py", build, "UNLOCK_LAST",
         scm.UNLOCK_BASE + len(data.progressive_strands()) - 1),
        ("build_scm.py", build, "FINALE_ACTIVE", scm.FINALE_ACTIVE_GLOBAL),
        ("build_scm.py", build, "PACKAGES_SHUFFLED", scm.PACKAGES_SHUFFLED_GLOBAL),
        ("build_scm.py", build, "EMERGENCY_SHUFFLED", scm.EMERGENCY_SHUFFLED_GLOBAL),
        ("build_scm.py", build, "RADIO_RESOLVE_BASE", scm.RADIO_RESOLVE_BASE),
        ("build_scm.py", build, "RADIO_REQUEST", scm.RADIO_REQUEST_GLOBAL),
        ("build_scm.py", build, "OWNERSHIP_BASE", scm.OWNERSHIP_BASE),
        ("build_scm.py", build, "MINIMAP_UNLOCK", scm.MINIMAP_UNLOCK_GLOBAL),
        ("build_scm.py", build, "SIDE_EVENTS_ENABLED", scm.SIDE_EVENTS_CASH_GLOBAL),
        ("build_scm.py", build, "STUNT_JUMPS_ENABLED", scm.STUNT_JUMPS_CASH_GLOBAL),
        ("build_scm.py", build, "RAMPAGES_ENABLED", scm.RAMPAGES_CASH_GLOBAL),
        ("build_scm.py", build, "PROPERTIES_ENABLED", scm.PROPERTIES_CASH_GLOBAL),
        ("build_scm.py", build, "CONTENT_LOCK_FLAG_BASE", scm.CONTENT_LOCK_FLAG_BASE),
        ("build_scm.py", build, "CONTENT_UNLOCK_BASE", scm.CONTENT_UNLOCK_BASE),
        ("build_scm.py", build, "DISTRICT_UNLOCK_BASE", scm.DISTRICT_UNLOCK_BASE),
        # The foundation writes the top of the block once so Sanny sizes it, and
        # the marker scratch starts one above that write.
        ("add_markers.py", markers, "SIZING_GLOBAL", scm.highest_reserved_global()),
        # The watcher polls nothing until the seed hash is stamped, so the global
        # it waits on is as load-bearing as the ones it writes.
        ("add_markers.py", markers, "SEED_HASH_GLOBAL", scm.SEED_HASH_BASE),
        # The pickup watcher writes one completion global per slot, contiguous
        # from the first pickup location. A base that drifts writes 110 checks
        # onto whatever locations sit there instead, which is silent in game.
        ("add_markers.py", markers, "PICKUP_COMPLETION_BASE",
         scm.completion_global(data.PICKUP_NAMES[0])),
        # The shop run sits INSIDE the completion block, directly above the
        # pickup run, so it moves when pickup slots are added and stays put when
        # shop items are. That is the trap: every base ABOVE the completion block
        # moves by the whole class list, so a blanket shift of those leaves this
        # one behind, and the shop items then write other locations' completion
        # globals. build_scm.py holds it as a literal and is checked here;
        # add_markers.py derives it from PICKUP_COMPLETION_BASE and the slot
        # table, so there is nothing there to drift and nothing to pin.
        ("build_scm.py", build, "SHOP_COMPLETION_BASE",
         scm.completion_global(data.shop_data.SHOP_ITEM_NAMES[0])),
        ("ASI", asi, "kPackagesShuffledGlobal", scm.PACKAGES_SHUFFLED_GLOBAL),
        ("ASI", asi, "kRadioRandomizedGlobal", scm.RADIO_RANDOMIZED_GLOBAL),
        ("ASI", asi, "kRadioUnlockBase", scm.RADIO_UNLOCK_BASE),
        ("ASI", asi, "kRadioResolveBase", scm.RADIO_RESOLVE_BASE),
        ("ASI", asi, "kRadioRequestGlobal", scm.RADIO_REQUEST_GLOBAL),
        ("ASI", asi, "kMinimapShuffledGlobal", scm.MINIMAP_SHUFFLED_GLOBAL),
        ("ASI", asi, "kMinimapUnlockGlobal", scm.MINIMAP_UNLOCK_GLOBAL),
        ("ASI", asi, "kAbilityLockFlagBase", scm.ABILITY_LOCK_FLAG_BASE),
        ("ASI", asi, "kAbilityUnlockBase", scm.ABILITY_UNLOCK_BASE),
        ("ASI", asi, "kContentLockFlagBase", scm.CONTENT_LOCK_FLAG_BASE),
        ("ASI", asi, "kDistrictUnlockBase", scm.DISTRICT_UNLOCK_BASE),
        # What a district unlock holds. Drift here is silent twice over: every
        # gate asks ">= 1" so the game plays the same, and the page simply
        # reverts to counting all eleven districts and offering the empty ones.
        ("ASI", asi, "kDistrictReleased", scm.DISTRICT_RELEASED),
        ("ASI", asi, "kDistrictAbsent", scm.DISTRICT_ABSENT),
        ("ASI", asi, "kFinaleActiveGlobal", scm.FINALE_ACTIVE_GLOBAL),
        ("ASI", asi, "kFinaleWarpGlobal", scm.FINALE_WARP_GLOBAL),
        # The district block is addressed as base plus class times stride plus
        # district, so this count is the stride. A base that drifts moves every
        # global together and shows up immediately; a stride that drifts still
        # addresses district zero of class zero correctly and misses everything
        # else, which is the harder failure to see.
        ("ASI", asi, "kDistrictCount", len(scm.DISTRICT_KEYS)),
        ("ASI", asi, "kRadioStationCount", scm.RADIO_STATION_COUNT),
        ("ASI", asi, "kSeedHashBase", scm.SEED_HASH_BASE),
        ("ASI", asi, "kSeedHashGlobalCount", scm.SEED_HASH_GLOBAL_COUNT),
        ("ASI", asi, "kAppliedIndexGlobal", scm.APPLIED_INDEX_GLOBAL),
        # Both size a block the ASI walks. A kContentCount that grew would run
        # the district loop off the end of its block and into the finale warp
        # flag, which is the global directly above it.
        ("ASI", asi, "kContentCount", len(scm.CONTENT_KEYS)),
        ("ASI", asi, "kAbilityCount", len(scm.ABILITY_KEYS)),
    ]

    cleo_dir = REPOSITORY_ROOT / "mod" / "cleo"

    problems: list[str] = list(asi_collisions)
    problems.extend(_cleo_problems(cleo_dir, scm, data))
    problems.extend(_literal_table_problems(scm_dir, scm))
    problems.extend(_district_list_problems(scm_dir, scm))
    problems.extend(_pad_door_problems(scm_dir, data))
    problems.extend(_text_key_problems(scm_dir, installer))
    problems.extend(_match_tolerance_problems(asi_dir, data))
    for where, source, name, want in expected:
        if name not in source:
            problems.append(f"{where}: {name} not found, so nothing was checked")
            continue
        if source[name] != want:
            problems.append(
                f"{where}: {name} is {source[name]}, the world derives {want} "
                f"(off by {want - source[name]})")

    if problems:
        print("Reserved global mirrors disagree with scm.py:")
        for problem in problems:
            print(f"  {problem}")
        print()
        print("Every base above the completion block moves when a location is "
              "added. Shift each mirror by the same amount, rebuild main.scm and "
              "rebuild the ASI.")
        return 1

    # A green line that counts what it did not read is a green line that lies:
    # the compiled scripts are gitignored, so a checkout and every CI run has
    # none of them, and that is the usual case rather than the exception. Both
    # numbers come from the set actually judged, so a fifth compiled script that
    # nothing looks at cannot inflate them.
    present = sum(1 for name in CLEO_SCRIPTS if (cleo_dir / name).is_file())
    print(f"{len(expected)} named mirrors, {len(LITERAL_SITES)} literal sites "
          f"and {present} of {len(CLEO_SCRIPTS)} judged CLEO scripts present "
          f"agree with scm.py "
          f"(block tops out at ${scm.highest_reserved_global()}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
