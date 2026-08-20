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

import re
import sys

SRC, DST = sys.argv[1], sys.argv[2]
CLEO_OUT = sys.argv[3] if len(sys.argv) > 3 else None

# A gate term meaning "any mainland crossing", mirroring build_scm.MAINLAND_ANY.
# Mainland Access and the four crossing items are alternatives, so a gate naming
# one of them alone would hold forever under the setting that never writes it.
MAINLAND_ANY = "any mainland crossing"
MAINLAND_UNLOCKS = [9030, 9032, 9033, 9034, 9035]

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
    "VercettiProtection": [("PRO1", [(9016, 1)]),
                           ("PRO2", [(9016, 2)]),
                           ("PRO3", [(9016, 3)])],
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
    "Malibu": [("BANK1", [(9023, 1), (9341, 1), (9418, 1)]),
               ("BANK2", [(9023, 2), (9341, 1), (9418, 1)]),
               ("BANK3", [(9023, 3), (9341, 1), (9418, 1)]),
               ("BANK4", [(9023, 4), (9341, 1), (9418, 1)])],
    "FilmStudio": [("PORN1", [(9024, 1), (9338, 1), (9415, 1)]),
                   ("PORN2", [(9024, 2), (9338, 1), (9415, 1)]),
                   ("PORN3", [(9024, 3), (9338, 1), (9415, 1)]),
                   ("PORN4", [(9024, 4), (9338, 1), (9415, 1)])],
    "Printworks": [("COU1", [(9025, 1), (9336, 1), (9413, 1)]),
                   ("COU2", [(9025, 2), (9336, 1), (9413, 1)])],
    "KaufmanCabs": [("TWAR1", [(9026, 1), (9340, 1), (9417, 1)]),
                    ("TWAR2", [(9026, 2), (9340, 1), (9417, 1)]),
                    ("TWAR3", [(9026, 3), (9340, 1), (9417, 1)])],
}

# Fresh scratch globals, all above the ASI-written block (its top is the highest
# district content unlock, $9514). One handle, one started-flag, one shown-flag
# per managed mission.
HANDLE_BASE = 9515
STARTED_BASE = 9575
SHOWN_BASE = 9635
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
        counts = [gate[0][1] for _, gate in missions]
        assert counts == list(range(1, len(counts) + 1)), (
            f"play order: strand {strand} gate counts {counts} are not 1..N in "
            f"list order")
        numbers = [launched_mission(launcher) for launcher, _ in missions]
        assert numbers == sorted(numbers), (
            f"play order: strand {strand} launches missions {numbers}, which is "
            f"not the vanilla order")


check_play_order()

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

# --- Relocate the two bulky completion watchers to CLEO ------------------------
# APPKG (100 package checks) and APSTAT (rampage/stunt/taxi checks) are the
# heaviest MAIN-section threads and poll only numeric globals, so they port to a
# CLEO script unchanged. Moving them out of the MAIN script buffer makes room for
# APMARK without overflowing VC's fixed main-script buffer. The completion globals
# they set ($9080.. and $9180..) are unchanged, so the ASI polls them identically.
def remove_thread(label, loop_goto):
    start = next((i for i, ln in enumerate(lines) if ln == f":{label}"), None)
    assert start is not None, f"relocate: :{label} not found"
    end = next(i for i in range(start, len(lines)) if lines[i] == loop_goto)
    del lines[start:end + 1]


remove_thread("APPKG", "goto @APPKG_LOOP")
remove_thread("APSTAT", "goto @APSTAT_LOOP")
remove_thread("APACT", "goto @APACT_LOOP")
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
if CLEO_OUT:
    with open(CLEO_OUT, "wb") as handle:
        handle.write(nl.join(cleo).encode("latin-1"))

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
# foundation's sizing line, the highest ASI-written global (the top district
# content unlock).
found = next(i for i, ln in enumerate(lines) if ln == "$9514 = 0")
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
