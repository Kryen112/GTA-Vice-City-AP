"""Second pass over the built decompile: make mission-giver markers AP-driven.

Each managed mission gets its own fresh marker handle at the vanilla coordinates
and sprite. A central APMARK watcher shows a mission's marker only while that
mission is the active (first-unpassed, in-order) one in its strand AND its unlock
gate holds, and starts the mission's launcher at that moment. Vanilla's own
marker reveals and launcher starts for these missions are severed, so nothing
appears on the map until the AP unlock lands. Marker coordinates are static
(each coord global is assigned once at init), so a fresh handle at those coords
reproduces the vanilla marker without depending on vanilla's reveal timing.
"""
from __future__ import annotations

import re
import sys

SRC, DST = sys.argv[1], sys.argv[2]
CLEO_OUT = sys.argv[3] if len(sys.argv) > 3 else None

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
    "Avery": [("SER1", [(9014, 1)]), ("SER3", [(9014, 2)]), ("SER2", [(9014, 3)])],
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
    "VercettiFinale": [("FIN1", [(9022, 1), (9016, 3), (268, 1), (273, 1), (1175, 7)]),
                       ("FIN2", [(9022, 2), (9016, 3), (9030, 1)])],
    # Venue strand gates also require the property bought (the venue purchase's
    # completion global) and owned (the ownership global its AP item drives),
    # so the beam and blip stay hidden and the launcher stays unstarted until
    # the progressive, the purchase, and the ownership item all exist.
    "Malibu": [("BANK1", [(9023, 1), (9337, 1), (9405, 1)]),
               ("BANK2", [(9023, 2), (9337, 1), (9405, 1)]),
               ("BANK3", [(9023, 3), (9337, 1), (9405, 1)]),
               ("BANK4", [(9023, 4), (9337, 1), (9405, 1)])],
    "FilmStudio": [("PORN1", [(9024, 1), (9334, 1), (9402, 1)]),
                   ("PORN2", [(9024, 2), (9334, 1), (9402, 1)]),
                   ("PORN3", [(9024, 3), (9334, 1), (9402, 1)]),
                   ("PORN4", [(9024, 4), (9334, 1), (9402, 1)])],
    "Printworks": [("COU1", [(9025, 1), (9332, 1), (9400, 1)]),
                   ("COU2", [(9025, 2), (9332, 1), (9400, 1)])],
    "KaufmanCabs": [("TWAR1", [(9026, 1), (9336, 1), (9404, 1)]),
                    ("TWAR2", [(9026, 2), (9336, 1), (9404, 1)]),
                    ("TWAR3", [(9026, 3), (9336, 1), (9404, 1)])],
}

# Fresh scratch globals, all above the ASI-written block (its top is the
# ownership globals, $9414). One handle, one started-flag, one shown-flag per
# managed mission.
HANDLE_BASE = 9420
STARTED_BASE = 9480
SHOWN_BASE = 9540
MARKER_SPRITE_DEFAULT = "34"  # generic mission-attempt sprite; overridden per giver

with open(SRC, "rb") as handle:
    raw = handle.read()
nl = "\r\n" if b"\r\n" in raw else "\n"
lines = raw.decode("latin-1").split(nl)

label_at: dict[str, int] = {}
for i, ln in enumerate(lines):
    if ln.startswith(":") and ln[1:] not in label_at:
        label_at[ln[1:]] = i

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
# they set ($9076.. and $9176..) are unchanged, so the ASI polls them identically.
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
stat_checks = ([(f"${1439 + n} == 1", 9176 + n) for n in range(35)]
               + [(f"${795 + n} == 1", 9211 + n) for n in range(36)]
               + [(f"$369 >= {10 * n}", 9282 + n) for n in range(1, 11)])
for idx, (cond, comp) in enumerate(stat_checks):
    cleo += ["if ", f"  {cond}", f"goto_if_false @AW_S{idx}", f"${comp} = 1", f":AW_S{idx}"]
# Activity + side events (APACT). Checkpoint Charlie ($607), the six Sunshine
# races (all of $1588..$1593), and 14 independent side-event win flags.
cleo += ["if ", "  $607 == 1", "goto_if_false @AW_RACES", "$9361 = 1", ":AW_RACES"]
for race_flag in range(1588, 1594):
    cleo += ["if ", f"  ${race_flag} == 1", "goto_if_false @AW_SIDE"]
cleo += ["$9362 = 1", ":AW_SIDE"]
side_events = [(1597, 9303), (1598, 9304), (55, 9305), (1584, 9306), (1585, 9307),
               (1586, 9308), (1587, 9309), (8241, 9310), (8485, 9311), (8156, 9312),
               (363, 9313), (364, 9314), (339, 9315), (351, 9316)]
for idx, (flag, comp) in enumerate(side_events):
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
        for global_index, count in m["gate"]:
            out += ["if ", f"  ${global_index} >= {count}", f"goto_if_false @APMARK_{launcher}_HIDE"]
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
# script-owned interior) or is on a mission, so a marker create or launcher start
# never runs during a cutscene or mission transition. The not-controllable half
# is the same flag all item application defers on; the on-mission half
# additionally keeps a launcher start out of an already-running mission.
body = ["", ":APMARK", "script_name 'APMARK'", "", ":APMARK_LOOP", "wait 250",
        "if ", "  is_player_playing $player_char", "goto_if_false @APMARK_LOOP",
        "if ", "  $onmission == 0", "goto_if_false @APMARK_LOOP"]
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
# foundation's sizing line, the highest ASI-written global (Skumole Shack's
# ownership global).
found = next(i for i, ln in enumerate(lines) if ln == "$9414 = 0")
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
