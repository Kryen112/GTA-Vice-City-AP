"""Second pass over the built decompile: make mission-giver markers AP-driven.

Each managed mission gets its own fresh marker handle at the vanilla coordinates
and sprite. A central APMARK watcher shows a mission's marker only while that
mission is the active (first-unpassed, in-order) one in its strand AND its unlock
gate holds, and starts the mission's launcher at that moment. Vanilla's own
marker reveals and launcher starts for these missions are severed, so nothing
appears on the map until the AP unlock lands. Marker coordinates are static
(each coord global is assigned once at init), so a fresh handle at those coords
reproduces the vanilla marker without depending on vanilla's reveal timing.

The whole pass is also held until the game's opening mission is done, so the
first mission of the game is the first mission of the seed whatever items are in
hand when it starts.
"""
from __future__ import annotations

import os
import re
import sys

# The world's own pickup and shop tables, for the handles the pickup watcher
# polls and for where Phil's four stands sit in the shop block.
# A leaf module with no Archipelago imports, so this stays a standalone script.
# Appended rather than inserted: that directory holds a dozen generically
# named modules (data, items, options, regions, rules, scm) and putting it
# first would shadow them for the rest of the process.
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "..", "apworld", "gta_vice_city"))
import pickup_data
import shop_data

SRC, DST = sys.argv[1], sys.argv[2]
CLEO_OUT = sys.argv[3] if len(sys.argv) > 3 else None

# A gate term meaning "any mainland crossing", mirroring build_scm.MAINLAND_ANY.
# Mainland Access and the four crossing items are alternatives, so a gate naming
# one of them alone would hold forever under the setting that never writes it.
MAINLAND_ANY = "any mainland crossing"
MAINLAND_UNLOCKS = [9030, 9032, 9033, 9034, 9035]

# A gate term meaning "this vanilla mission has passed", mirroring
# build_scm.MISSION_PASSED and, behind it, data.IN_GAME_PASSED_PREREQUISITES.
# Written as the launcher whose guard flag records the pass; the flag itself is
# read out of the source, the way this pass reads every marker coordinate. Only
# strand_block emits it, so the term belongs in STRANDS and nowhere else.
MISSION_PASSED = "mission passed"


def mission_passed(launcher):
    """The gate term for the mission `launcher` starts having been passed."""
    return (MISSION_PASSED, launcher)


# The vanilla flag An Old Friend sets as it ends, which is the game's own record
# that the opening mission is done. Read rather than mirrored into a reserved
# global, the way the finale gate reads vanilla $273, $268 and $1175: it is a
# vanilla fact, and reading it does not depend on the HOT launcher still running
# to have observed it.
AN_OLD_FRIEND_PASSED = 222
# The mission's own thread, whose end is the one place that flag is set.
AN_OLD_FRIEND_THREAD = "HOTEL"

# Strand -> ordered launchers, and each launcher's unlock gate (global, count).
# Mirrors build_scm.py MISSIONS. HOT (free, sphere-0) keeps its vanilla marker.
# ICE1 (Cherry Popper, no locate marker) and the venue selectors are handled by
# whether a locate/coords is found, not skipped by name.
STRANDS = {
    "Rosenberg": [("LAW1", [(9010, 1)]), ("LAW2", [(9010, 2)]),
                  ("LAW3", [(9010, 3)]), ("LAW4", [(9010, 4)])],
    "Cortez": [("GEN1", [(9011, 1)]), ("GEN2", [(9011, 2)]),
               ("GEN3", [(9011, 3)]), ("GEN4", [(9011, 4)]),
               ("GEN5", [(9011, 5)])],
    "Diaz": [("BAR1", [(9012, 1)]), ("BAR2", [(9012, 2)]),
             ("BAR3", [(9012, 3)]), ("BAR4", [(9012, 4)]),
             ("BAR5", [(9012, 5), (9013, 1)])],
    "DeathRow": [("KEN1", [(9013, 1)])],
    "Avery": [("SER1", [(9014, 1)]), ("SER2", [(9014, 2)]), ("SER3", [(9014, 3)])],
    "Phil": [("PHI1", [(9015, 1)]), ("PHI2", [(9015, 2)])],
    # The protection strand gives from the estate, so its markers also wait on
    # Rub Out having passed and handed the mansion over: on the unlock alone
    # they stand inside the mansion while Diaz still owns it. The term subsumes
    # the strand's Diaz unlock count, since Rub Out cannot pass before its own
    # gate opens on that count.
    "VercettiProtection": [("PRO1", [(9016, 1), mission_passed("BAR5")]),
                           ("PRO2", [(9016, 2), mission_passed("BAR5")]),
                           ("PRO3", [(9016, 3), mission_passed("BAR5")])],
    "Baker": [("BIK1", [(9017, 1)]), ("BIK2", [(9017, 2)]), ("BIK3", [(9017, 3)])],
    "Umberto": [("CUB1", [(9018, 1)]), ("CUB2", [(9018, 2)]),
                ("CUB3", [(9018, 3)]), ("CUB4", [(9018, 4)])],
    "Poulet": [("HAT1", [(9019, 1)]), ("HAT2", [(9019, 2)]), ("HAT3", [(9019, 3)])],
    "LoveFist": [("ROC1", [(9020, 1)]), ("ROC2", [(9020, 2)]), ("ROC3", [(9020, 3)])],
    "MrBlack": [("ASSIN_1", [(9021, 1)]), ("ASSIN_2", [(9021, 2)]), ("ASSIN_3", [(9021, 3)]),
                ("ASSIN_4", [(9021, 4)]), ("ASSIN_5", [(9021, 5)])],
    # Cap the Collector keeps its vanilla asset prerequisite: Hit the Courier
    # passed ($273), Cop Land passed ($268), and the owned-asset count $1175
    # at seven or more, so the finale marker and launcher wait for the assets.
    # The last mission's mainland term is MAINLAND_ANY, since Mainland Access and
    # the crossing items are alternatives and this gate guards both the marker
    # and the launcher start.
    "VercettiFinale": [("FIN1", [(9022, 1), (9016, 3), (268, 1), (273, 1), (1175, 7)]),
                       ("FIN2", [(9022, 2), (9016, 3), MAINLAND_ANY])],
    # Venue strand gates also require the property bought (the venue purchase's
    # completion global) and owned (the ownership global its AP item drives),
    # so the beam and blip stay hidden and the launcher stays unstarted until
    # the progressive, the purchase, and the ownership item all exist.
    "Malibu": [("BANK1", [(9023, 1), (9341, 1), (9570, 1)]),
               ("BANK2", [(9023, 2), (9341, 1), (9570, 1)]),
               ("BANK3", [(9023, 3), (9341, 1), (9570, 1)]),
               ("BANK4", [(9023, 4), (9341, 1), (9570, 1)])],
    "FilmStudio": [("PORN1", [(9024, 1), (9338, 1), (9567, 1)]),
                   ("PORN2", [(9024, 2), (9338, 1), (9567, 1)]),
                   ("PORN3", [(9024, 3), (9338, 1), (9567, 1)]),
                   ("PORN4", [(9024, 4), (9338, 1), (9567, 1)])],
    "Printworks": [("COU1", [(9025, 1), (9336, 1), (9565, 1)]),
                   ("COU2", [(9025, 2), (9336, 1), (9565, 1)])],
    "KaufmanCabs": [("TWAR1", [(9026, 1), (9340, 1), (9569, 1)]),
                    ("TWAR2", [(9026, 2), (9340, 1), (9569, 1)]),
                    ("TWAR3", [(9026, 3), (9340, 1), (9569, 1)])],
}

# Fresh scratch globals, all above the reserved block, whose top is the finale
# active flag: build_scm's foundation sizes the reserved block by writing that
# global once, and this scratch starts one above it. Both halves of that
# relation live here so they move together, and the write before DST is checked
# against it. One handle, one started-flag, one shown-flag per managed mission.
SIZING_GLOBAL = 9669

# The ambient pickup checks. Their completion globals are contiguous from
# here, one per slot in pickup_data order, because the pickup class is the
# last one in the world's registry and completion globals follow location id
# order. The handles come from pickup_data itself rather than from a copy.
PICKUP_COMPLETION_BASE = 9376

# The shop checks, contiguous from here for the same reason: the shop class is
# registered after the pickup class, so its completion globals follow the whole
# pickup block. Only Phil's four are polled from here, and they are the LAST
# four of the shop block, because shop_data lists them last; the other
# thirty-two are sold by script threads that write their own completion global
# where the sale happens.
SHOP_COMPLETION_BASE = PICKUP_COMPLETION_BASE + len(pickup_data.PICKUP_SLOTS)

# The first of the four globals the ASI packs the seed hash into. Non-zero means
# the ASI has stamped this seed, which is what the pickup watcher waits for
# before latching anything.
#
# Zero is a safe test for "not stamped yet", which is not obvious: the ASI packs
# the hash's ASCII CHARACTERS four to a global, not its hex nibbles, so a hash
# beginning 0000 lands as 0x30303030 rather than as zero. Every character is a
# hex digit, all below 0x80, so the packed value is positive whenever a hash has
# been written and zero only when none has.
SEED_HASH_GLOBAL = 9000
HANDLE_BASE = SIZING_GLOBAL + 1
STARTED_BASE = HANDLE_BASE + 60
SHOWN_BASE = STARTED_BASE + 60
MARKER_SPRITE_DEFAULT = "34"  # generic mission-attempt sprite; overridden per giver

with open(SRC, "rb") as handle:
    raw = handle.read()
nl = "\r\n" if b"\r\n" in raw else "\n"
lines = raw.decode("latin-1").split(nl)

def check_an_old_friend_flag():
    # The APMARK gate reads a vanilla flag, so the build refuses a source where
    # that flag means anything other than "the opening mission is done": it is
    # set exactly once, and inside the mission's own thread. A decompile or an
    # earlier transform that set it from somewhere else would leave the gate
    # holding the whole map on a condition nobody satisfies.
    write = f"${AN_OLD_FRIEND_PASSED} = 1"
    sites = [i for i, ln in enumerate(lines) if ln == write]
    assert len(sites) == 1, (
        f"an old friend: {write} appears at {len(sites)} sites, not one")
    own_name = f"script_name '{AN_OLD_FRIEND_THREAD}'"
    starts = [i for i, ln in enumerate(lines) if ln == own_name]
    assert len(starts) == 1, f"an old friend: {own_name} matched {len(starts)}"
    end = next(i for i in range(starts[0] + 1, len(lines))
               if lines[i].startswith("script_name '"))
    assert starts[0] < sites[0] < end, (
        f"an old friend: {write} is at line {sites[0] + 1}, outside "
        f"{AN_OLD_FRIEND_THREAD}'s own thread")


label_at: dict[str, int] = {}
for i, ln in enumerate(lines):
    if ln.startswith(":") and ln[1:] not in label_at:
        label_at[ln[1:]] = i

check_an_old_friend_flag()

MISSION_HEADER = re.compile(r"^//-------------Mission (\d+)---------------$")


def mission_blocks():
    # Mission number -> (start, end) line span, from the decompile's own header
    # comments. Mirrors build_scm.mission_blocks; build_scm leaves the comments
    # in place, so they are still here to read.
    found = [(int(MISSION_HEADER.match(ln).group(1)), i)
             for i, ln in enumerate(lines) if MISSION_HEADER.match(ln)]
    spans = {}
    for position, (number, start) in enumerate(found):
        end = found[position + 1][1] if position + 1 < len(found) else len(lines)
        spans[number] = (start, end)
    return spans


create_re = re.compile(
    r"^add_sprite_blip_for_contact_point (\$\d+) = create_icon_marker_and_sphere (\S+) at (\S+) (\S+) (\S+)$")


def launcher_locate_coords(label: str):
    start = label_at.get(label)
    if start is None:
        return None
    # Scan the launcher's own thread only, ending at the next thread's
    # script_name: a fixed window breaks when inserted gate conditions push the
    # locate down, and an unbounded one could borrow the next thread's locate.
    for j in range(start + 2, len(lines)):
        if lines[j].startswith("script_name '"):
            break
        m = re.match(r"^  locate_player_\S+ \$player_char \S+ (\S+) (\S+) (\S+) radius", lines[j])
        if m:
            return (m.group(1), m.group(2), m.group(3))
    return None


def sprite_at_coords(coords):
    # Prefer a reveal create (below the init block) at these coords; fall back to
    # the init create. Returns the vanilla sprite id so the marker looks vanilla.
    best = None
    for i, ln in enumerate(lines):
        m = create_re.match(ln)
        if m and (m.group(3), m.group(4), m.group(5)) == coords:
            if i > 600:
                return m.group(2)
            best = m.group(2)
    return best or MARKER_SPRITE_DEFAULT


def passed_flag(label: str):
    # The launcher's guard flag: `if $flag == 1 / goto @gate / terminate`.
    start = label_at.get(label)
    if start is None:
        return None
    for j in range(start, min(start + 40, len(lines))):
        m = re.match(r"^  (\$\S+) == 1$", lines[j])
        if m and lines[j + 1].startswith("goto_if_false @"):
            return m.group(1)
    return None


def launched_mission(label: str):
    # The mission number a launcher starts, read from the source: its first
    # load_and_launch_mission_internal. Every launcher in STRANDS launches a
    # mission, so a missing label or launch is a table error, not a variant.
    start = label_at.get(label)
    assert start is not None, f"play order: launcher {label} has no label"
    launch = next((j for j in range(start, len(lines))
                   if lines[j].startswith("load_and_launch_mission_internal")), None)
    assert launch is not None, f"play order: launcher {label} launches no mission"
    return int(lines[launch].split()[1])


def check_play_order():
    # Same guard as build_scm.py, over this table: Vice City numbers each
    # strand's missions in play order, so a strand whose gate counts do not
    # ascend by mission number has a launcher on the wrong count, and APMARK
    # would reveal the strand's markers out of order. The list position drives
    # APMARK's in-strand ordinal while the gate count drives the unlock, so both
    # orderings are checked and each must agree with the other.
    for strand, missions in STRANDS.items():
        # Same assumption as build_scm.check_play_order, asserted for the same
        # reason: a mainland or passed term first would be read as a count.
        for launcher, gate in missions:
            first = gate[0]
            assert first != MAINLAND_ANY and first[0] != MISSION_PASSED, (
                f"play order: {launcher}'s first gate term is {first}, not its "
                f"strand unlock")
        counts = [gate[0][1] for _, gate in missions]
        assert counts == list(range(1, len(counts) + 1)), (
            f"play order: strand {strand} gate counts {counts} are not 1..N in "
            f"list order")
        numbers = [launched_mission(launcher) for launcher, _ in missions]
        assert numbers == sorted(numbers), (
            f"play order: strand {strand} launches missions {numbers}, which is "
            f"not the vanilla order")


check_play_order()

# Every passed term's flag, resolved here and not where the watcher is written.
# passed_flag indexes into the source through label_at, which is built once at
# load, so a flag read after the severing and the thread relocation below would
# index lines that have moved.
#
# Each flag must also be written at exactly one site AND that write must sit
# inside the block of the mission the launcher launches, both halves of the
# guard check_an_old_friend_flag applies to $222 and for the same reason. A gate
# on a flag nothing sets never opens, and one on a flag written from somewhere
# other than the mission's own pass records something else; either way the
# strand's markers stay off the map while logic calls its missions reachable.
# build_scm.py asserts the same two things over its own table, each file reading
# the flag for itself: two writes in one block would satisfy both, so this narrows
# the two picks to the same block rather than proving them one flag.
PASSED_FLAGS = {}
mission_spans = mission_blocks()
for strand_missions in STRANDS.values():
    for _launcher, gate in strand_missions:
        for term in gate:
            if term == MAINLAND_ANY or term[0] != MISSION_PASSED:
                continue
            if term[1] in PASSED_FLAGS:
                continue
            resolved = passed_flag(term[1])
            assert resolved is not None, (
                f"passed gate: launcher {term[1]} has no guard flag to gate on")
            write = f"{resolved} = 1"
            sites = [i for i, ln in enumerate(lines) if ln == write]
            assert len(sites) == 1, (
                f"passed gate: {write} appears at {len(sites)} sites, not one, "
                f"so the gate cannot name the write that records the pass")
            number = launched_mission(term[1])
            assert number in mission_spans, (
                f"passed gate: mission {number}, which {term[1]} launches, has "
                f"no header comment to read a block from")
            block_start, block_end = mission_spans[number]
            assert block_start < sites[0] < block_end, (
                f"passed gate: {write} is at line {sites[0] + 1}, outside the "
                f"block of the mission {term[1]} launches")
            PASSED_FLAGS[term[1]] = resolved

# Resolve every managed mission to a marker spec. Missions with no locate marker
# (none found) are dropped from marker management and reported.
managed = []          # (strand, ordinal, launcher, gate, coords, sprite, passed)
unmanaged = []        # (launcher, reason)
handle_index = 0
for strand, missions in STRANDS.items():
    for ordinal, (launcher, gate) in enumerate(missions):
        coords = launcher_locate_coords(launcher)
        flag = passed_flag(launcher)
        if coords is None or flag is None:
            unmanaged.append((launcher, "no locate coords" if coords is None else "no passed flag"))
            continue
        managed.append({
            "strand": strand, "ordinal": ordinal, "launcher": launcher, "gate": gate,
            "coords": coords, "sprite": sprite_at_coords(coords), "passed": flag,
            "handle": HANDLE_BASE + handle_index,
            "started": STARTED_BASE + handle_index,
            "shown": SHOWN_BASE + handle_index,
        })
        handle_index += 1

managed_launchers = {m["launcher"] for m in managed}
highest_global = SHOWN_BASE + handle_index - 1

# --- Sever vanilla reveals and starts for managed missions ---------------------
# Delete each vanilla marker REVEAL at a managed mission's coords and each
# `start_new_script @<managed launcher>`. The init pre-build block (a `create`
# immediately followed by `remove_blip` of the same handle) is LEFT intact: it
# creates then hides the vanilla handle at boot, which is harmless because APMARK
# uses its own fresh handles, and removing the create would leave a remove_blip on
# an uninitialized handle. A reveal is a `create` NOT in that init pair.
managed_coords = {m["coords"] for m in managed}
severed_creates = severed_starts = 0
kept = []
for i, ln in enumerate(lines):
    m = create_re.match(ln)
    if m and (m.group(3), m.group(4), m.group(5)) in managed_coords:
        is_init_pair = i + 1 < len(lines) and lines[i + 1] == f"remove_blip {m.group(1)}"
        if not is_init_pair:
            severed_creates += 1
            continue
    s = re.match(r"^start_new_script @(\S+)\s*$", ln)
    if s and s.group(1) in managed_launchers:
        severed_starts += 1
        continue
    kept.append(ln)
lines = kept

# --- Relocate threads out of the MAIN section to CLEO -------------------------
# VC gives the MAIN section a fixed buffer, so a thread that does not have to
# live there should not. Two kinds move. APPKG (100 package checks), APSTAT
# (rampage/stunt/taxi checks) and APACT (activity and side-event flags) poll only
# numeric globals and are rewritten into the watcher below; the completion
# globals they set are unchanged, so the ASI polls them identically. APAREA,
# APREWD, APRADIO and APPAD do real work with objects, road switches and player
# state and are carried across as they stand.
def remove_thread(label):
    """Cuts a whole thread out of MAIN and hands back its body.

    A thread is its entry label and every line under it until a label that is
    not its own, which is NOT the same as everything up to its loop goto: APAREA
    continues past `goto @APAREA_LOOP` into the :APAREA_SHARED subroutine its own
    branches gosub. Cutting at the loop moved the callers and left the callee, and
    Sanny compiles a gosub to a name it cannot see as offset zero and exits zero,
    so nothing downstream catches it.
    """
    start = next((i for i, ln in enumerate(lines) if ln == f":{label}"), None)
    assert start is not None, f"relocate: :{label} not found"
    end = start + 1
    while end < len(lines):
        match = re.fullmatch(r":(\w+)", lines[end])
        if match and not (match.group(1) == label
                          or match.group(1).startswith(f"{label}_")):
            break
        end += 1
    body = lines[start:end]
    # Nothing but this thread may be in the cut: a second script_name would mean
    # the walk ran into the next thread through a label it mistook for its own.
    intruders = [ln for ln in body[1:] if ln.startswith("script_name ")
                 and ln != f"script_name '{label}'"]
    assert not intruders, f"relocate: :{label} cut swallowed {intruders}"
    del lines[start:end]
    while body and body[-1] == "":
        body.pop()
    return body


remove_thread("APPKG")
remove_thread("APSTAT")
remove_thread("APACT")

# Four more threads leave MAIN, and unlike the three above they are carried
# across rather than rewritten: they do real work with objects, road switches and
# player state, so re-expressing them by hand would be a second implementation to
# keep in step. Each becomes its own CLEO script, because a .cs runs from its own
# entry point and two loops in one file would fall through into each other.
# APPAD is here for a second reason besides the buffer: out of main.scm it cannot
# change that file's size, so shipping it cannot shift an offset a save in
# progress still points at.
#
# What makes these four portable and APMARK not: none of them names a label
# outside itself, so nothing has to reach back into main.scm. APMARK starts a
# mission launcher per managed mission, and a label belongs to the file it
# compiles in, so it cannot follow until something else can start those threads.
PORTABLE_THREADS = [("APAREA", "aparea"), ("APREWD", "aprewd"),
                    ("APRADIO", "apradio"), ("APPAD", "appad")]
ported = []
for label, filename in PORTABLE_THREADS:
    body = remove_thread(label)
    # A CLEO script has no script_name and no entry label of its own; the rest of
    # the body, including every internal label, carries over untouched.
    carried = [ln for ln in body
               if ln != f":{label}" and ln != f"script_name '{label}'"]
    assert carried, f"relocate: :{label} came back empty"
    # The whole point of the cut boundary: a carried thread may not name anything
    # it left behind. Sanny resolves an unknown @name to offset zero and exits
    # zero, so this is the only place the mistake is catchable.
    defined = {match.group(1) for match in
               (re.fullmatch(r":(\w+)", ln) for ln in carried) if match}
    referenced = {match.group(1) for ln in carried
                  for match in re.finditer(r"@(\w+)", ln)}
    dangling = sorted(referenced - defined)
    assert not dangling, (
        f"relocate: :{label} would reference {dangling} left in main.scm")
    ported.append((label, filename, carried))

# The six weapon shops leave MAIN, one file each, the same shape as the three
# above and for the same reason: a CLEO script runs from its own entry point.
#
# One file for all six was tried and does not work. Starting the other five from
# inside the .cs needs start_new_script, and CLEO for VC does not override that
# opcode: the game's own handler stores the operand as the new thread's
# instruction pointer without the negative-label transform that goto, jf and
# gosub all apply, so a label local to a .cs becomes an address below script
# space and the thread runs whatever is there. Only the thread the file itself
# becomes would have run.
#
# What makes one-file-each possible is duplication. Every shop gosubs shared
# subroutines that live inside HARD3's label space, so each file carries its own
# copy of HARD3's body; the copies are inert except through those gosubs, since
# the file's own thread loops and never falls into them. Duplicating is safe
# because a gosub runs in its CALLER's thread, before the move and after it, so
# a copied subroutine sees the same state either way. That includes the till
# ladder's TIMERA, which is per thread and was always the calling shop's.
#
# They are worth moving because they are what grew: the shop check transform in
# build_scm.py adds to exactly these threads, and MAIN had a few hundred bytes
# left. Out here the transform costs MAIN nothing.
SHOP_THREADS = ["AMMU1", "AMMU2", "AMMU3", "HARD1", "HARD2", "HARD3"]
SHOP_SHARED = "HARD3"
shop_carried = []
for label in SHOP_THREADS:
    body = remove_thread(label)
    assert body, f"relocate: :{label} came back empty"
    shop_carried.append((label, body))

# The set has to be closed: every label any of the six names must be defined by
# one of the six. Sanny resolves an unknown @name to offset zero and exits zero,
# so this is the only place the mistake is catchable.
shop_defined = {match.group(1) for _label, body in shop_carried
                for match in (re.fullmatch(r":(\w+)", ln) for ln in body) if match}
shop_referenced = {match.group(1) for _label, body in shop_carried
                   for ln in body for match in re.finditer(r"@(\w+)", ln)}
shop_dangling = sorted(shop_referenced - shop_defined)
assert not shop_dangling, (
    f"relocate: the shop threads would reference {shop_dangling} left in main.scm")

for label in SHOP_THREADS:
    boot = f"start_new_script @{label} "
    assert lines.count(boot) == 1, (
        f"relocate: {boot!r} appears {lines.count(boot)} times, expected 1")
    lines.remove(boot)

for label, _filename in PORTABLE_THREADS:
    # Asserted rather than filtered: a start whose thread has gone would compile
    # to a thread starting at offset zero, silently.
    boot = f"start_new_script @{label} "
    assert lines.count(boot) == 1, (
        f"relocate: {boot!r} appears {lines.count(boot)} times, expected 1")
    lines.remove(boot)
lines = [ln for ln in lines
         if ln not in ("start_new_script @APPKG ", "start_new_script @APSTAT ",
                       "start_new_script @APACT ")]

# Hidden packages are detected per package by the ASI (matching each collected
# collectable pickup to its coordinate), so the CLEO watcher no longer counts
# them; it polls the stat and activity/side-event flags only.
cleo = ["{$CLEO .cs}", "", "0000:", "", ":AW_LOOP", "wait 500"]
stat_checks = ([(f"${1439 + n} == 1", 9180 + n) for n in range(35)]
               + [(f"${795 + n} == 1", 9215 + n) for n in range(36)]
               + [(f"$369 >= {10 * n}", 9286 + n) for n in range(1, 11)])
for idx, (cond, comp) in enumerate(stat_checks):
    cleo += ["if ", f"  {cond}", f"goto_if_false @AW_S{idx}", f"${comp} = 1", f":AW_S{idx}"]
# Activity + side events (APACT), mirroring build_scm.add_activity_watcher:
# Checkpoint Charlie ($607), the six Sunshine Autos races ($1588..$1593, one
# check each in showroom menu order), and 14 side-event win flags. Every flag is
# an independent set-once signal, so each writes its own completion global.
activity_flags = ([(607, 9365)]
                  + [(1587 + race, 9369 + race) for race in range(1, 7)]
                  + [(1597, 9307), (1598, 9308), (55, 9309), (1584, 9310),
                     (1585, 9311), (1586, 9312), (1587, 9313), (8241, 9314),
                     (8485, 9315), (8156, 9316), (363, 9317), (364, 9318),
                     (339, 9319), (351, 9320)])
for idx, (flag, comp) in enumerate(activity_flags):
    cleo += ["if ", f"  ${flag} == 1", f"goto_if_false @AW_E{idx}", f"${comp} = 1", f":AW_E{idx}"]
cleo += ["goto @AW_LOOP", ""]

# --- Build the APPICK watcher -------------------------------------------------
# One pass per frame over every ambient slot and over Phil's four shop stands,
# asking the game whether each has been collected and latching its completion
# global when it has. The ASI already polls every completion global, so this is
# the whole of pickup detection: nothing else has to learn what a pickup is.
#
# wait 0 and not a slower pass, because the answer is CONSUMED by being read.
# has_pickup_been_collected (CPickups::IsPickUpPickedUp, 0x441880) never looks
# at the pickup pool: it scans a twenty-entry ring of recently collected
# handles, and on a match it returns true and zeroes the entry it matched. So a
# collection is an event sitting in a small ring rather than a flag on the
# pickup, and a pass that skipped a frame could find the ring rewritten.
# Vanilla polls this same opcode on the 13 bribe handles from a wait 0 loop,
# which is the same conclusion the game itself came to.
#
# Its own file because a CLEO script runs from its own entry point and two
# loops in one file would fall through into each other.
pickup_cleo = ["{$CLEO .cs}", "", "0000:", "", ":APPICK_LOOP", "wait 0"]
# Poll nothing until the seed hash is stamped. This script starts at frame
# zero whatever the client is doing, and the ASI takes its baseline of the
# completion globals on the first frame it has a hash: anything already
# latched is in that baseline, and a global that starts non-zero is skipped
# forever. So a player who starts a new game before connecting and walks
# over a pickup would lose that check permanently. The hash global is the
# one thing that says the ASI has seen this seed.
pickup_cleo += ["if ", f"  ${SEED_HASH_GLOBAL} > 0",
                "goto_if_false @APPICK_LOOP"]
# Each slot, then each shop stand, as (label, handle global, completion global,
# whether the handle can still be zero). One list so the emitted pass has one
# shape, and the labels stay unique across the two halves.
polled: list[tuple[str, int, int, bool]] = [
    (f"APPICK_{slot}", handle, PICKUP_COMPLETION_BASE + slot,
     slot >= pickup_data.MISSION_CREATED_FIRST_SLOT)
    for slot, handle in enumerate(pickup_data.PICKUP_HANDLE_GLOBALS)
]
# Phil's Place. Its stands are in-shop pickups the engine sells, so they are
# detected here like any pickup even though the shop class owns the check. Their
# completion globals are found by where shop_data lists them rather than by an
# offset written down, so the four moving within that table cannot silently
# point this at another shop's check.
stand_handles = [stand[6] for stand in pickup_data.SHOP_STAND_SLOTS]
stand_offsets = {item.script_global: index
                 for index, item in enumerate(shop_data.SHOP_ITEMS)
                 if item.thread in shop_data.SHOP_PICKUP_THREADS}
assert sorted(stand_offsets) == sorted(stand_handles), (
    f"shop_data lists pickup stands {sorted(stand_offsets)} and pickup_data "
    f"holds {sorted(stand_handles)}, so a stand would be polled into another "
    f"check's completion global")
polled += [
    (f"APPICK_STAND_{index}", handle,
     SHOP_COMPLETION_BASE + stand_offsets[handle], True)
    for index, handle in enumerate(stand_handles)
]
for label, handle, completion, may_be_zero in polled:
    # Set unconditionally while collected rather than testing the global
    # first: the write is idempotent, the ASI reads it as a latch, and one
    # condition per slot keeps the pass cheap.
    #
    # A handle that can still be zero is tested for that FIRST, and that is not
    # tidiness. The ring the opcode scans is zeroed at boot and every read
    # leaves a zero behind, so handle zero matches a spent entry and the opcode
    # answers true: a stand polled before the mission that creates it would
    # report itself collected on the first frame the seed hash is up, and hand
    # over its item for nothing.
    if may_be_zero:
        pickup_cleo += ["if ", f"  ${handle} > 0", f"goto_if_false @{label}"]
    pickup_cleo += ["if ", f"  has_pickup_been_collected ${handle}",
                    f"goto_if_false @{label}",
                    f"${completion} = 1", f":{label}"]
pickup_cleo += ["goto @APPICK_LOOP", ""]
if CLEO_OUT:
    target = os.path.join(os.path.dirname(os.path.abspath(CLEO_OUT)),
                          "appickup.txt")
    with open(target, "wb") as handle_out:
        handle_out.write(nl.join(pickup_cleo).encode("latin-1"))
    stand_globals = [SHOP_COMPLETION_BASE + stand_offsets[handle]
                     for handle in stand_handles]
    print(f"wrote appickup.txt, {len(pickup_data.PICKUP_HANDLE_GLOBALS)} "
          f"slots polled into ${PICKUP_COMPLETION_BASE}.."
          f"${PICKUP_COMPLETION_BASE + len(pickup_data.PICKUP_HANDLE_GLOBALS) - 1}"
          f" and {len(stand_handles)} shop stands into "
          f"${min(stand_globals)}..${max(stand_globals)}")
# A relocated thread may not name a model with #NAME. That syntax compiles to a
# NEGATIVE number, and the game's create_object handler reads it as an index into
# the model-name table the running script owns, then dereferences the result
# straight into the model info array. The table belongs to main.scm, so in a
# CLEO script the index means nothing and the game reads a wild pointer and dies
# where the object would have been created. Every name a carried thread uses is
# therefore resolved to its numeric model id here, from the game's own IDE files,
# and an assertion refuses a name that has no entry rather than shipping a crash.
MODEL_NAME_IDS = {
    "#BODYARMOUR": 368,      # generic.ide, the three Ammu-Nations' armour
    "#COMGATE1OPEN": 2444,   # starisl.ide, the Starfish Island gates
    "#COMGATE2OPEN": 2443,
}


def numeric_models(carried, where):
    """Turns every #NAME model reference into its numeric id."""
    def numbered(match):
        name = match.group(0)
        model = MODEL_NAME_IDS.get(name.upper())
        assert model is not None, (
            f"relocate: {where} names {name} and would crash the game where "
            "the object is created; add its model id to MODEL_NAME_IDS")
        return str(model)

    # Matched whole, so a name that is a prefix of a longer one cannot be
    # rewritten in place of it, and every name is checked rather than only
    # the ones this table happens to hold.
    return [re.sub(r"#[A-Za-z0-9_]+", numbered, line) for line in carried]


if CLEO_OUT:
    with open(CLEO_OUT, "wb") as handle:
        handle.write(nl.join(cleo).encode("latin-1"))
    # One file per carried thread, named for it, beside the watcher.
    directory = os.path.dirname(os.path.abspath(CLEO_OUT))
    for label, filename, carried in ported:
        lines_out = numeric_models(carried, f"{filename}.cs")
        script = ["{$CLEO .cs}", "", "0000:", *lines_out, ""]
        target = os.path.join(directory, f"{filename}.txt")
        with open(target, "wb") as handle:
            handle.write(nl.join(script).encode("latin-1"))
        print(f"relocated {label} to {filename}.txt ({len(carried)} lines)")

    # The six shops, one file each. Every file is its own thread's body followed
    # by a copy of the shared subroutine block, which is HARD3's body; HARD3's
    # own file is just that body. The entry label and script_name come off, the
    # way the three relocations above take them off, because a CLEO script runs
    # from its start and CLEO names it from the filename.
    shared = dict(shop_carried)[SHOP_SHARED]
    shared_copy = [ln for ln in shared if ln != f"script_name '{SHOP_SHARED}'"]
    for label, body in shop_carried:
        own = [ln for ln in body
               if ln != f":{label}" and ln != f"script_name '{label}'"]
        assert own, f"relocate: :{label} has no body of its own"
        carried = own if label == SHOP_SHARED else own + shared_copy
        # Each file has to be closed on its own: whatever it names, it defines.
        defined = {match.group(1) for match in
                   (re.fullmatch(r":(\w+)", ln) for ln in carried) if match}
        referenced = {match.group(1) for ln in carried
                      for match in re.finditer(r"@(\w+)", ln)}
        dangling = sorted(referenced - defined)
        assert not dangling, (
            f"relocate: {label.lower()}.cs would reference {dangling}")
        # Unique, not just present. Sanny binds a repeated label's references to
        # the first definition and compiles clean, so a duplicate is a jump to
        # the wrong place rather than a build failure.
        label_lines = [ln for ln in carried if re.fullmatch(r":\w+", ln)]
        assert len(label_lines) == len(set(label_lines)), (
            f"relocate: {label.lower()}.cs defines a label twice: "
            f"{sorted({ln for ln in label_lines if label_lines.count(ln) > 1})}")
        # The appended copy is only reachable by gosub, which holds because the
        # thread's OWN body ends by transferring away rather than running on into
        # it. Tested on that body, not on `carried`: the copy's own tail is a
        # return, so asserting after the append tests the copy every time and the
        # boundary never.
        assert own[-1].startswith(("goto @", "return")), (
            f"relocate: {label.lower()}.cs's own body ends on {own[-1]!r}, so it "
            "would fall into the copied subroutines")
        filename = f"ap{label.lower()}"
        lines_out = numeric_models(carried, f"{filename}.cs")
        script = ["{$CLEO .cs}", "", "0000:", *lines_out, ""]
        target = os.path.join(directory, f"{filename}.txt")
        with open(target, "wb") as handle:
            handle.write(nl.join(script).encode("latin-1"))
        print(f"relocated {label} to {filename}.txt ({len(carried)} lines)")

# --- Build the APMARK watcher --------------------------------------------------
by_strand: dict[str, list] = {}
for m in managed:
    by_strand.setdefault(m["strand"], []).append(m)

def strand_block(strand, missions):
    out = [f":APMARK_{strand}"]
    done = f"APMARK_{strand}_DONE"
    for m in sorted(missions, key=lambda x: x["ordinal"]):
        launcher = m["launcher"]
        active = f"APMARK_{launcher}_ACTIVE"
        after = f"APMARK_{launcher}_AFTER"
        # Passed: hide this mission's marker if it is still shown, then fall
        # through to the next mission's test. Unpassed: it is the active mission.
        out += ["if ", f"  {m['passed']} == 1", f"goto_if_false @{active}",
                "if ", f"  ${m['shown']} == 1", f"goto_if_false @{after}",
                f"remove_blip ${m['handle']}", f"${m['shown']} = 0", f"goto @{after}",
                f":{active}"]
        # First unpassed mission: decide show/hide on its gate.
        gate_true = f"APMARK_{launcher}_SHOW"
        for term in m["gate"]:
            hide = f"@APMARK_{launcher}_HIDE"
            if term == MAINLAND_ANY:
                out += ["if or", *[f"  ${unlock} >= 1" for unlock in MAINLAND_UNLOCKS],
                        f"goto_if_false {hide}"]
            elif term[0] == MISSION_PASSED:
                out += ["if ", f"  {PASSED_FLAGS[term[1]]} == 1",
                        f"goto_if_false {hide}"]
            else:
                global_index, count = term
                out += ["if ", f"  ${global_index} >= {count}", f"goto_if_false {hide}"]
        # Gate holds: show marker (once) and start launcher (once), then done strand.
        # No remove_blip before create: the handle is either fresh (0, never
        # created) or was just removed by HIDE / the passed path, so there is no
        # stale blip to free and no risk of removing handle 0.
        out += [f":{gate_true}",
                "if ", f"  ${m['shown']} == 0", f"goto_if_false @APMARK_{launcher}_STARTED",
                f"add_sprite_blip_for_contact_point ${m['handle']} = create_icon_marker_and_sphere "
                f"{m['sprite']} at {m['coords'][0]} {m['coords'][1]} {m['coords'][2]}",
                f"${m['shown']} = 1",
                f":APMARK_{launcher}_STARTED",
                "if ", f"  ${m['started']} == 0", f"goto_if_false @{done}",
                f"start_new_script @{launcher}",
                f"${m['started']} = 1",
                f"goto @{done}"]
        # Gate does not hold: hide marker (once), then done strand (nothing later
        # in this strand can be active before this mission is passed).
        out += [f":APMARK_{launcher}_HIDE",
                "if ", f"  ${m['shown']} == 1", f"goto_if_false @{done}",
                f"remove_blip ${m['handle']}",
                f"${m['shown']} = 0",
                f"goto @{done}",
                f":{after}"]
    out += [f":{done}"]
    return out


# Defer all marker work while the player is not controllable (loading, cutscene,
# script-owned interior), while the player is on a mission, or until An Old Friend
# is done. The not-controllable condition is the same flag all item application
# defers on; the on-mission one keeps a launcher start out of an already-running
# mission; the opening-mission one orders the game's first mission ahead of every
# managed one.
#
# That last one is why the pass is gated as a whole rather than per mission. An
# Old Friend is the game's opening mission and the one story mission APMARK does
# not manage: it keeps its vanilla marker and its vanilla launcher, so it stays
# visible and startable while every managed marker and launcher start waits. A
# seed hands its items over before the game starts, so without this a strand's
# first mission opens beside the opening one. One condition here holds every
# launcher start, which is what the ordering needs, for three lines of the MAIN
# section instead of the thousand-odd bytes a condition on every launcher gate
# costs.
body = ["", ":APMARK", "script_name 'APMARK'", "", ":APMARK_LOOP", "wait 250",
        "if ", "  is_player_playing $player_char", "goto_if_false @APMARK_LOOP",
        "if ", "  $onmission == 0", "goto_if_false @APMARK_LOOP",
        "if ", f"  ${AN_OLD_FRIEND_PASSED} == 1", "goto_if_false @APMARK_LOOP"]
for strand in by_strand:
    body += [f"gosub @APMARK_{strand}"]
body += ["goto @APMARK_LOOP"]
for strand, missions in by_strand.items():
    body += strand_block(strand, missions)
    body += ["return"]

# Insert APMARK before :GEN1 and boot-start it next to @HOT, matching the other
# watcher threads.
anchor = next(i for i, ln in enumerate(lines) if ln == ":GEN1")
lines[anchor:anchor] = body
boot = next(i for i, ln in enumerate(lines) if ln == "start_new_script @HOT ")
lines[boot + 1:boot + 1] = ["start_new_script @APMARK "]

# Grow the reserved block to cover the new scratch globals. The anchor is the
# foundation's sizing line, which writes the highest reserved global, the finale
# active flag.
SIZING_LINE = f"${SIZING_GLOBAL} = 0"
# Found inside the foundation rather than anywhere in the script, because the top
# of the block is also a flag a mission writes, so the same line appears again in
# that mission's body. The foundation is the run of writes after the boot
# thread's own name, and the sizing line is the one there.
foundation_start = next(i for i, ln in enumerate(lines)
                        if ln == "script_name 'HOT'")
foundation_window = range(foundation_start, min(foundation_start + 40, len(lines)))
sizing = [i for i in foundation_window if lines[i] == SIZING_LINE]
# Said rather than raised: a reserved global added anywhere moves the top, the
# foundation then sizes a global this script does not name, and these writes
# would land on top of the ASI's. Zero hits and a duplicate both fail here.
assert len(sizing) == 1, (
    f"the foundation's sizing line {SIZING_LINE} appears {len(sizing)} times in "
    f"the foundation, so the reserved block no longer tops out where the marker "
    f"scratch starts; move SIZING_GLOBAL with scm.py's own highest reserved "
    f"global")
found = sizing[0]
lines[found + 1:found + 1] = [f"${highest_global} = 0"]

with open(DST, "wb") as handle:
    handle.write(nl.join(lines).encode("latin-1"))

print(f"managed {len(managed)} missions across {len(by_strand)} strands")
print(f"severed {severed_creates} vanilla marker reveals, {severed_starts} vanilla starts")
print(f"scratch globals ${HANDLE_BASE}..${highest_global}")
if unmanaged:
    print("UNMANAGED (kept vanilla marker):")
    for launcher, reason in unmanaged:
        print(f"  - {launcher}: {reason}")
