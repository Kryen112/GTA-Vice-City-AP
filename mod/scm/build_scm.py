"""Apply AP edits to a clean VC decompile: foundation, per-mission gate +
completion write + reward suppression, and the area watcher that opens the
mainland and the two Starfish Island gates on their AP items.

Config per mission is just (launcher_label, gate_conditions, completion_global).
The launcher's guard flag, gate-block label, and loop-back label are derived
from its uniform structure, and the cash/banner reward is auto-detected near the
mission's passed-flag assignment. Every anchor is asserted, so a bad match fails
loudly. Reads SRC, writes DST; line endings preserved.
"""
import math
import re
import sys

SRC, DST = sys.argv[1], sys.argv[2]

# (launcher, [(unlock_global, count), ...], completion_global). Gate list empty
# = free mission. Order mirrors the strands in the spec. The first gate of a
# gated mission is always its own strand's progressive unlock, and those unlocks
# occupy this block, which check_play_order uses to group the table by strand.
UNLOCK_FIRST, UNLOCK_LAST = 9010, 9029

# A gate term meaning "any mainland crossing", written in place of a
# (global, count) pair. Mainland Access and the four crossing items are
# alternatives: split_mainland_access decides which the seed puts in the pool,
# and the other unlock global is never written, so a gate naming one of them
# alone would hold forever under the other setting. The emitters expand this to
# an if-or over all five. MAINLAND_UNLOCKS mirrors the area block in scm.py.
MAINLAND_ANY = "any mainland crossing"
MAINLAND_UNLOCKS = [9030, 9032, 9033, 9034, 9035]

# A gate term meaning "this vanilla mission has passed", written as the launcher
# whose guard flag records the pass. Mirrors data.IN_GAME_PASSED_PREREQUISITES,
# which is where the world says which strand waits on which mission. The flag is
# read out of the source at build time, so no vanilla flag number is copied by
# hand, and reading the vanilla flag does not depend on that launcher's own
# thread still running to have noticed the pass. Only a mission gate understands
# the term: gate_term is its one emitter, so it belongs in MISSIONS here and in
# add_markers.py STRANDS, and nowhere else (ACTIVITIES unpacks every term as a
# global and a count).
MISSION_PASSED = "mission passed"
# Each passed term's flag, filled by resolve_passed_flags before any gate is
# written. Spelled the same way in add_markers.py, since the two tables are
# mirrors and a reader compares them line by line.
PASSED_FLAGS = {}


def mission_passed(launcher):
    """The gate term for the mission `launcher` starts having been passed."""
    return (MISSION_PASSED, launcher)


# The fifteen property purchases in purchase order: (buy cutscene, the purchase
# completion global written at that cutscene). Each purchase is an AP location,
# and the property itself is an AP item whose ownership global sits at the same
# offset into its own block, so both terms of "bought AND owned" come from a
# property's position here.
PURCHASES = [
    ("BUYPRO1", 9336), ("CARBUY1", 9337), ("BUYPRO2", 9338), ("ICECUT", 9339),
    ("TAXCUT", 9340), ("BUYPRO3", 9341), ("BOATBY", 9342), ("BUYPRO4", 9343),
    ("BUYPRO5", 9344), ("LNKVBUY", 9345), ("HYCOBUY", 9346), ("OCHEBUY", 9347),
    ("WASHBUY", 9348), ("VCPTBUY", 9349), ("SKUMBUY", 9350),
]

# The base of the ownership block, matching scm.py: one global per purchasable
# property, in the order above, written by the ASI when the ownership item
# arrives (or all stamped to 1 when the properties class is off, the vanilla
# collapse). Every property grant reads bought AND owned.
#
# This and the first completion global above are the only two property globals
# written down. Everything that gates on a property, the venue mission gates,
# the two activity gates, the safehouse and business save threads and the Pole
# Position and Sunshine Autos recognitions, names the buy cutscene and derives
# the number, so no gate can end up on another property's item and no gate can
# be missed when a block moves. The world test
# test_property_ownership_globals_match_the_hand_written_mirrors pins all
# fifteen ownership globals against the world's own layout, which is what
# catches a location added anywhere earlier shifting the block.
OWNERSHIP_BASE = 9555


def purchase_index(buy_thread):
    labels = [label for label, _completion in PURCHASES]
    assert buy_thread in labels, f"{buy_thread} is not a property purchase"
    return labels.index(buy_thread)


def bought(buy_thread):
    """The gate term for the purchase having been made."""
    return (PURCHASES[purchase_index(buy_thread)][1], 1)


def ownership_global(buy_thread):
    return OWNERSHIP_BASE + purchase_index(buy_thread)


def owned(buy_thread):
    """The gate term for the property's ownership item having arrived."""
    return (ownership_global(buy_thread), 1)


OWNERSHIP_SUNSHINE = ownership_global("CARBUY1")
OWNERSHIP_POLE_POSITION = ownership_global("BUYPRO4")

MISSIONS = [
    # Rosenberg (9010)
    ("HOT", [], 9036), ("LAW1", [(9010, 1)], 9037), ("LAW2", [(9010, 2)], 9038),
    ("LAW3", [(9010, 3)], 9039), ("LAW4", [(9010, 4)], 9040),
    # Cortez (9011)
    ("GEN1", [(9011, 1)], 9041), ("GEN2", [(9011, 2)], 9042),
    ("GEN3", [(9011, 3)], 9043), ("GEN4", [(9011, 4)], 9044),
    ("GEN5", [(9011, 5)], 9045),
    # Diaz (9012). Rub Out additionally needs Lance rescued in Death Row.
    ("BAR1", [(9012, 1)], 9046), ("BAR2", [(9012, 2)], 9047),
    ("BAR3", [(9012, 3)], 9048), ("BAR4", [(9012, 4)], 9049),
    ("BAR5", [(9012, 5), (9013, 1)], 9050),
    # Death Row (9013)
    ("KEN1", [(9013, 1)], 9051),
    # Avery (9014): Four Iron, Demolition Man, Two Bit Hit. The mission threads
    # are named out of order (SERG1, SERG3, SERG2), the launchers are not.
    ("SER1", [(9014, 1)], 9052), ("SER2", [(9014, 2)], 9053), ("SER3", [(9014, 3)], 9054),
    # Phil Cassidy (9015)
    ("PHI1", [(9015, 1)], 9055), ("PHI2", [(9015, 2)], 9056),
    # Vercetti Protection (9016). The strand gives from the estate, so every
    # mission of it also waits on Rub Out having passed and handed the mansion
    # over. That term subsumes the strand's Diaz unlock count: Rub Out cannot
    # pass before its own gate opens on $9012 >= 5, so the count is not repeated
    # here.
    ("PRO1", [(9016, 1), mission_passed("BAR5")], 9057),
    ("PRO2", [(9016, 2), mission_passed("BAR5")], 9058),
    ("PRO3", [(9016, 3), mission_passed("BAR5")], 9059),
    # Big Mitch Baker (9017)
    ("BIK1", [(9017, 1)], 9060), ("BIK2", [(9017, 2)], 9061), ("BIK3", [(9017, 3)], 9062),
    # Umberto Robina (9018)
    ("CUB1", [(9018, 1)], 9063), ("CUB2", [(9018, 2)], 9064),
    ("CUB3", [(9018, 3)], 9065), ("CUB4", [(9018, 4)], 9066),
    # Auntie Poulet (9019)
    ("HAT1", [(9019, 1)], 9067), ("HAT2", [(9019, 2)], 9068), ("HAT3", [(9019, 3)], 9069),
    # Love Fist (9020)
    ("ROC1", [(9020, 1)], 9070), ("ROC2", [(9020, 2)], 9071), ("ROC3", [(9020, 3)], 9072),
    # Mr. Black (9021)
    ("ASSIN_1", [(9021, 1)], 9073), ("ASSIN_2", [(9021, 2)], 9074), ("ASSIN_3", [(9021, 3)], 9075),
    ("ASSIN_4", [(9021, 4)], 9076), ("ASSIN_5", [(9021, 5)], 9077),
    # Vercetti Finale (9022, after the protection strand 9016>=3). Cap the
    # Collector keeps its vanilla asset prerequisite, read from the vanilla
    # globals: Hit the Courier passed ($273), Cop Land passed ($268), and the
    # owned-asset count $1175 at seven or more (the CELL controller required
    # $1175 > 6). The last mission also mirrors logic's mainland requirement:
    # its launcher only activates once Cap the Collector passes on the mainland,
    # so the condition is already true whenever it can fire, and it is written as
    # MAINLAND_ANY so it stays true whichever mainland item the seed hands out.
    ("FIN1", [(9022, 1), (9016, 3), (268, 1), (273, 1), (1175, 7)], 9078),
    ("FIN2", [(9022, 2), (9016, 3), MAINLAND_ANY], 9079),
    # Venue strands also require their property bought, read from the purchase's
    # completion global (set at the buy cutscene, save-persisted), and owned,
    # read from the ownership global its AP item drives. Both terms name the buy
    # cutscene, so a venue cannot end up gated on another venue's property.
    # Malibu Club (9023)
    ("BANK1", [(9023, 1), bought("BUYPRO3"), owned("BUYPRO3")], 9351),
    ("BANK2", [(9023, 2), bought("BUYPRO3"), owned("BUYPRO3")], 9352),
    ("BANK3", [(9023, 3), bought("BUYPRO3"), owned("BUYPRO3")], 9353),
    ("BANK4", [(9023, 4), bought("BUYPRO3"), owned("BUYPRO3")], 9354),
    # Film Studio (9024)
    ("PORN1", [(9024, 1), bought("BUYPRO2"), owned("BUYPRO2")], 9355),
    ("PORN2", [(9024, 2), bought("BUYPRO2"), owned("BUYPRO2")], 9356),
    ("PORN3", [(9024, 3), bought("BUYPRO2"), owned("BUYPRO2")], 9357),
    ("PORN4", [(9024, 4), bought("BUYPRO2"), owned("BUYPRO2")], 9358),
    # Printworks (9025)
    ("COU1", [(9025, 1), bought("BUYPRO1"), owned("BUYPRO1")], 9359),
    ("COU2", [(9025, 2), bought("BUYPRO1"), owned("BUYPRO1")], 9360),
    # Kaufman Cabs (9026)
    ("TWAR1", [(9026, 1), bought("TAXCUT"), owned("TAXCUT")], 9361),
    ("TWAR2", [(9026, 2), bought("TAXCUT"), owned("TAXCUT")], 9362),
    ("TWAR3", [(9026, 3), bought("TAXCUT"), owned("TAXCUT")], 9363),
    # Cherry Popper (9027; the buy cutscene is also what starts its launcher).
    # Boatyard (9028) and Sunshine Autos (9029) are activity launchers with no
    # passed-flag guard, wired bespoke in ACTIVITIES; their threads too start
    # only at the buy cutscene, which carries the purchase condition.
    ("ICE1", [(9027, 1), bought("ICECUT"), owned("ICECUT")], 9364),
]

with open(SRC, "rb") as handle:
    raw = handle.read()
nl = "\r\n" if b"\r\n" in raw else "\n"
lines = raw.decode("latin-1").split(nl)
# The source as it arrived, for the guards that ask what the GAME writes rather
# than what this script has written since. Checking those against `lines` would
# let an earlier transform's own output answer for the decompile.
SOURCE_LINES = frozenset(lines)
edits = []

# The game's own completion percentage is these lines over set_progress_total,
# and the stats menu prints it, so a suppression that swallows one costs the
# player a percentage point with nothing to notice it by. Two things can do that:
# deleting the line, which the count below catches, and wrapping it in one of the
# guards this script inserts, which leaves the count alone and still stops it
# running. Every guarded span records its skip label as it goes in, so the check
# before the write can say exactly what each guard covers.
PROGRESS_LINE = "player_made_progress 1"
source_progress_points = sum(1 for line in lines if line == PROGRESS_LINE)
guard_labels = []

# What the game itself says the points add up to, so a PROGRESS_LINE that stops
# matching (a decompile spelling it differently, or a step other than one) reads
# as zero points and fails here rather than leaving both checks below passing
# over nothing.
_progress_totals = [line for line in lines if line.startswith("set_progress_total ")]
assert len(_progress_totals) == 1, \
    f"expected one set_progress_total, found {len(_progress_totals)}"
declared_progress_total = int(_progress_totals[0].split()[1])
assert source_progress_points == declared_progress_total, (
    f"the decompile has {source_progress_points} completion points against a "
    f"declared total of {declared_progress_total}; the percentage the stats menu "
    "shows is not these lines, so the checks before the write mean nothing")


def insert_after(anchor, new, description):
    hits = [i for i, ln in enumerate(lines) if ln == anchor]
    assert len(hits) == 1, f"{description}: anchor {anchor!r} matched {len(hits)}"
    lines[hits[0] + 1:hits[0] + 1] = new
    edits.append(description)


def insert_before(anchor, new, description):
    hits = [i for i, ln in enumerate(lines) if ln == anchor]
    assert len(hits) == 1, f"{description}: anchor {anchor!r} matched {len(hits)}"
    lines[hits[0]:hits[0]] = new
    edits.append(description)


skipped = []


class NonStandard(Exception):
    pass


def _first(indices):
    for j in indices:
        return j
    return None


def derive(launcher):
    # Guard-gate launcher: guard `if $flag == 1 / goto @gateblock` (done path
    # ends in terminate), then a gate block whose marker checks share a loop-back
    # label. Covers marker launchers and payphone launchers alike.
    starts = [i for i, ln in enumerate(lines) if ln == f":{launcher}"]
    if len(starts) != 1:
        raise NonStandard(f"label matched {len(starts)}")
    i = starts[0]
    # Search only within this launcher (up to its own mission launch or the next
    # thread) so a short activity launcher cannot borrow the next thread's guard.
    end = _first(j for j in range(i + 2, len(lines))
                 if lines[j].startswith("load_and_launch_mission_internal")
                 or lines[j].startswith("script_name '"))
    end = end if end is not None else i + 40
    guard_idx = _first(j for j in range(i, end) if re.match(r"^  \$\S+ == 1$", lines[j]))
    if guard_idx is None or not lines[guard_idx + 1].startswith("goto_if_false @"):
        raise NonStandard("no standard guard")
    flag = lines[guard_idx].strip().split(" ")[0]
    gate_block = lines[guard_idx + 1].split("@", 1)[1]
    gb = _first(j for j in range(guard_idx, len(lines)) if lines[j] == f":{gate_block}")
    if gb is None:
        raise NonStandard("gate block label missing")
    marker = _first(j for j in range(gb, gb + 40) if lines[j].strip() == "is_player_playing $player_char")
    if marker is None or not lines[marker + 1].startswith("goto_if_false @"):
        raise NonStandard("no marker gate")
    loopback = lines[marker + 1].split("@", 1)[1]
    return flag, gate_block, loopback


def gate_term(term, loopback):
    # One gate condition as script lines. MAINLAND_ANY becomes an if-or over
    # every mainland unlock, so the gate holds under either setting; a passed
    # term becomes the named launcher's own vanilla guard flag, read from the
    # source; everything else is a single global at a count.
    if term == MAINLAND_ANY:
        return ["if or", *[f"  ${unlock} >= 1" for unlock in MAINLAND_UNLOCKS],
                f"goto_if_false @{loopback}"]
    if term[0] == MISSION_PASSED:
        return ["if ", f"  {PASSED_FLAGS[term[1]]} == 1",
                f"goto_if_false @{loopback}"]
    global_index, count = term
    return ["if ", f"  ${global_index} >= {count}", f"goto_if_false @{loopback}"]


def resolve_passed_flags():
    # Every passed term's flag, read from its launcher's own guard before a
    # single gate is written. Resolved here and not inside gate_term because the
    # wiring loop turns a NonStandard into a printed skip line, so a lazy read
    # could leave a mission carrying its completion write and no gate at all,
    # reported only in that printout.
    #
    # Each flag must also be written at exactly one site AND that write must sit
    # inside the block of the mission the launcher launches, both halves of the
    # guard add_markers.check_an_old_friend_flag applies to $222 and for the same
    # reason. A gate on a flag nothing sets holds its content forever, and one on
    # a flag written from somewhere other than the mission's own pass records
    # something else; either way the strand hides while logic calls it reachable.
    spans = mission_blocks()
    for _launcher, gate_conditions, _completion in MISSIONS:
        for term in gate_conditions:
            if term == MAINLAND_ANY or term[0] != MISSION_PASSED:
                continue
            if term[1] in PASSED_FLAGS:
                continue
            flag, _gate_block, _loopback = derive(term[1])
            write = f"{flag} = 1"
            sites = [i for i, ln in enumerate(lines) if ln == write]
            assert len(sites) == 1, (
                f"passed gate: {write} appears at {len(sites)} sites, not one, "
                f"so the gate cannot name the write that records the pass")
            start, end = spans[launcher_mission_number(term[1])]
            assert start < sites[0] < end, (
                f"passed gate: {write} is at line {sites[0] + 1}, outside the "
                f"block of the mission {term[1]} launches")
            PASSED_FLAGS[term[1]] = flag
    print(f"resolved passed gate flags for {len(PASSED_FLAGS)} launchers")


def check_gate_mainland_terms():
    # A gate naming one mainland unlock directly would hold forever under the
    # setting that never writes it, so every mainland term must be MAINLAND_ANY.
    for launcher, gate_conditions, _completion in MISSIONS:
        for term in gate_conditions:
            if term == MAINLAND_ANY or term[0] == MISSION_PASSED:
                continue
            assert term[0] not in MAINLAND_UNLOCKS, (
                f"gate {launcher} names mainland unlock ${term[0]} directly; "
                f"use MAINLAND_ANY so both settings satisfy it")
    print(f"verified mainland gate terms across {len(MISSIONS)} launchers")


def wire(launcher, gate_conditions, completion_global):
    flag, gate_block, loopback = derive(launcher)
    guard = f"  {flag} == 1"
    goto = f"goto_if_false @{gate_block}"
    hits = [i for i in range(len(lines) - 1) if lines[i] == guard and lines[i + 1] == goto]
    if len(hits) != 1:
        raise NonStandard(f"guard window matched {len(hits)}")
    # The done path (guard true) ends in terminate within a few lines; insert the
    # completion write right before it.
    term = _first(j for j in range(hits[0] + 2, hits[0] + 7) if lines[j].strip() == "terminate_this_script")
    if term is None:
        raise NonStandard("no terminate in done path")
    if lines.count(f":{gate_block}") != 1:
        raise NonStandard("gate block not unique")
    lines[term:term] = [f"${completion_global} = 1"]
    if gate_conditions:
        block = []
        for term in gate_conditions:
            block += gate_term(term, loopback)
        insert_after(f":{gate_block}", block, f"gate {launcher} {gate_conditions}")
    edits.append(f"completion {launcher} ${completion_global}")


# The three bridge roadblocks the mainland flip deletes, in the order their
# districts read from north to south, with the unlock global of the crossing
# item that opens each. The district names come from the game's own navig.zon:
# every roadblock stands on the start-island side of its crossing.
# (crossing item, roadblock object handle, unlock global.)
MAINLAND_ROADBLOCKS = [
    ("Prawn Island Bridge", 1781, 9032),
    ("Leaf Links Bridge", 1782, 9033),
    ("Ocean Beach Bridge", 1783, 9034),
]
MAINLAND_ACCESS_UNLOCK = 9030
STARFISH_ACCESS_UNLOCK = 9031
STARFISH_CAUSEWAY_UNLOCK = 9035
ROAD_SWITCHES = ("switch_ped_roads_on ", "switch_roads_on ")


def relocate_mainland_open():
    # Extracts Phnom Penh's mainland-open routine and splits it three ways: one
    # piece per bridge roadblock (its delete plus the road and ped switches
    # directly above it, which open the span it stands on), the Starfish west
    # gate piece (the $1779 swap and its own switches), and the shared
    # remainder. The shared part is everything not tied to one crossing: the
    # vanilla flag $847, the mainland hospital and police restarts, the
    # hurricane stop, the Washington pier door and the announcement.
    anchor = [i for i, ln in enumerate(lines) if ln == "$passed_COK2_Phnom_Penh_86 = 1"]
    assert len(anchor) == 1, f"mainland: passed anchor matched {len(anchor)}"
    start = next(j for j in range(anchor[0], anchor[0] + 20) if lines[j] == "$847 = 1")
    end = next(j for j in range(start, start + 40) if lines[j] == "play_announcement 1")
    block = lines[start:end + 1]
    assert 20 <= len(block) <= 32 and "delete_object $1781" in block, (
        f"mainland: extracted block looks wrong ({len(block)} lines)")
    del lines[start:end + 1]
    west_start = block.index("delete_object $1779") - 2
    west_gate = block[west_start:west_start + 5]
    assert (west_gate[0].startswith("switch_ped_roads_on -787.8")
            and west_gate[4] == "dont_remove_object $1779"), (
        f"mainland: west-gate piece looks wrong ({west_gate})")
    shared = block[:west_start] + block[west_start + 5:]
    pieces = {}
    for _name, handle, _unlock in MAINLAND_ROADBLOCKS:
        delete = f"delete_object ${handle}"
        assert shared.count(delete) == 1, f"mainland: {delete} matched once expected"
        last = shared.index(delete)
        first = last
        while first > 0 and shared[first - 1].startswith(ROAD_SWITCHES):
            first -= 1
        assert first < last, f"mainland: {delete} has no road switches above it"
        pieces[handle] = shared[first:last + 1]
        del shared[first:last + 1]
    assert shared[0] == "$847 = 1" and shared[-1] == "play_announcement 1", (
        f"mainland: shared piece looks wrong ({shared[:2]} .. {shared[-1:]})")
    assert "delete_object $1784" in shared, "mainland: pier door left a crossing"
    assert not any(ln.startswith(ROAD_SWITCHES) for ln in shared), (
        "mainland: a road switch stayed in the shared piece")
    edits.append(f"relocated mainland-open ({len(shared)} shared + "
                 f"{len(MAINLAND_ROADBLOCKS)} crossings + {len(west_gate)} west gate)")
    return shared, pieces, west_gate


def sever_starfish_east_open():
    # Extracts the east-gate opening from the CELL phone thread's Diaz intro
    # (the $1780 swap and its bridge-span road switches), which vanilla runs
    # once Guardian Angels passes. The phone call and its $1157 once-guard stay
    # in CELL; the gate moves to the watcher so it opens on the item, and a
    # Rub Out passed before Guardian Angels can no longer suppress it.
    anchor = [i for i, ln in enumerate(lines)
              if ln.startswith("create_object_no_offset $1780 = init_object #COMGATE2OPEN at -183.824")]
    assert len(anchor) == 1, f"starfish: east-gate anchor matched {len(anchor)}"
    start = anchor[0] - 3
    block = lines[start:start + 5]
    assert block[0].startswith("switch_ped_roads_on -230.0") \
        and block[2] == "delete_object $1780" \
        and block[4] == "dont_remove_object $1780", \
        f"starfish: east-gate piece looks wrong ({block})"
    del lines[start:start + 5]
    edits.append("severed starfish east-gate open from CELL")
    return block


# Property purchases: each buy mission-let is a post-purchase cutscene, so mark
# its completion at the mission-let start. Order matches the apworld order.
def add_purchase_completions():
    for label, completion in PURCHASES:
        insert_after(f"script_name '{label}'", [f"${completion} = 1"], f"purchase {label} ${completion}")


# Safehouse save threads: (save thread, the buy cutscene that starts it, garage
# grant lines moved out of that cutscene). Each SAVEn thread is started only by
# its buy cutscene and persists inside saves, so gating its body on the ownership
# global defers the save pickup until the property is bought and owned in either
# order, and the garage changes ride the same gate.
#
# The buy cutscene also announces the save three ways the gate was not holding:
# it swaps the property's radar blip to the save-house icon, and it prints that
# the player can save here and, where the house has one, store cars in the
# garage. All three move behind the gate, so the icon appears and the texts print
# when the save actually becomes usable. The cutscene keeps its camera work, its
# money, and the owned-property stat.
#
# The cutscene names here are asserted rather than trusted: the save thread a
# cutscene starts is what pairs a house with its ownership global, and SAVE4 and
# SAVE5 pair in the opposite order to that global order, so a silent mismatch
# would gate two houses on each other's items.
SAFEHOUSES = [
    # El Swanko Casa. Its cutscene is the one not named for its property.
    ("SAVE1", "BUYPRO5", ["change_garage_type $663 change_to_type 16"]),
    # Links View Apartment
    ("SAVE2", "LNKVBUY", ["change_garage_type $655 change_to_type 26"]),
    # Hyman Condo
    ("SAVE3", "HYCOBUY", ["change_garage_type $667 change_to_type 17",
                          "change_garage_type $668 change_to_type 18",
                          "change_garage_type $669 change_to_type 24"]),
    # 1102 Washington Street, the higher global of the inverted pair
    ("SAVE4", "WASHBUY", []),
    # Ocean Heights Apartment, the lower one
    ("SAVE5", "OCHEBUY", ["change_garage_type $659 change_to_type 25"]),
    # Vice Point
    ("SAVE6", "VCPTBUY", []),
    # Skumole Shack
    ("SAVE7", "SKUMBUY", []),
]
# The blip a buy cutscene swaps in for a bought safehouse: the save-house icon at
# the property's own coordinates. The vanilla script creates it on two paths, the
# ordinary cutscene and the not-playing bail, both naming one handle.
SAVE_HOUSE_BLIP = re.compile(
    r"^add_short_range_sprite_blip_for_contact_point (\$\d+) = "
    r"create_asset_radar_marker_with_icon 19 at ")
# The cutscene's own announcements: that the player can save here, and for a
# house with a garage that they can store cars in it. Read rather than named,
# since Hyman Condo's is plural for its three garages.
BUY_ANNOUNCEMENT = re.compile(r"^print_now 'BUY\w+' time 3000 1$")


def buy_cutscene_span(save_thread, buy_thread):
    """The line range of the cutscene that starts this save thread.

    A save thread is started only by the purchase that grants it, from every path
    that purchase can take, so which cutscene starts it is what pairs a property
    with its ownership global. Read from the source rather than tabled, and the
    expected name asserted, so the pairing cannot drift.
    """
    starts = [i for i, ln in enumerate(lines) if ln == f"start_new_script @{save_thread} "]
    assert starts, f"property save {save_thread}: nothing starts it"
    names = [i for i, ln in enumerate(lines) if ln.startswith("script_name '")]
    cutscenes = [i for i in names if lines[i] == f"script_name '{buy_thread}'"]
    assert len(cutscenes) == 1, (
        f"property save {save_thread}: script_name {buy_thread!r} "
        f"matched {len(cutscenes)}")
    owners = {max(i for i in names if i < start) for start in starts}
    assert owners == set(cutscenes), (
        f"property save {save_thread}: started by "
        f"{sorted(lines[owner] for owner in owners)}, not {buy_thread} alone")
    owner = cutscenes[0]
    return owner, min([i for i in names if i > owner] + [len(lines)])


def safehouse_cutscene(save_thread, buy_thread, garage_lines):
    # What the buy cutscene gives this safehouse: the save-house blip handle and
    # the announcements to move behind the gate.
    owner, end = buy_cutscene_span(save_thread, buy_thread)
    handles = {match.group(1) for match in
               (SAVE_HOUSE_BLIP.match(lines[i]) for i in range(owner, end)) if match}
    assert len(handles) == 1, (
        f"safehouse {save_thread}: {buy_thread} names blips {sorted(handles)}")
    sites = [i for i in range(owner, end) if BUY_ANNOUNCEMENT.match(lines[i])]
    # A house announces its garage exactly when it has one to change, so the two
    # tables prove each other: a mistabled garage line shows up as a text with no
    # grant or a grant with no text.
    assert len(sites) == (2 if garage_lines else 1), (
        f"safehouse {save_thread}: {buy_thread} announces "
        f"{[lines[i] for i in sites]} against {len(garage_lines)} garage grants")
    return handles.pop(), sites


# Business save threads: (save thread, the buy cutscene that starts it). Every
# business a player buys carries a save point of its own, and like a safehouse's
# it is created by a thread that only its purchase starts, so the same gate
# defers it until the property is owned.
#
# A business needs less of that gate than a safehouse does: its save is the
# pickup alone, which the engine draws on the radar itself, so there is no save
# icon to hide, and its cutscene announces nothing about saving. So this is the
# wait and nothing else. The asset icon the purchase puts on the radar is a
# different thing and stays at the purchase, like the rest of what a purchase
# opens up.
#
# What a business purchase opens up, and keeps opening before the item arrives:
# the Film Studio's three gates, the Cherry Popper and Kaufman Cabs doors, the
# Boatyard doors, Sunshine Autos' five garages. All passage into a property the
# player paid for, so all left alone. The safehouse gate holds a garage, which
# looks like the same thing and is not: that garage is storage the save point
# comes with, one of the three things its cutscene announces, so it waits with
# the save rather than with the front door.
#
# For the Film Studio the gates are a solvability matter besides. Two hidden
# packages sit inside its walls and no access rule gives them an ownership term,
# so holding the gates would put two locations behind an item the fill never
# required for them.
#
# PSAVE1 and PSAVE2 are absent on purpose: the Ocean View Hotel comes with the
# game and the mansion arrives with Rub Out, so neither is bought and neither has
# an ownership item to wait for. check_property_saves proves the split.
BUSINESS_SAVES = [
    ("PSAVE8", "BUYPRO1"),    # Printworks
    ("PSAVE3", "CARBUY1"),    # Sunshine Autos
    ("PSAVE9", "BUYPRO2"),    # Film Studio
    ("PSAVE7", "ICECUT"),     # Cherry Popper
    ("PSAVE4", "TAXCUT"),     # Kaufman Cabs
    ("PSAVE10", "BUYPRO3"),   # Malibu Club
    ("PSAVE6", "BOATBY"),     # Boatyard
    ("PSAVE5", "BUYPRO4"),    # Pole Position
]


def check_property_saves():
    # Every thread named PSAVEn, split by whether a property purchase starts it.
    # The ones a purchase starts are exactly the ones that must wait for an
    # ownership item, so a save added to a property, or one tabled against the
    # wrong purchase, fails here rather than granting a save nobody bought. The
    # safehouses' SAVEn threads are outside this and prove themselves the same
    # way, one at a time, in safehouse_cutscene.
    purchases = {label for label, _completion in PURCHASES}
    names = [i for i, ln in enumerate(lines) if ln.startswith("script_name '")]
    bought = set()
    for index in names:
        thread = lines[index].split("'")[1]
        if not thread.startswith("PSAVE"):
            continue
        starts = [i for i, ln in enumerate(lines)
                  if ln == f"start_new_script @{thread} "]
        starters = {lines[max(i for i in names if i < start)].split("'")[1]
                    for start in starts}
        if starters & purchases:
            assert starters <= purchases, (
                f"property save {thread}: started by {sorted(starters)}, "
                f"which is a purchase and something else")
            bought.add(thread)
    tabled = {save_thread for save_thread, _buy in BUSINESS_SAVES}
    assert bought == tabled, (
        f"property saves a purchase starts are {sorted(bought)}, "
        f"the table holds {sorted(tabled)}")
    # Which cutscene starts each one, so the pairing that picks the ownership
    # global is proved row by row and not only as a set.
    for save_thread, buy_thread in BUSINESS_SAVES:
        buy_cutscene_span(save_thread, buy_thread)
    print(f"verified {len(tabled)} business saves against the purchase table")


def defer_business_saves():
    # The ownership global comes from the cutscene column, which check_property_saves
    # proves against the script before this runs.
    for save_thread, buy_thread in BUSINESS_SAVES:
        ownership = ownership_global(buy_thread)
        gate = [f":AP{save_thread}", "wait 250",
                "if ", f"  ${ownership} >= 1", f"goto_if_false @AP{save_thread}"]
        insert_after(f"script_name '{save_thread}'", gate,
                     f"business save {save_thread} ownership ${ownership}")


def defer_safehouse_grants():
    for save_thread, buy_thread, garage_lines in SAFEHOUSES:
        ownership = ownership_global(buy_thread)
        blip, sites = safehouse_cutscene(save_thread, buy_thread, garage_lines)
        # The announcements read the same in every cutscene, so they move by
        # position, highest first; the garage grants each name their own garage,
        # so those move by text, and after the positions have been used.
        announcements = [lines[site] for site in sites]
        for site in sorted(sites, reverse=True):
            del lines[site]
        for grant in garage_lines:
            hits = [i for i, ln in enumerate(lines) if ln == grant]
            assert len(hits) == 1, f"safehouse {save_thread}: {grant!r} matched {len(hits)}"
            del lines[hits[0]]
        # The announcements keep the cutscene's own spacing between them, so two
        # texts still read one after the other rather than the second replacing
        # the first. The gate's open path runs once, then falls into the vanilla
        # body, so they print once.
        told = []
        for announcement in announcements:
            if told:
                told.append("wait 3000")
            told.append(announcement)
        # The hide sits above the wait, so it runs on the thread's first slice
        # rather than a quarter second in, and inside the loop, so a save written
        # while the gate held comes back hidden too.
        gate = [f":AP{save_thread}",
                f"change_blip_display {blip} display 0",
                "wait 250",
                "if ", f"  ${ownership} >= 1", f"goto_if_false @AP{save_thread}",
                f"change_blip_display {blip} display 2",
                *garage_lines,
                *told]
        insert_after(f"script_name '{save_thread}'", gate,
                     f"safehouse {save_thread} ownership ${ownership} blip {blip}, "
                     f"{len(announcements)} announcements moved")


def gate_pole_position_completion():
    # The Pole Position asset completes on the back-room spend ($1086 > 299,
    # once), inside the strip-club interior thread. The recognition waits for
    # the property to be owned; the club itself stays open vanilla-style, and
    # a spend made before ownership counts on the next club exit after it.
    anchor = [i for i, ln in enumerate(lines)
              if ln == "  $1086 > 299" and lines[i + 1] == "  $1096 == 0"]
    assert len(anchor) == 1, f"pole position: spend guard matched {len(anchor)}"
    lines[anchor[0] + 2:anchor[0] + 2] = [f"  ${OWNERSHIP_POLE_POSITION} >= 1"]
    edits.append(f"pole position completion owned ${OWNERSHIP_POLE_POSITION}")


# The four import garage lists, Sunshine Autos' mission strand. Each list
# wants six vehicles ($1105 counts them) and its own thread recognizes the
# fill, then starts the next list's thread and terminates itself, so vanilla
# already forces the order the progressives impose. The Sunshine Autos asset
# is the FIRST list: $1175 += 1 and $628 = 1 sit in IMPORT1's recognition
# block, and lists two through four only raise the daily take by 2500 each.
# (thread name, unlock count, completion global.)
SUNSHINE_IMPORT_LISTS = [
    ("IMPORT1", 1, 9366), ("IMPORT2", 2, 9367),
    ("IMPORT3", 3, 9368), ("IMPORT4", 4, 9369),
]
SUNSHINE_UNLOCK = 9029


def gate_sunshine_import_lists():
    # Gate and complete each list at its own recognition block. The gate holds
    # the whole block, which is also what advances the garage to the next list,
    # so a held list cannot be filled ahead of its item; the thread re-polls
    # every loop, so a list filled before the item completes once it arrives.
    for position, (thread, count, completion) in enumerate(SUNSHINE_IMPORT_LISTS):
        anchor = [i for i, ln in enumerate(lines) if ln == f":{thread}_87"]
        assert len(anchor) == 1, f"sunshine import: :{thread}_87 matched {len(anchor)}"
        i = anchor[0]
        shape = lines[i + 1:i + 4]
        assert (shape[0] == "if " and shape[1] == "  $1107 == 0"
                and shape[2].startswith("goto_if_false @")), (
            f"sunshine import: {thread} branch shape looks wrong ({shape})")
        loopback = shape[2][len("goto_if_false @"):]
        if position + 1 < len(SUNSHINE_IMPORT_LISTS):
            successor = SUNSHINE_IMPORT_LISTS[position + 1][0]
            starts = [j for j, ln in enumerate(lines)
                      if ln == f"start_new_script @{successor} "]
            successor_label = lines.index(f":{successor}")
            assert len(starts) == 1 and i < starts[0] < successor_label, (
                f"sunshine import: {thread} does not chain to {successor} "
                f"from inside its own thread")
        lines[i + 4:i + 4] = [
            "if and", f"  ${SUNSHINE_UNLOCK} >= {count}",
            f"  ${OWNERSHIP_SUNSHINE} >= 1", f"goto_if_false @{loopback}",
            f"${completion} = 1",
        ]
    edits.append(f"sunshine import: {len(SUNSHINE_IMPORT_LISTS)} lists gated "
                 f"on ${SUNSHINE_UNLOCK} and owned ${OWNERSHIP_SUNSHINE}")


def _hold_condition(class_index, district):
    # One condition, "this district of this class is released", to add to a test
    # the vanilla script already makes. A single condition rather than a pair is
    # what config_globals buys: an unlocked class arrives already released.
    # ">= 1" and not "== 1": released is 1 and a pair holding no content of this
    # class at all is 2, and content has to pass in both cases.
    return f"  ${district_unlock(class_index, district)} >= 1"


def gate_stunt_jumps():
    # Each jump is detected at its own takeoff, a locate_player_in_car_3d over
    # the ramp followed by `$792 = <id>`, and gating there is what makes the hold
    # per district: the id is the index into STUNT_JUMP_DISTRICTS. A held jump
    # never enters the sequence at all, so no per-jump flag ($795..$830) sets and
    # the APSTAT watcher sees nothing, the 36-counter $791 does not advance,
    # player_made_progress and register_unique_jump_found do not run so neither
    # the completion percentage nor the jump stat moves, and no pass text or cash
    # prints. The jump still flies, since only the detection is skipped, and it
    # stays re-doable forever.
    #
    # Ids 25 and 26 each have two takeoff definitions, so there are more sites
    # than jumps; every site gates on its own id's district.
    sites = []
    for index, line in enumerate(lines):
        match = re.fullmatch(r"\$792 = (\d+)", line)
        if match is None or match.group(1) == "0":
            continue
        identifier = int(match.group(1))
        assert 1 <= identifier <= len(STUNT_JUMP_DISTRICTS), \
            f"stunt jump gate: id {identifier} outside the district table"
        assert lines[index - 3] == "if ", (
            f"stunt jump {identifier}: expected `if ` at {index - 3}, "
            f"found {lines[index - 3]!r}")
        assert lines[index - 2].startswith("  locate_player_in_car_3d "), (
            f"stunt jump {identifier}: expected a takeoff locate at {index - 2}, "
            f"found {lines[index - 2]!r}")
        assert lines[index - 1].startswith("goto_if_false @USJ_"), (
            f"stunt jump {identifier}: expected the miss branch at {index - 1}, "
            f"found {lines[index - 1]!r}")
        sites.append((index, identifier))
    assert len(sites) >= len(STUNT_JUMP_DISTRICTS), \
        f"stunt jump gate: {len(sites)} takeoff sites for {len(STUNT_JUMP_DISTRICTS)} jumps"
    covered = {identifier for _index, identifier in sites}
    assert covered == set(range(1, len(STUNT_JUMP_DISTRICTS) + 1)), \
        f"stunt jump gate: ids {sorted(covered)} do not cover every jump"
    # Highest first, so an insertion never moves a site still to be edited.
    for index, identifier in sorted(sites, reverse=True):
        district = STUNT_JUMP_DISTRICTS[identifier - 1]
        lines[index - 3] = "if and"
        lines[index - 2:index - 2] = [_hold_condition(STUNT_JUMPS_CLASS, district)]
    edits.append(f"stunt jumps: {len(sites)} takeoffs gated by district")


STORE_GUARD_NUMBER = r"(-?[\d.]+|\$\d+)"
STORE_AREA = re.compile(
    rf"^  is_player_in_area_3d \$player_char 0 {STORE_GUARD_NUMBER} {STORE_GUARD_NUMBER} "
    rf"{STORE_GUARD_NUMBER} {STORE_GUARD_NUMBER} {STORE_GUARD_NUMBER} "
    rf"{STORE_GUARD_NUMBER}$")
STORE_LOCATE = re.compile(
    rf"^  locate_\w+ \$player_char (?:stopped 1 |0 ){STORE_GUARD_NUMBER} "
    rf"{STORE_GUARD_NUMBER} {STORE_GUARD_NUMBER} radius")


def _scalar_global(token):
    # A coordinate the script keeps in a global, resolvable only because the
    # whole file assigns it exactly once, as a literal.
    if not token.startswith("$"):
        return float(token)
    pattern = re.compile(rf"^\{token} = (-?\d+\.?\d*)$")
    values = [match.group(1) for match in (pattern.match(ln) for ln in lines) if match]
    assert len(values) == 1, f"{token}: {len(values)} assignments, expected 1"
    return float(values[0])


def _store_guard_point(index):
    # Where the nearest guarding test above this line puts the player: an area
    # box gives its centre, a locate gives its point.
    for probe in range(index, max(index - 8, -1), -1):
        area = STORE_AREA.match(lines[probe])
        if area:
            return ((_scalar_global(area.group(1)) + _scalar_global(area.group(4))) / 2,
                    (_scalar_global(area.group(2)) + _scalar_global(area.group(5))) / 2)
        locate = STORE_LOCATE.match(lines[probe])
        if locate:
            return (_scalar_global(locate.group(1)), _scalar_global(locate.group(2)))
    raise AssertionError(f"store gate: no guarding test above line {index}")


def gate_store_robberies():
    # The 15 stores are two thread families sharing two robbery handlers:
    # @SHOP5_1010 for the 12 street stores (gosub'd from SHOP1..SHOP5) and
    # @HARD3_2856 for the 3 hardware stores (from HARD1..HARD3). The aim test
    # inside a handler is the whole trigger, but it is shared, so it cannot say
    # which store is being robbed. What can is the per-store test that gosubs
    # into the handler, one for each of the 15, guarded by that store's own area.
    #
    # Those entries are not in store order, and store order is the
    # add_stores_knocked_off order the completions and the district table use, so
    # the two are paired by position: each stat site's guarding coordinate
    # against each entry's. Asserted to be a bijection within a few metres, so a
    # mispairing fails the build rather than gating the wrong store.
    #
    # A held store reads exactly as the player standing outside: the clerk still
    # spawns, still tracks the player, and killing him still raises the wanted
    # level, all vanilla.
    stat_sites = [i for i, ln in enumerate(lines) if ln == "add_stores_knocked_off 1"]
    assert len(stat_sites) == len(STORE_DISTRICTS), \
        f"store gate: {len(stat_sites)} stat sites for {len(STORE_DISTRICTS)} stores"
    entries = [i for i, ln in enumerate(lines)
               if ln.strip() in ("gosub @SHOP5_1010", "gosub @HARD3_2856")]
    assert len(entries) == len(STORE_DISTRICTS), \
        f"store gate: {len(entries)} robbery entries for {len(STORE_DISTRICTS)} stores"
    stat_points = [_store_guard_point(site) for site in stat_sites]
    entry_points = [_store_guard_point(site) for site in entries]
    paired: dict[int, int] = {}
    for order, point in enumerate(stat_points):
        distance, nearest = min(
            (((other[0] - point[0]) ** 2 + (other[1] - point[1]) ** 2) ** 0.5, k)
            for k, other in enumerate(entry_points))
        assert distance < 40.0, (
            f"store {order + 1}: nearest robbery entry is {distance:.0f} units away, "
            f"too far to pair")
        # Nearest alone would pair two stores that stand close together; the
        # margin over the runner-up is what says the pairing is the only
        # reading. Measured at 20 units for the tightest pair and 60 or more for
        # every other, with eleven of the fifteen exact.
        runner_up = sorted(
            ((other[0] - point[0]) ** 2 + (other[1] - point[1]) ** 2) ** 0.5
            for other in entry_points)[1]
        assert runner_up - distance > 15.0, (
            f"store {order + 1}: robbery entries at {distance:.0f} and "
            f"{runner_up:.0f} units are too close together to tell apart")
        assert nearest not in paired, (
            f"store {order + 1} and store {paired[nearest] + 1} both pair with "
            f"robbery entry {nearest}")
        paired[nearest] = order
    # Highest first, so an insertion never moves an entry still to be edited.
    for entry, order in sorted(paired.items(), reverse=True):
        index = entries[entry]
        assert lines[index - 1].startswith("goto_if_false @"), (
            f"store {order + 1}: expected the outside branch at {index - 1}, "
            f"found {lines[index - 1]!r}")
        assert lines[index - 3] == "if ", (
            f"store {order + 1}: expected `if ` at {index - 3}, "
            f"found {lines[index - 3]!r}")
        lines[index - 3] = "if and"
        lines[index - 2:index - 2] = [
            _hold_condition(ROBBABLE_STORES_CLASS, STORE_DISTRICTS[order])]
    edits.append(f"stores: {len(paired)} robbery entries gated by district")


def add_store_completions():
    # Each of the 15 store robberies calls add_stores_knocked_off; mark that
    # store's completion right after it. Source order maps to $9321..$9335.
    sites = [i for i, ln in enumerate(lines) if ln == "add_stores_knocked_off 1"]
    assert len(sites) == 15, f"stores: found {len(sites)} sites (expected 15)"
    for k in range(len(sites) - 1, -1, -1):
        lines[sites[k] + 1:sites[k] + 1] = [f"${9321 + k} = 1"]
    edits.append(f"stores: {len(sites)} completions $9321..$9335")


# The weapon shops. Six threads sell 32 things between them, and each sale is a
# stand-near test, an affordability test, a grant and a charge. The completion
# globals are contiguous from here in the world's shop_data order, because the
# shop class is appended last in the registry and completion globals follow
# location id order.
SHOP_COMPLETION_BASE = 9486

# Whether a pending shop item hides what it sells: the wall wears the AP marker
# in place of the item and the purchase hands over nothing until the check comes
# back from the server.
#
# Two things have to hold for this to be on, and both are load-bearing rather
# than incidental. The game loads MAIN into a fixed 225512 byte buffer, and the
# withholding, the model swap and the rebuild on purchase together cost a few
# thousand bytes that only exist because add_markers.py moves the six shop
# threads out; over that line the tail of the script, which is where the audio
# threads live, is simply not there in game. And every gate this emits carries a
# term for SHOPS_ENABLED as well as the completion global, because a disabled
# class behaves fully vanilla: reading the completion global alone would hand a
# seed with shuffle_shops off nothing on a first purchase, since that global is
# allocated either way.
SHOP_WITHHOLD = True

# The AP check marker's model, the same one a pending pickup wears. A shop puts
# this on the wall in place of what it sells until that check is taken.
SHOP_MARKER_MODEL = 376

# One while the shuffle_shops class is on, stamped by the ASI from slot_data.
# Mirrors scm.SHOPS_ENABLED_GLOBAL, pinned by check_scm_mirrors. Every piece of
# the withholding asks this first, so a seed without the class leaves the shops
# exactly as the game wrote them: the wall wears its own model and a purchase
# pays out. Without it the script would act on the completion global alone,
# which is allocated for every seed, and a class that is off would still change
# the world.
SHOPS_ENABLED = 9576

# (thread, script global, what it hands over, its own model) per shop item,
# mirroring shop_data.SHOP_ITEMS in order. The third element is a weapon type,
# or "armour" for the body armour every Ammu-Nation sells, which grants armour
# rather than a weapon. A weapon type appears at most once per thread, which is
# what lets a grant identify which item is being bought, and the script global
# is what identifies which object on the wall is that item.
SHOP_ITEM_GRANTS = [
    ("AMMU1", 889, 17, 274), ("AMMU1", 890, 24, 283), ("AMMU1", 891, 19, 277),
    ("AMMU1", 892, 27, 276), ("AMMU1", 893, "armour", 368),
    ("AMMU2", 889, 17, 274), ("AMMU2", 890, 23, 282), ("AMMU2", 891, 21, 279),
    ("AMMU2", 892, 28, 285), ("AMMU2", 893, 12, 270),
    ("AMMU2", 895, "armour", 368),
    ("AMMU3", 889, 18, 275), ("AMMU3", 890, 25, 284), ("AMMU3", 891, 20, 278),
    ("AMMU3", 892, 26, 280), ("AMMU3", 893, 29, 286),
    ("AMMU3", 894, "armour", 368),
    ("HARD1", 875, 2, 260), ("HARD1", 876, 7, 265), ("HARD1", 877, 8, 266),
    ("HARD1", 878, 6, 264), ("HARD1", 879, 9, 267),
    ("HARD2", 875, 2, 260), ("HARD2", 876, 7, 265), ("HARD2", 877, 8, 266),
    ("HARD2", 878, 5, 263), ("HARD2", 879, 10, 268),
    ("HARD3", 875, 2, 260), ("HARD3", 876, 7, 265), ("HARD3", 877, 8, 266),
    ("HARD3", 878, 9, 267), ("HARD3", 879, 11, 269),
]


def shop_marker_heading(item_positions, shopkeeper):
    """The heading that aims a shop's markers out of its display wall."""
    # A shop's items hang in a line on one wall, so the coordinate they vary
    # along is the wall and the other one is its normal. Which WAY along that
    # normal the room lies is what the vanilla item orientation does not say: a
    # weapon lies on its rack, so its own yaw tracks the wall rather than the
    # room. Taking that yaw and turning it 180 degrees was right in three shops
    # and 180 out in the other three. The shopkeeper stands IN the room, so the
    # sign of the offset from the wall to them is the answer, and it comes from
    # the same script.
    spread_x = max(x for x, _y in item_positions) - min(
        x for x, _y in item_positions)
    spread_y = max(y for _x, y in item_positions) - min(
        y for _x, y in item_positions)
    count = len(item_positions)
    middle_x = sum(x for x, _y in item_positions) / count
    middle_y = sum(y for _x, y in item_positions) / count
    # Both inputs are separated by an order of magnitude in every real shop, the
    # narrowest being a 0.2 wobble along a 4.1 line and a keeper 1.5 out. Close
    # to either boundary the geometry no longer says which wall or which side,
    # and copysign answers +1 for a zero rather than admitting it cannot tell.
    wall, across = sorted((spread_x, spread_y))
    assert across > 4.0 * max(wall, 0.05), (
        f"shops: item spreads {spread_x} by {spread_y} do not pick out a wall")
    offset = (shopkeeper[1] - middle_y if spread_x >= spread_y
              else shopkeeper[0] - middle_x)
    assert abs(offset) > 1.0, (
        f"shops: the shopkeeper stands {offset} from the display wall, too "
        "close to say which side of it the room is on")
    normal = ((0.0, math.copysign(1.0, offset)) if spread_x >= spread_y
              else (math.copysign(1.0, offset), 0.0))
    # Heading 180 faces +Y and 90 faces +X, the mapping every one of the six
    # measured shops agrees with.
    return math.degrees(math.atan2(normal[0], -normal[1])) % 360.0


def marker_orientation(handle, block, heading):
    """The marker stands upright and faces the room, whatever the item did."""
    # The vanilla lines orient a WEAPON on a rack, so a marker box wearing
    # them shows the player its unlit back, or for the flat-laid tools its
    # underside. The box takes the shop's own facing instead, and no tilt,
    # because a display box stands up straight.
    carried = [line for line in block[1:]
               if line.startswith(("set_object_dynamic ",
                                   "set_object_collision "))]
    # Every line in the block is either carried over or deliberately replaced
    # by the facing. A kind this does not know would vanish from the marker
    # branch without a word, so it stops the build instead.
    known = ("set_object_dynamic ", "set_object_collision ",
             "set_object_rotation ", "set_object_heading ")
    unknown = [line for line in block[1:] if not line.startswith(known)]
    assert not unknown, (
        f"shops: the marker branch would drop {unknown}; decide whether the "
        "marker carries it or is oriented by it")
    return [*carried, f"set_object_heading ${handle} z_angle_to {heading}"]


def add_shop_completions():
    # Buying a thing for the first time is the check, so every purchase writes
    # its completion global right after the money leaves.
    #
    # The CHARGE is the anchor, not the grant. A weapon purchase grants twice,
    # once with the ammo it gives and once with a cap on a branch for a player
    # who already owns it, and it charges once per branch; anchoring on the grant
    # would write the completion for a sale that never happened. Anchoring on the
    # charge and naming the item by the grant that precedes it marks exactly what
    # was paid for, and a thread's top-up branch writes the same global again,
    # which costs nothing.
    completion = {}
    handle_of = {}
    by_object = {}
    for index, (thread, handle, grant, model) in enumerate(SHOP_ITEM_GRANTS):
        key = (thread, grant)
        assert key not in completion, f"shops: {key} listed twice"
        completion[key] = SHOP_COMPLETION_BASE + index
        handle_of[key] = handle
        assert (thread, handle) not in by_object, (
            f"shops: {thread} ${handle} listed twice")
        by_object[(thread, handle)] = (SHOP_COMPLETION_BASE + index, model)

    threads = {}
    for thread in ("AMMU1", "AMMU2", "AMMU3", "HARD1", "HARD2", "HARD3"):
        starts = [i for i, ln in enumerate(lines) if ln == f"script_name '{thread}'"]
        assert len(starts) == 1, f"shops: {thread} appears {len(starts)} times"
        start = starts[0]
        after = [i for i, ln in enumerate(lines)
                 if i > start and ln.startswith("script_name '")]
        threads[thread] = (start, after[0] if after else len(lines))

    # How each item's object is built in vanilla: the create_object line and the
    # set_object lines that follow it for the same handle. Captured before
    # anything is rewritten, so a purchase can put the real item back by
    # replaying exactly what the shop would have built.
    vanilla_block = {}
    for thread, (start, end) in threads.items():
        for index in range(start, end):
            line = lines[index]
            if not line.startswith("create_object $"):
                continue
            handle = int(line.split("create_object $")[1].split(" ")[0])
            if (thread, handle) not in by_object:
                continue
            block = [line]
            for follow in range(index + 1, end):
                if lines[follow].startswith("set_object") and \
                        f"${handle} " in lines[follow]:
                    block.append(lines[follow])
                else:
                    break
            vanilla_block[(thread, handle)] = block

    # One facing per shop, derived from the shop itself. Read before any
    # rewriting, from the same create lines the blocks above came from.
    marker_heading = {}
    for thread, (start, end) in threads.items():
        item_positions = []
        keepers = []
        for index in range(start, end):
            line = lines[index]
            if line.startswith("create_object $"):
                handle = int(line.split("create_object $")[1].split(" ")[0])
                if (thread, handle) in by_object:
                    position = line.split(" at ")[1].split()
                    item_positions.append((float(position[0]),
                                           float(position[1])))
            elif line.startswith("create_char $"):
                position = line.split(" at ")[1].split()
                keepers.append((float(position[0]), float(position[1])))
        if not item_positions:
            continue
        # One char per shop thread, so the keeper is not merely the first: it is
        # the only one, and a position driving a player-visible facing is not
        # picked by ordering.
        assert len(keepers) == 1, (
            f"shops: {thread} creates {len(keepers)} chars, so which one stands "
            "in the room is a choice this cannot make")
        marker_heading[thread] = shop_marker_heading(item_positions, keepers[0])

    # Every shop's facing was measured in game, so every shop's facing is pinned
    # here, and the set is pinned too rather than each entry being optional.
    # Pinning only the three whose rooms lie toward +Y would leave the X
    # handedness free, and the flip that passes those three is exactly the one
    # that put Downtown and Little Havana 180 degrees out.
    verified_in_game = {"AMMU1": 180.0, "AMMU2": 180.0, "AMMU3": 90.0,
                        "HARD1": 0.0, "HARD2": 180.0, "HARD3": 270.0}
    assert set(marker_heading) == set(verified_in_game), (
        "shops: the shops with derived facings and the shops measured in game "
        f"differ by {sorted(set(marker_heading) ^ set(verified_in_game))}, so a "
        "facing would ship unverified")
    for thread, expected in verified_in_game.items():
        assert marker_heading[thread] == expected, (
            f"shops: {thread} derives {marker_heading[thread]} where {expected} "
            "was verified in game")

    # Three kinds of edit, all collected first and applied back to front so an
    # insertion cannot move a site that has not been rewritten yet.
    replacements = {}
    # How many lines each replacement consumes. The creation sites take the whole
    # vanilla block, because the orientation lines trail the create and would
    # otherwise apply to whichever object the branch built.
    replaced_span = {}
    charges = []
    seen = set()
    label = 0
    marker_requests = []
    for thread, (start, end) in threads.items():
        pending = None
        first_object = None
        for index in range(start, end):
            line = lines[index]
            if line.startswith("create_object $"):
                if first_object is None:
                    first_object = index
                if not SHOP_WITHHOLD:
                    continue
                handle = int(line.split("create_object $")[1].split(" ")[0])
                entry = by_object.get((thread, handle))
                if entry is not None:
                    global_index, model = entry
                    # The model is a number for a weapon and a NAME for the body
                    # armour, so the token is read out of the line rather than
                    # matched against the number this table carries.
                    head, _, tail = line.rpartition(" = create_object ")
                    token, _, position = tail.partition(" at ")
                    assert head and position, (
                        f"shops: {thread} ${handle} is not a create_object line")
                    assert token == str(model) or token.startswith("#"), (
                        f"shops: {thread} ${handle} creates {token}, not {model}")
                    label += 1
                    # Named after the thread they sit in. A relocation cuts
                    # a thread at the first label that is not its own, so a
                    # label named anything else ends the cut early and takes
                    # the rest of the thread with it.
                    own = f"{thread}_APSHOP_OWN_{label}"
                    made = f"{thread}_APSHOP_MADE_{label}"
                    # The wall wears the marker until the check is taken.
                    # Each branch carries its own orientation: the marker stands
                    # up and faces out, the item keeps exactly what the shop gave
                    # it.
                    block = vanilla_block[(thread, handle)]
                    replacements[index] = [
                        "if and", f"  ${SHOPS_ENABLED} == 1",
                        f"  ${global_index} == 0", f"goto_if_false @{own}",
                        f"{head} = create_object {SHOP_MARKER_MODEL} at {position}",
                        *marker_orientation(handle, block,
                                            marker_heading[thread]),
                        f"goto @{made}",
                        f":{own}",
                        *block,
                        f":{made}",
                    ]
                    replaced_span[index] = len(block)
            elif line.startswith("give_weapon_to_player $player_char weapon "):
                pending = int(line.split("weapon ")[1].split(" ")[0])
                if not SHOP_WITHHOLD:
                    continue
                key = (thread, pending)
                assert key in completion, f"shops: {thread} grants unlisted {pending}"
                label += 1
                done = f"{thread}_APSHOP_DONE_{label}"
                # Nothing is handed over while the check is still to be taken.
                replacements[index] = [
                    "if or", f"  ${SHOPS_ENABLED} == 0",
                    f"  ${completion[key]} == 1", f"goto_if_false @{done}",
                    line, f":{done}",
                ]
            elif line.startswith("add_armour_to_player "):
                pending = "armour"
                if not SHOP_WITHHOLD:
                    continue
                key = (thread, pending)
                assert key in completion, f"shops: {thread} grants unlisted armour"
                label += 1
                done = f"{thread}_APSHOP_DONE_{label}"
                replacements[index] = [
                    "if or", f"  ${SHOPS_ENABLED} == 0",
                    f"  ${completion[key]} == 1", f"goto_if_false @{done}",
                    line, f":{done}",
                ]
            elif line.startswith("add_score $player_char money += -"):
                assert pending is not None, (
                    f"shops: {thread} charges at line {index} with no grant before it")
                key = (thread, pending)
                assert key in completion, f"shops: {thread} sells unlisted {pending}"
                label += 1
                charges.append((index, completion[key], (thread, handle_of[key]),
                                label))
                seen.add(key)
                pending = None
        assert first_object is not None, f"shops: {thread} creates no stock"
        if SHOP_WITHHOLD and thread in marker_heading:
            marker_requests.append((first_object, thread))

    missing = [key for key in completion if key not in seen]
    assert not missing, f"shops: no purchase site found for {missing}"

    sites = ([(index, None, body) for index, body in replacements.items()]
             + [(index, (global_index, object_key, tag), None)
                for index, global_index, object_key, tag in charges]
             + [(index, ("request", thread), None)
                for index, thread in marker_requests])
    # A thread's first create IS the first item it sells in all six, so the
    # request insertion lands on the same index as that item's creation span and
    # the two are ordered only by sorted() being stable over the concatenation
    # above. Replacement first, then the request inserting ahead of it. The other
    # way round, the span would eat the inserted request and strand the tail of
    # the vanilla block, so the order is pinned here rather than left to be
    # noticed.
    request_indices = {index for index, _thread in marker_requests}
    for index in request_indices & set(replacements):
        replacement_position = next(
            position for position, site in enumerate(sites)
            if site[0] == index and site[2] is not None)
        request_position = next(
            position for position, site in enumerate(sites)
            if site[0] == index and site[1] is not None
            and site[1][0] == "request")
        assert replacement_position < request_position, (
            f"shops: the request at line {index} would be applied before the "
            "creation span that shares its index and be eaten by it")
    for index, kind, body in sorted(sites, key=lambda s: s[0], reverse=True):
        if body is not None:
            lines[index:index + replaced_span.get(index, 1)] = body
        elif isinstance(kind, tuple) and kind[0] == "request":
            # The marker has to be in memory before the wall can wear it, and a
            # shop is where nothing else needs it. Asked for only when the class
            # is on: a blocking stream flush on every shop entry is not what a
            # seed without the class should be paying.
            skip = f"{kind[1]}_APSHOP_NOMODEL"
            lines[index:index] = [
                "if ", f"  ${SHOPS_ENABLED} == 1", f"goto_if_false @{skip}",
                f"request_model {SHOP_MARKER_MODEL}", "load_all_models_now ",
                f":{skip}"]
        else:
            global_index, object_key, tag = kind
            # The check is taken, so the wall stops advertising it. The object is
            # rebuilt here rather than left for the shop to rebuild on the next
            # visit, so what is bought turns back into itself while the player is
            # still standing at it. Replays the shop's own build, so the item
            # keeps the facing and the moving-list flag it was given.
            handle = object_key[1]
            if SHOP_WITHHOLD:
                # Named after its thread, like the others: a relocation
                # cuts a thread at the first label that is not its own.
                # Keyed on the site, not the item: three items charge at two
                # branches each, so an item-keyed label is defined twice.
                kept = f"{object_key[0]}_APSHOP_KEPT_{tag}"
                lines[index + 1:index + 1] = (
                    [f"${global_index} = 1",
                     "if ", f"  ${SHOPS_ENABLED} == 1", f"goto_if_false @{kept}",
                     f"delete_object ${handle}"]
                    + vanilla_block[object_key] + [f":{kept}"])
            else:
                lines[index + 1:index + 1] = [f"${global_index} = 1"]
    edits.append(
        f"shops: {len(charges)} purchase sites across {len(threads)} threads, "
        f"{len(completion)} completions "
        f"${SHOP_COMPLETION_BASE}..${SHOP_COMPLETION_BASE + len(completion) - 1}, "
        f"{len(replacements)} lines gated on the check")


def add_package_watcher():
    # Hidden packages are count-only in the SCM (get_collectable1s_collected),
    # so mark package N's completion global ($9079+N) once at least N are
    # collected. Unrolled per package with a chained early-exit (the counts are
    # cumulative, so the first unmet threshold ends the sweep). VC's script VM
    # does NOT execute Sanny's dynamic global-array access (a read silently
    # drops, a write crashes the game on use), so no array indexing here.
    # $9006 is an unused reserved scratch global.
    body = ["", ":APPKG", "script_name 'APPKG'", "",
            ":APPKG_LOOP", "wait 500",
            "get_collectable1s_collected $9006"]
    for count in range(1, 101):
        body += ["if ", f"  $9006 >= {count}", "goto_if_false @APPKG_DONE", f"${9079 + count} = 1"]
    body += [":APPKG_DONE", "goto @APPKG_LOOP"]
    insert_before(":GEN1", body, "APPKG package watcher")
    insert_after("start_new_script @HOT ", ["start_new_script @APPKG "], "boot start @APPKG")


def add_area_watcher(shared_block, crossing_pieces, east_gate, west_gate):
    # One watcher, one branch per crossing plus the two island gates. A crossing
    # opens on its own item OR on Mainland Access, which is what lets one static
    # script serve both settings: with split_mainland_access off only Mainland
    # Access is ever written and every crossing opens together, and with it on
    # only the crossing globals are. A crossing branch guards on its roadblock
    # still existing, so its road switches and its delete run once without a flag
    # of their own.
    #
    # The shared part of the flip (the vanilla flag $847 that stocks the sniper
    # rifle, the mainland restarts, the hurricane stop, the Washington pier door
    # and the announcement) is a subroutine, gosubbed from the bridge trigger and
    # again from the west gate, and once-guarded by the $847 it sets. Reaching it
    # through the west gate is what keeps a causeway item held without Starfish
    # Island Access from flipping the mainland open before any route exists.
    #
    # The Starfish east gate opens on Starfish Island Access alone; the west gate
    # needs that plus a crossing item or Mainland Access, since it is the sole
    # barrier on the island's mainland crossing. Both once-guard on the reserved
    # scratch globals $9004 (east) and $9007 (west), since each swaps its object
    # rather than deleting it. The vanilla flag $1157 stays with the phone call in
    # CELL, which would block a watcher keyed on it if the call fired first.
    labels = [f"APAREA_CROSS_{position}" for position in range(len(MAINLAND_ROADBLOCKS))]
    bridge_unlocks = [unlock for _name, _handle, unlock in MAINLAND_ROADBLOCKS]
    body = ["", ":APAREA", "script_name 'APAREA'", "", ":APAREA_LOOP", "wait 500"]
    body += ["if or", f"  ${MAINLAND_ACCESS_UNLOCK} >= 1"]
    body += [f"  ${unlock} >= 1" for unlock in bridge_unlocks]
    body += [f"goto_if_false @{labels[0]}", "gosub @APAREA_SHARED"]
    for position, (_name, handle, unlock) in enumerate(MAINLAND_ROADBLOCKS):
        following = (labels[position + 1] if position + 1 < len(labels)
                     else "APAREA_STAR")
        body += [f":{labels[position]}",
                 "if or", f"  ${MAINLAND_ACCESS_UNLOCK} >= 1", f"  ${unlock} >= 1",
                 f"goto_if_false @{following}",
                 "if ", f"  does_object_exist ${handle}",
                 f"goto_if_false @{following}",
                 *crossing_pieces[handle]]
    body += [":APAREA_STAR",
             "if ", f"  ${STARFISH_ACCESS_UNLOCK} >= 1", "goto_if_false @APAREA_LOOP",
             "if ", "  $9004 == 0", "goto_if_false @APAREA_WEST",
             "$9004 = 1",
             *east_gate,
             ":APAREA_WEST",
             "if or", f"  ${MAINLAND_ACCESS_UNLOCK} >= 1",
             f"  ${STARFISH_CAUSEWAY_UNLOCK} >= 1", "goto_if_false @APAREA_LOOP",
             "if ", "  $9007 == 0", "goto_if_false @APAREA_LOOP",
             "$9007 = 1",
             *west_gate,
             "gosub @APAREA_SHARED",
             "goto @APAREA_LOOP",
             "", ":APAREA_SHARED",
             "if ", "  $847 == 0", "goto_if_false @APAREA_SHARED_DONE",
             *shared_block,
             ":APAREA_SHARED_DONE", "return "]
    insert_before(":GEN1", body, "APAREA watcher thread")
    insert_after("start_new_script @HOT ", ["start_new_script @APAREA "], "boot start @APAREA")


# Activity launchers (Boatyard's Checkpoint Charlie, the Sunshine Autos race
# showroom) are repeatable and have no passed-flag guard, so they are wired
# bespoke: a gate at the launcher top and completion from the vanilla win flags
# via the APACT watcher. Each requires its property's ownership global; the
# purchase condition is implicit, since these threads start only at the buy
# cutscene. The showroom carries no unlock count: its menu wraps all six races
# freely from the first visit, so they are flat checks and Sunshine's
# progressive gates the import lists instead.
# (launcher-10 label, [(global, count), ...], loop-back label.)
ACTIVITIES = [
    ("COKRUN_10", [(9028, 1), owned("BOATBY")], "COKRUN_345"),
    ("RACES_10", [owned("CARBUY1")], "RACES_121"),
]

# The six races' vanilla win flags in showroom menu order (menu arm n sets
# $1587+n once on its first win), paired with their completion globals.
SUNSHINE_RACE_WINS = [
    (1588, 9370), (1589, 9371), (1590, 9372),
    (1591, 9373), (1592, 9374), (1593, 9375),
]


def add_activity_gates():
    for label, conditions, loopback in ACTIVITIES:
        starts = [i for i, ln in enumerate(lines) if ln == f":{label}"]
        assert len(starts) == 1, f"activity gate: :{label} matched {len(starts)}"
        i = starts[0]
        assert lines[i + 1] == "wait $default_wait_time", f"activity gate: {label} missing wait"
        gate = []
        for global_index, count in conditions:
            gate += ["if ", f"  ${global_index} >= {count}", f"goto_if_false @{loopback}"]
        lines[i + 2:i + 2] = gate
        edits.append(f"activity gate {label} {conditions}")


# Side events (14): completion-only, no gate (always playable). Each is a
# vanilla win flag set to 1 once on first completion. (win_flag, completion).
# Order matches the spec's side_events block ($9307..$9320).
SIDE_EVENTS = [
    (1597, 9307), (1598, 9308), (55, 9309),                  # Hotring, Bloodring, Dirtring
    (1584, 9310), (1585, 9311), (1586, 9312), (1587, 9313),  # chopper checkpoints
    (8241, 9314), (8485, 9315), (8156, 9316),                # RC Bandit, Baron, Raider
    (363, 9317), (364, 9318), (339, 9319), (351, 9320),      # Trial, Test Track, PCJ, Cone
]


def add_activity_watcher():
    # Boot-started watcher that polls vanilla win flags and marks completions:
    # Checkpoint Charlie ($607 -> $9365), the six Sunshine Autos races
    # ($1588..$1593, one check each), and the 14 side events. Every flag is an
    # independent set-once signal, so each writes its own completion global.
    watched = [(607, 9365), *SUNSHINE_RACE_WINS, *SIDE_EVENTS]
    body = ["", ":APACT", "script_name 'APACT'", "",
            ":APACT_LOOP", "wait 1000"]
    for index, (win_flag, completion_global) in enumerate(watched):
        skip = "@APACT_LOOP" if index == len(watched) - 1 else f"@APACT_EVENT_{index}"
        body += ["if ", f"  ${win_flag} == 1", f"goto_if_false {skip}", f"${completion_global} = 1"]
        if index != len(watched) - 1:
            body += [f":APACT_EVENT_{index}"]
    body += ["goto @APACT_LOOP"]
    insert_before(":GEN1", body, "APACT activity + side-event watcher")
    insert_after("start_new_script @HOT ", ["start_new_script @APACT "], "boot start @APACT")


# Vanilla cash suppression. The AP check replaces each check's one-time
# completion cash; repeatable earnings (fares, per-action pay, replay prizes,
# race replay prizes, till cash) stay vanilla. Story mission pass cash is deleted
# outright (story missions are always on); every toggleable class gates its
# cash on a class-cash config flag instead, so a disabled class pays fully
# vanilla. Side events suppress the first completion only: the payout skips
# while the class flag is set and the event's completion global is still zero,
# so replays pay. The flag indices match scm.py.
MISSION_HEADER = re.compile(r"^//-------------Mission (\d+)---------------$")
PASS_BANNER = re.compile(r"^print_with_number_big 'M_PASS' number (\d+) time \d+ style 1$")
CASH_ADD = re.compile(r"^add_score \$player_char money \+= (\$?\d+)$")

# Venue mission launchers, the Properties class members among MISSIONS
# (mirrors data.VENUE_STRANDS). Their pass cash is gated, not deleted.
VENUE_LAUNCHERS = frozenset([
    "BANK1", "BANK2", "BANK3", "BANK4", "PORN1", "PORN2", "PORN3", "PORN4",
    "COU1", "COU2", "TWAR1", "TWAR2", "TWAR3", "ICE1",
])

apcash_numbers = iter(range(1, 10_000))


def next_apcash_label():
    return f"APCASH_{next(apcash_numbers)}"


def guard_flag(index, span, flag):
    # Wrap `span` lines in an if-flag-zero guard: vanilla pays only while the
    # class-cash flag is zero (the class is disabled).
    guard_span(index, span, flag, next_apcash_label())


def guard_replay(index, span, completion, flag):
    # Wrap `span` lines so they run when the check's class is off OR the event's
    # completion global is already set (a replay). Only the first completion
    # while the class is on skips the payout: the payout and the win-flag write
    # share one script frame, and the APACT watcher marks the completion global
    # at least a frame later, so the global is still zero exactly on the run the
    # AP check eats.
    label = next_apcash_label()
    lines[index + span:index + span] = [f":{label}"]
    lines[index:index] = ["if or", f"  ${flag} == 0",
                          f"  ${completion} == 1", f"goto_if_false @{label}"]
    guard_labels.append(label)


def mission_blocks():
    # Mission number -> (start, end) line span from the decompile's headers.
    found = [(int(MISSION_HEADER.match(ln).group(1)), i)
             for i, ln in enumerate(lines) if MISSION_HEADER.match(ln)]
    spans = {}
    for position, (number, start) in enumerate(found):
        end = found[position + 1][1] if position + 1 < len(found) else len(lines)
        spans[number] = (start, end)
    return spans


def launcher_mission_number(launcher):
    starts = [i for i, ln in enumerate(lines) if ln == f":{launcher}"]
    assert len(starts) == 1, f"mission number: :{launcher} matched {len(starts)}"
    launch = _first(j for j in range(starts[0], len(lines))
                    if lines[j].startswith("load_and_launch_mission_internal "))
    assert launch is not None, f"mission number: {launcher} has no launch opcode"
    return int(lines[launch].split()[1])


def check_play_order():
    # Vice City numbers each strand's missions in play order, so a strand whose
    # gate counts do not ascend by mission number has a launcher on the wrong
    # count, and the progressive would open its giver's missions out of order.
    # Avery is the trap: its mission threads are named SERG1, SERG3, SERG2, so
    # pairing launchers by thread name puts Two Bit Hit before Demolition Man.
    strands = {}
    for launcher, gate_conditions, _ in MISSIONS:
        if not gate_conditions:
            continue
        # A gated mission's first term is its own strand unlock, which is what
        # groups this table by strand. Asserted rather than assumed, because a
        # mainland or passed term first is a (global, count) unpack away from a
        # TypeError that names neither the launcher nor the rule it broke.
        first = gate_conditions[0]
        assert first != MAINLAND_ANY and first[0] != MISSION_PASSED, (
            f"play order: {launcher}'s first gate term is {first}, not its "
            f"strand unlock")
        unlock, count = first
        if UNLOCK_FIRST <= unlock <= UNLOCK_LAST:
            strands.setdefault(unlock, []).append((count, launcher))
    for unlock, entries in sorted(strands.items()):
        ordered = sorted(entries)
        counts = [count for count, _ in ordered]
        assert counts == list(range(1, len(counts) + 1)), (
            f"play order: strand ${unlock} gates {ordered} are not counts 1..N")
        missions = [launcher_mission_number(launcher) for _, launcher in ordered]
        assert missions == sorted(missions), (
            f"play order: strand ${unlock} gates {ordered} launch missions "
            f"{missions}, which is not the vanilla order")
    print(f"verified play order across {len(strands)} strands")


# The finale, which the hunt goal's warp borrows two facts from: the mission its
# launcher launches, and the vanilla flag that records its pass. Both are read
# out of the source at build time, so neither a mission number nor a vanilla flag
# is written down here.
FINALE_LAUNCHER = "FIN2"
FINALE_FACTS = {}

# What the finale's ending path does with a handle, read off the source rather
# than trusted: every opcode in that path taking one global and nothing else
# must be one of these, so a decompile that releases a handle some other way
# fails the build instead of leaving that handle unstamped. The writer is in the
# list because it shares the shape: it fills a global rather than reading one.
FINALE_RELEASES = ("delete_char", "remove_char_elegantly", "remove_blip",
                   "remove_pickup")
FINALE_ENDING_WRITERS = ("get_game_timer",)
# What the skipped body creates and the ending path releases: thirteen chars
# (two actors and eleven car passengers), three blips and three pickups. The
# nine gang member slots the ending releases beside them are not here because
# the setup already holds them at the sentinel.
FINALE_HANDLE_COUNT = 19
# The launch conditions, spelled the way the source spells them. Asserted to
# appear in the decompile before they are emitted, because a condition Sanny
# does not recognize as the game's own reads as a fresh always-zero global and
# the watcher would launch the finale in the middle of another mission.
FINALE_LAUNCH_CONDITIONS = ("  $onmission == 0",
                            "  is_player_playing $player_char",
                            "  can_player_start_mission $player_char")


def resolve_finale_facts():
    # Read before a single gate is written, for the reason resolve_passed_flags
    # reads its flags there: the wiring loop turns a NonStandard into a printed
    # skip line, so a lazy read could leave the watcher on a flag nothing sets,
    # and it would then launch the finale again after every ending it plays.
    flag, _gate_block, _loopback = derive(FINALE_LAUNCHER)
    number = launcher_mission_number(FINALE_LAUNCHER)
    write = f"{flag} = 1"
    sites = [i for i, ln in enumerate(lines) if ln == write]
    assert len(sites) == 1, (
        f"finale warp: {write} appears at {len(sites)} sites, not one, so the "
        f"watcher cannot tell an ending already played from one still to play")
    start, end = mission_blocks()[number]
    assert start < sites[0] < end, (
        f"finale warp: {write} is at line {sites[0] + 1}, outside the block of "
        f"the mission {FINALE_LAUNCHER} launches")
    FINALE_FACTS["passed_flag"] = flag
    FINALE_FACTS["mission"] = number
    print(f"resolved finale facts: mission {number}, passed flag {flag}")


def add_finale_flag():
    # Raised on the mission's first line and dropped on its last, so the ASI can
    # tell the mansion siege is on and leave the pickup pool alone for it.
    #
    # One write each because the mission has one entry label and one
    # terminate_this_script: every path through it, passed or failed, converges
    # on that terminate, which is what makes a single drop cover them all. Both
    # counts are asserted rather than assumed, since a structure that grew a
    # second exit would leave the flag raised for the rest of the session. The
    # ASI drops it too if it ever sees it raised with no mission running, so a
    # thread killed from outside cannot strand it either.
    number = FINALE_FACTS["mission"]
    start, end = mission_blocks()[number]
    # The entry is read off the source rather than named: the mission's first
    # label is where its thread begins, so the raise lands on the one line every
    # run of it reaches, once.
    entries = [i for i in range(start, end) if lines[i].startswith(":")]
    assert entries, f"finale flag: mission {number} opens on no label"
    entry = entries[0]
    exits = [i for i in range(start, end)
             if lines[i].strip() == "terminate_this_script"]
    assert len(exits) == 1, (
        f"finale flag: mission {number} has {len(exits)} terminate_this_script, "
        "not one, so one drop cannot cover every way out")
    assert exits[0] > entry, (
        f"finale flag: mission {number} terminates at line {exits[0] + 1}, before "
        f"its own first label at {entry + 1}, so inserting the later index first "
        "would move the earlier one")
    # Later index first, so inserting does not move the earlier one.
    lines.insert(exits[0], f"${FINALE_ACTIVE} = 0")
    lines.insert(entry + 1, f"${FINALE_ACTIVE} = 1")
    # The only two writers, asserted. The globals below the unlock block look
    # unused and are all taken for scratch, and this flag has to survive a whole
    # mission: a second writer would clear it under the ASI, which reads it every
    # frame to decide whether to touch the pool at all.
    writers = [i for i, line in enumerate(lines)
               if line.strip().startswith(f"${FINALE_ACTIVE} =")]
    assert len(writers) == 3, (
        f"finale flag: ${FINALE_ACTIVE} is written at {len(writers)} sites, not "
        "the three expected, the foundation's sizing and initialising line plus "
        "the raise and drop this adds, so something else uses it")
    reads = [i for i, line in enumerate(lines)
             if f"${FINALE_ACTIVE}" in line and i not in writers]
    assert not reads, (
        f"finale flag: ${FINALE_ACTIVE} is read at {len(reads)} sites in the "
        "script, and only the ASI is meant to read it")
    print(f"finale flag: ${FINALE_ACTIVE} raised in mission {number} and dropped "
          "at its exit")


def add_finale_warp():
    # A macguffin hunt ends in the story's ending, so the last Package Fragment
    # plays it: the ASI raises the warp flag and this watcher launches the finale
    # wherever the player is standing, on the conditions every vanilla launcher
    # waits for and no others. No position, no money, no asset count and none of
    # the AP gate, since the goal is already met by then. The mission's own
    # passed flag is what keeps an ending from playing twice, and it is what lets
    # the watcher keep polling a flag the ASI raises on every frame the client
    # asks for the ending.
    #
    # Inside the mission, one branch past the setup jumps to the block that plays
    # the ending cutscene, so what the player gets is the vanilla ending, its
    # credits, its mission pass and its completion point, and none of the fight.
    # That block opens with make_player_safe_for_cutscene, which is what makes
    # "in whatever state" the mission's own business rather than this script's.
    #
    # The body the branch skips is what creates the actors, blips and pickups the
    # ending path then releases, so each of those handles is stamped with the
    # sentinel the setup already uses for the rest. Handles the ending releases
    # and the mission never creates belong to other threads, and stamping one of
    # those would leak a live blip onto the radar for good, so ownership decides
    # which are stamped: created in the skipped body, and not already initialized
    # by the setup.
    number = FINALE_FACTS["mission"]
    start, end = mission_blocks()[number]
    cutscenes = [i for i in range(start, end) if lines[i] == "load_cutscene 'FINALE'"]
    assert len(cutscenes) == 1, (
        f"finale warp: mission {number} loads the ending cutscene "
        f"{len(cutscenes)} times, not once")
    safe = [i for i in range(start, cutscenes[0])
            if lines[i].startswith("make_player_safe_for_cutscene ")]
    assert safe, (
        "finale warp: nothing makes the player safe before the ending cutscene, "
        "so a warp into it would land in whatever state the player was in")
    entry = safe[-1]
    assert lines[entry - 1].startswith(":"), (
        "finale warp: the ending block does not open on a label, so there is "
        "nothing to jump to")
    target = lines[entry - 1][1:]
    anchors = [i for i in range(start, entry)
               if lines[i].startswith("load_special_character ")]
    assert anchors, "finale warp: the mission setup loads no cutscene character"
    branch = anchors[0]
    # The jump has to stay at the gosub depth it starts at, or the return that
    # ends the ending path returns from the wrong call. The mission's entry block
    # gosubs its body and the branch goes in that body's own straight run, which
    # is what these two assert: the body's label comes first, and nothing between
    # it and the branch calls or returns.
    entry_gosubs = [lines[i] for i in range(start, branch)
                    if lines[i].startswith("gosub @")]
    assert entry_gosubs, "finale warp: the mission does not gosub its own body"
    body_label = f":{entry_gosubs[0].split('@', 1)[1].strip()}"
    body_start = [i for i in range(start, branch) if lines[i] == body_label]
    assert len(body_start) == 1, (
        f"finale warp: {body_label} is the body the mission gosubs and it "
        f"appears {len(body_start)} times before the branch, not once")
    assert not any(lines[i].startswith("gosub @") or lines[i].strip() == "return"
                   for i in range(body_start[0], branch)), (
        "finale warp: the branch would go inside a nested subroutine of the "
        "mission body, where a jump out leaves the return stack dirty")
    # What the ending path does with a global it names alone, derived from the
    # source: everything must be a release this transform knows how to stamp for
    # or the writer that fills its own global. A verb outside both is a handle
    # released in a way ownership cannot be reasoned about, so it fails here.
    verbs = re.compile(r"^([a-z_0-9]+) \$(\d+)$")
    unknown = sorted({match.group(1) for i in range(entry - 1, end)
                      if (match := verbs.match(lines[i]))
                      and match.group(1) not in FINALE_RELEASES
                      and match.group(1) not in FINALE_ENDING_WRITERS})
    assert not unknown, (
        f"finale warp: the ending path uses {unknown} on a global of its own, "
        f"which is neither a release this stamps for nor a known writer")
    # Only the sentinel counts as already initialized. A setup that zeroed a
    # handle instead would otherwise leave it unstamped, and the ending path
    # would release handle zero.
    sentinel = re.compile(r"^\$(\d+) = -1$")
    # Ownership is any opcode filling the global, not only the creations, so a
    # creation spelled some other way cannot read as a handle another thread
    # owns. Stamping is still confined to what the ending releases.
    created = re.compile(r"^[a-z_0-9]+ \$(\d+) = ")
    released = re.compile(rf"^(?:{'|'.join(FINALE_RELEASES)}) \$(\d+)$")
    initialized = {int(match.group(1)) for i in range(start, branch)
                   if (match := sentinel.match(lines[i]))}
    owned = {int(match.group(1)) for i in range(branch, entry - 1)
             if (match := created.match(lines[i]))}
    handles = sorted({int(match.group(1)) for i in range(entry - 1, end)
                      if (match := released.match(lines[i]))} & owned - initialized)
    assert len(handles) == FINALE_HANDLE_COUNT, (
        f"finale warp: {len(handles)} handles to stamp, expected "
        f"{FINALE_HANDLE_COUNT}; the ending path or the body it skips has moved, "
        f"so re-derive which handles the warp has to account for: {handles}")
    # The one thing a jump over a mission body can quietly cost the player is a
    # completion point, the percentage the stats menu shows. The warp has to skip
    # none of them and still reach the mission's own.
    assert PROGRESS_LINE not in lines[branch:entry - 1], (
        "finale warp: the body the warp skips holds a completion point")
    assert PROGRESS_LINE in lines[entry - 1:end], (
        "finale warp: the ending path reaches no completion point, so the warp "
        "would cost the player the finale's percentage")
    skip = "APFINWARP"
    lines[branch:branch] = [
        "if ", f"  ${FINALE_WARP} == 1", f"goto_if_false @{skip}",
        *[f"${handle} = -1" for handle in handles],
        f"goto @{target}",
        f":{skip}",
    ]
    for condition in FINALE_LAUNCH_CONDITIONS:
        assert condition in SOURCE_LINES, (
            f"finale warp: the source never writes {condition!r}, so the "
            f"watcher would be emitting a condition this game does not use")
    body = ["", ":APFIN", "script_name 'APFIN'", "",
            ":APFIN_LOOP", "wait 500",
            "if and", f"  ${FINALE_WARP} == 1",
            f"  {FINALE_FACTS['passed_flag']} == 0",
            *FINALE_LAUNCH_CONDITIONS,
            "goto_if_false @APFIN_LOOP",
            f"load_and_launch_mission_internal {number}",
            "goto @APFIN_LOOP"]
    insert_before(":GEN1", body, "APFIN finale warp watcher")
    insert_after("start_new_script @HOT ", ["start_new_script @APFIN "],
                 "boot start @APFIN")
    edits.append(f"finale warp: mission {number} branches to @{target}, "
                 f"{len(handles)} handles stamped")


def suppress_mission_rewards():
    # Every wired mission's pass cash, detected inside its mission block: each
    # M_PASS banner, plus every literal cash add whose amount matches a banner
    # amount in the same block, since the pass blocks scatter flag, banner,
    # and cash in different orders and distances across missions. In-mission
    # 'BONUS' earnings pay other amounts and stay; the audit pins them, so an
    # amount collision fails the build.
    spans = mission_blocks()
    actions = []
    for launcher, _, _ in MISSIONS:
        number = launcher_mission_number(launcher)
        start, end = spans[number]
        amounts = {PASS_BANNER.match(lines[i]).group(1)
                   for i in range(start, end) if PASS_BANNER.match(lines[i])}
        for i in range(start, end):
            cash = CASH_ADD.match(lines[i])
            if PASS_BANNER.match(lines[i]) or (cash and cash.group(1) in amounts):
                actions.append((i, launcher))
    deleted = wrapped = 0
    for index, launcher in sorted(actions, reverse=True):
        if launcher in VENUE_LAUNCHERS:
            guard_flag(index, 1, PROPERTIES_ENABLED)
            wrapped += 1
        else:
            del lines[index]
            deleted += 1
    edits.append(f"mission rewards: {deleted} story lines removed, "
                 f"{wrapped} venue lines gated")


# The six race prizes, paid on every win in showroom menu order. The first win
# is the check, so the payout gates like a side event's: the properties class
# flag plus that race's completion global, which the APACT watcher has not yet
# marked on the run the check eats (no wait separates the prize from the win
# flag). Entry fees are money and stay vanilla, as do second and third place.
SUNSHINE_RACE_PRIZES = [
    (9370, "add_score $player_char money += 400"),
    (9371, "add_score $player_char money += 2000"),
    (9372, "add_score $player_char money += 4000"),
    (9373, "add_score $player_char money += 8000"),
    (9374, "add_score $player_char money += 20000"),
    (9375, "add_score $player_char money += 40000"),
]
SUNSHINE_RACE_MISSION = 82


def suppress_sunshine_race_first_wins():
    start, end = mission_blocks()[SUNSHINE_RACE_MISSION]
    targets = []
    for completion, anchor in SUNSHINE_RACE_PRIZES:
        hits = [i for i in range(start, end) if lines[i] == anchor]
        assert len(hits) == 1, f"sunshine race prize: {anchor!r} matched {len(hits)}"
        targets.append((hits[0], completion))
    for index, completion in sorted(targets, reverse=True):
        guard_replay(index, 1, completion, PROPERTIES_ENABLED)
    edits.append(f"sunshine race first-win prizes gated: {len(targets)} lines")


def suppress_boatyard_first_run_reward():
    # Checkpoint Charlie is replayable with escalating prizes ($8582 counts
    # runs); only the first run is the check, paying 5000 and setting $607.
    # That banner and cash gate on the properties flag; the replay tiers
    # (6000 and up) stay vanilla winnings.
    anchors = [i for i, ln in enumerate(lines) if ln == "$607 = 1"]
    assert len(anchors) == 1, f"boatyard reward: $607 = 1 matched {len(anchors)}"
    a = anchors[0]
    banner = _first(j for j in range(a - 8, a) if lines[j]
                    == "print_with_number_big 'M_PASS' number 5000 time 5000 style 1")
    assert banner is not None and lines[banner + 1] == "add_score $player_char money += 5000", \
        "boatyard reward: first-run 5000 pair not found"
    guard_flag(banner, 2, PROPERTIES_ENABLED)
    edits.append("boatyard first-run reward gated on the properties flag")


def suppress_stunt_jump_rewards():
    # The USJ thread pays escalating cash ($790, plus 100 per jump) per unique
    # jump and 10000 for the last. The REWARD banner and the cash gate on the
    # class flag; the USJ pass text, sound, and stat registration stay.
    for banner, cash in [
        ("print_with_number_big 'REWARD' number $790 time 6000 style 6",
         "add_score $player_char money += $790"),
        ("print_with_number_big 'REWARD' number 10000 time 6000 style 6",
         "add_score $player_char money += 10000"),
    ]:
        hits = [i for i in range(len(lines) - 1)
                if lines[i] == banner and lines[i + 1] == cash]
        assert len(hits) == 1, f"stunt reward: {banner!r} pair matched {len(hits)}"
        guard_flag(hits[0], 2, STUNT_JUMPS_ENABLED)
    edits.append("stunt jump rewards gated on the class flag")


def suppress_rampage_rewards():
    # The RAMPAGE thread pays 50 * n per rampage and a flat 1000 for the last.
    # The cash and REWARD banners gate on the class flag; the RAMP_P and
    # RAMP_A pass texts stay. The flat 1000 add shares its text with other
    # missions, so it anchors on the RAMP_A REWARD banner that follows it.
    banner_all = "print_with_number_big 'REWARD' number 1000 time 6000 style 6"
    singles = ["add_score $player_char money += $1401",
               "print_with_number_big 'REWARD' number $1401 time 6000 style 6",
               banner_all]
    targets = []
    for anchor in singles:
        hits = [i for i, ln in enumerate(lines) if ln == anchor]
        assert len(hits) == 1, f"rampage reward: {anchor!r} matched {len(hits)}"
        targets.append(hits[0])
    thousand = [i for i, ln in enumerate(lines)
                if ln == "add_score $player_char money += 1000"
                and banner_all in lines[i + 1:i + 5]]
    assert len(thousand) == 1, f"rampage reward: final 1000 matched {len(thousand)}"
    targets.append(thousand[0])
    for index in sorted(targets, reverse=True):
        guard_flag(index, 1, RAMPAGES_ENABLED)
    edits.append("rampage rewards gated on the class flag")


# Each side event's first-completion payout lines, wrapped individually (the
# lines between them, wanted-level clears and pass tunes, stay unconditional).
# Completion globals match the SIDE_EVENTS watcher table above.
SIDE_EVENT_CASH_SITES = [
    ("Hotring", 79, 9307, [
        "print_with_number_big 'HOTR_29' number 5000 time 6000 style 6",
        "add_score $player_char money += 5000",
    ]),
    ("Bloodring", 80, 9308, [
        "print_with_number_big 'BLOD_09' number 1000 time 6000 style 6",
        "add_score $player_char money += 1000",
    ]),
    ("Dirtring", 81, 9309, [
        "print_with_number_big 'M_PASS' number 50000 time 5000 style 1",
        "add_score $player_char money += 50000",
        "print_with_number_big 'M_PASS' number 10000 time 5000 style 1",
        "add_score $player_char money += 10000",
        "print_with_number_big 'M_PASS' number 5000 time 5000 style 1",
        "add_score $player_char money += 5000",
    ]),
    ("Downtown Chopper Checkpoint", 84, 9310, [
        "print_with_number_big 'HELI_1B' number 100 time 5000 style 1",
        "add_score $player_char money += 100",
    ]),
    ("Ocean Beach Chopper Checkpoint", 85, 9311, [
        "print_with_number_big 'HELI_1B' number 100 time 5000 style 1",
        "add_score $player_char money += 100",
    ]),
    ("Vice Point Chopper Checkpoint", 86, 9312, [
        "print_with_number_big 'HELI_1B' number 100 time 5000 style 1",
        "add_score $player_char money += 100",
    ]),
    ("Little Haiti Chopper Checkpoint", 87, 9313, [
        "print_with_number_big 'HELI_1B' number 100 time 5000 style 1",
        "add_score $player_char money += 100",
    ]),
    ("Trial by Dirt", 88, 9317, [
        "print_with_number_big 'M_PASS' number $1756 time 5000 style 1",
        "add_score $player_char money += $1756",
    ]),
    ("Test Track", 89, 9318, [
        "print_with_number_big 'M_PASS' number $1774 time 5000 style 1",
        "add_score $player_char money += $1774",
    ]),
    ("PCJ Playground", 90, 9319, [
        "print_with_number_big 'M_PASS' number $1612 time 5000 style 1",
        "add_score $player_char money += $1612",
    ]),
    # Cone Crazy pays from two sites. A completion that sets a record, which the
    # first one always does, gosubs to the record subroutine and is paid $7926
    # there (200, doubling per record); a replay that sets no record is paid a
    # flat literal 200 in the win branch itself, behind an already-completed
    # test. So the first-win payout is the $7926 pair, and the literal 200 pair
    # is replay winnings that stay vanilla.
    ("Cone Crazy", 91, 9320, [
        "print_with_number_big 'M_PASS' number $7926 time 5000 style 1",
        "add_score $player_char money += $7926",
    ]),
    ("RC Raider Pickup", 93, 9316, [
        "print_with_number_big 'M_PASS' number 100 time 5000 style 1",
        "add_score $player_char money += 100",
    ]),
    ("RC Bandit Race", 94, 9314, [
        "add_score $player_char money += 100",
        "print_with_number_big 'M_PASS' number 100 time 5000 style 1",
    ]),
    ("RC Baron Race", 95, 9315, [
        "print_with_number_big 'M_PASS' number 100 time 5000 style 1",
        "add_score $player_char money += 100",
    ]),
]


def suppress_side_event_first_wins():
    # Cone Crazy's no-record replay consolation and Hotring's second and third
    # place prizes are repeatable winnings outside these anchors and stay.
    # Events run highest block first, so the wraps inserted in one block never
    # shift a block still waiting in the snapshot spans; the assert pins the
    # block layout the descending order relies on.
    spans = mission_blocks()
    total = 0
    previous_start = len(lines)
    for name, number, completion, anchors in sorted(
            SIDE_EVENT_CASH_SITES, key=lambda site: -site[1]):
        assert spans[number][0] < previous_start, \
            f"{name}: mission blocks are not in mission-number order"
        previous_start = spans[number][0]
        start, end = spans[number]
        targets = []
        for anchor in anchors:
            hits = [i for i in range(start, end) if lines[i] == anchor]
            assert len(hits) == 1, f"{name}: {anchor!r} matched {len(hits)}"
            targets.append(hits[0])
        for index in sorted(targets, reverse=True):
            guard_replay(index, 1, completion, SIDE_EVENTS_ENABLED)
        total += len(targets)
    edits.append(f"side event first-win payouts gated: {total} lines")


# Every cash add and M_PASS banner that stays unguarded on purpose, keyed by
# mission block (or MAIN) and exact line, with its count. The audit fails on
# any site outside this table, so a new or shifted payout fails the build.
EXPECTED_VANILLA_CASH = {
    # Free-roam skill and income threads.
    ("MAIN", "add_score $player_char money += $726"): 3,
    ("MAIN", "add_score $player_char money += $747"): 1,
    ("MAIN", "add_score $player_char money += 5"): 1,
    ("MAIN", "add_score $player_char money += $1370"): 1,
    # In-mission earnings, not pass rewards.
    ("M25", "add_score $player_char money += 100"): 4,
    ("M32", "add_score $player_char money += 1000"): 1,
    ("M56", "add_score $player_char money += 100"): 1,
    # The finale's money restoration mechanic.
    ("M52", "add_score $player_char money += $4974"): 1,
    ("M52", "add_score $player_char money += $4985"): 1,
    # The rifle range is not a check and stays fully vanilla.
    ("M66", "add_score $player_char money += 500"): 1,
    # Emergency-vehicle earnings and level bonuses stay vanilla grind income.
    ("M75", "add_score $player_char money += $6721"): 1,
    ("M75", "add_score $player_char money += $6723"): 1,
    ("M76", "add_score $player_char money += $6751"): 1,
    ("M76", "add_score $player_char money += 25000"): 1,
    ("M77", "add_score $player_char money += $6844"): 1,
    ("M78", "add_score $player_char money += $6897"): 1,
    ("M92", "add_score $player_char money += 5000"): 1,
    ("M92", "add_score $player_char money += 10"): 10,
    # Side-event repeatable winnings beyond the first completion.
    ("M79", "add_score $player_char money += 1500"): 1,
    ("M79", "add_score $player_char money += 500"): 1,
    ("M80", "add_score $player_char money += 100"): 16,
    ("M83", "add_score $player_char money += 10"): 4,
    ("M83", "add_score $player_char money += 15"): 4,
    ("M83", "add_score $player_char money += 12"): 8,
    ("M83", "add_score $player_char money += 8"): 8,
    ("M83", "add_score $player_char money += 6"): 8,
    ("M91", "add_score $player_char money += 200"): 1,
    ("M96", "add_score $player_char money += 6000"): 1,
    ("M96", "add_score $player_char money += 7000"): 1,
    ("M96", "add_score $player_char money += 8000"): 1,
    ("M96", "add_score $player_char money += 9000"): 1,
    ("M96", "add_score $player_char money += 15000"): 1,
}
EXPECTED_VANILLA_BANNERS = {
    ("M66", "print_with_number_big 'M_PASS' number 500 time 5000 style 1"): 1,
    ("M91", "print_with_number_big 'M_PASS' number 200 time 5000 style 1"): 1,
    ("M92", "print_with_number_big 'M_PASS' number 5000 time 5000 style 1"): 1,
    ("M96", "print_with_number_big 'M_PASS' number 6000 time 5000 style 1"): 1,
    ("M96", "print_with_number_big 'M_PASS' number 7000 time 5000 style 1"): 1,
    ("M96", "print_with_number_big 'M_PASS' number 8000 time 5000 style 1"): 1,
    ("M96", "print_with_number_big 'M_PASS' number 9000 time 5000 style 1"): 1,
    ("M96", "print_with_number_big 'M_PASS' number 15000 time 5000 style 1"): 1,
}
AUDIT_BANNER = re.compile(r"^print_with_number_big 'M_PASS' number \S+ time \d+ style 1$")
AUDIT_CASH = re.compile(r"^add_score \$player_char money \+= (\$?\d+)$")


def _inside_apcash_guard(index):
    # A site is guarded when scanning upward reaches its guard's
    # goto_if_false before any closing :APCASH_ label; a label first means
    # the site sits past the guarded span.
    for j in range(index - 1, max(0, index - 5) - 1, -1):
        if lines[j].startswith(":APCASH_"):
            return False
        if lines[j].startswith("goto_if_false @APCASH_"):
            return True
    return False


def audit_cash_sites():
    # Final gate: rescan the whole built source and require every unguarded
    # positive cash add and every unguarded M_PASS banner to match the pinned
    # tables exactly, both ways.
    context = "MAIN"
    cash_found: dict[tuple, int] = {}
    banner_found: dict[tuple, int] = {}
    for i, line in enumerate(lines):
        header = MISSION_HEADER.match(line)
        if header:
            context = f"M{int(header.group(1))}"
            continue
        if _inside_apcash_guard(i):
            continue
        if AUDIT_CASH.match(line):
            cash_found[(context, line)] = cash_found.get((context, line), 0) + 1
        elif AUDIT_BANNER.match(line):
            banner_found[(context, line)] = banner_found.get((context, line), 0) + 1
    for label, found, expected in [("cash", cash_found, EXPECTED_VANILLA_CASH),
                                   ("banner", banner_found, EXPECTED_VANILLA_BANNERS)]:
        unexpected = {key: n for key, n in found.items() if expected.get(key) != n}
        missing = {key: n for key, n in expected.items() if found.get(key) != n}
        assert not unexpected and not missing, \
            f"cash audit ({label}): unexpected {unexpected}, missing {missing}"
    edits.append("cash audit: every remaining payout is pinned vanilla")


def add_stat_watcher():
    # Rampages and unique stunt jumps each set a dedicated per-instance flag
    # (0->1 on genuine completion, never reset, never reused), so a boot-started
    # watcher copies each flag to its completion global. Checks are UNROLLED per
    # instance: Sanny's dynamic array READ ($dst = $base($idx,Ni)) silently
    # compiles to nothing (only array WRITE round-trips), so a loop cannot read
    # the flags. Rampages $1439..$1473 -> $9180..$9214 (35); stunts $795..$830 ->
    # $9215..$9250 (36); Taxi $369 (persistent career fares) -> $9287..$9296 at
    # every tenth fare.
    body = ["", ":APSTAT", "script_name 'APSTAT'", "", ":APSTAT_LOOP", "wait 1000"]
    checks = ([(f"${1439 + n} == 1", 9180 + n) for n in range(35)]
              + [(f"${795 + n} == 1", 9215 + n) for n in range(36)]
              + [(f"$369 >= {10 * n}", 9286 + n) for n in range(1, 11)])
    for index, (condition, completion) in enumerate(checks):
        label = f"@APSTAT_C{index}"
        body += ["if ", f"  {condition}", f"goto_if_false {label}", f"${completion} = 1", f":APSTAT_C{index}"]
    body += ["goto @APSTAT_LOOP"]
    insert_before(":GEN1", body, "APSTAT rampage+stunt+taxi watcher")
    insert_after("start_new_script @HOT ", ["start_new_script @APSTAT "], "boot start @APSTAT")


def _level_marks(level_var, base, maxlevel, done_label):
    # Mark completion globals base..base+level-1 for the current level, cumulative
    # with a chained early-exit. Unrolled (no dynamic array write, which crashes
    # VC's VM). At the insertion point level_var holds the just-completed level.
    block = []
    for level in range(1, maxlevel + 1):
        block += ["if ", f"  {level_var} >= {level}", f"goto_if_false @{done_label}",
                  f"${base + level - 1} = 1"]
    return [*block, f":{done_label}"]


def add_emergency_instrumentation():
    # Paramedic/Firefighter/Vigilante/Pizza level globals live in a shared
    # mission-scratch pool, valid only while that mission runs, so mark each
    # level at its in-mission completion point rather than from a watcher. At
    # register_*_level the level global holds the just-completed level (1..N).
    for anchor, level_var, base, maxlevel, done in [
        ("register_ambulance_level $6756", "$6756", 9251, 12, "APAMB_DONE"),
        ("register_fire_level $6848", "$6848", 9275, 12, "APFIR_DONE"),
        ("register_vigilante_level $6938", "$6938", 9263, 12, "APVIG_DONE"),
    ]:
        insert_after(anchor, _level_marks(level_var, base, maxlevel, done), f"emergency {level_var}")
    # Pizza levels 1..9 complete just before $7994 advances (pre-increment value
    # is the completed level); level 10 completes at the win flag $389 = 1.
    insert_before("$7994 += 1", _level_marks("$7994", 9297, 9, "APPIZ_DONE"),
                  "emergency pizza levels 1-9")
    insert_after("$389 = 1", ["$9306 = 1"], "emergency pizza level 10")


# Persistent-reward re-gating (Phase 3). When a reward group is shuffled (the
# ASI stamps its config flag from slot_data), the vanilla grant is suppressed and
# the APREWD applier drives it from the AP reward global instead. Indices match
# scm.py: rewards $9518..$9532, packages_shuffled $9533, emergency_shuffled $9534.
# $9008/$9009 are reserved once-guards for the two additive stat rewards.
# The finale active flag, which tops the reserved block and so is the
# foundation's sizing line: Sanny allocates script space up to the highest global
# written, so the top of the block has to be written once or the flag itself
# lands outside it. That same write initialises it, which a new game needs, since
# the layout must be live before any finale runs.
FINALE_ACTIVE = 9659
PACKAGES_SHUFFLED = 9533
EMERGENCY_SHUFFLED = 9534

# Radio randomization, indices matching scm.py. The ASI writes the nine resolve
# globals (station -> itself when its item is owned, else the next unlocked
# station); the scripted set_radio_channel sites read them, so they need no
# flag check of their own: the foundation initializes the map to identity,
# which is vanilla until the ASI overwrites it. The request global carries an
# ASI-posted retune to the APRADIO watcher, encoded station id plus one so the
# zero-initialized global idles.
RADIO_RESOLVE_BASE = 9545
RADIO_REQUEST = 9554

# The minimap unlock global, index matching scm.py. ASI-facing only (its
# shuffled flag sits at $9570 and this unlock at $9571; no gate reads either):
# the ASI hides the radar disc while the flag is set and this global is zero.
MINIMAP_UNLOCK = 9571

# Class-cash config flags, indices matching scm.py. The ASI stamps each to one
# when its check class is enabled, so the class's one-time completion cash is
# suppressed (the AP check is the reward); at zero everything pays vanilla.
# The properties flag gates the venue mission pass cash and Checkpoint
# Charlie's first run.
SIDE_EVENTS_ENABLED = 9572
STUNT_JUMPS_ENABLED = 9573
RAMPAGES_ENABLED = 9574
PROPERTIES_ENABLED = 9575

# The ability lock block, indices matching scm.py: eight lock flags at
# $9576..$9583 then eight unlock globals at $9584..$9591, all ASI-facing only
# (no gate reads them; the ASI enforces the locks per frame and they persist
# inside saves), so the script names none of them.
#
# The content lock block follows it in the same shape: five lock flags at
# $9592..$9596 then five unlock globals at $9597..$9601, in scm.CONTENT_KEYS
# order (hidden packages, rampages, stunt jumps, property purchases, robbable
# stores). No gate reads these either: a whole-class release reaches the script
# through the district block below, which is what a gate reads.
CONTENT_LOCK_FLAG_BASE = 9593
CONTENT_UNLOCK_BASE = 9598

# The district content unlock block follows: one global per class per district,
# a uniform five by eleven grid indexed class-major, so a class and a district
# give a global by formula. These are what a gate actually reads, at every
# granularity, because an item releases every global it covers: a whole-class
# item releases all eleven of its class's, so no gate has to know which
# granularity the seed chose and there is one code path for all three.
#
# A class the seed does not lock has its eleven stamped to 1 at config time (the
# client's config_globals), which is what lets each gate be a single condition
# rather than "not locked OR released", and keeps the toggle invariant: at zero
# locks every gate falls through. A class-district pair holding no content at all
# is stamped 2 instead, which _hold_condition passes just the same: the two are
# apart for the status page, not for any gate.
# Three of the five classes are pickups, so holding them belongs to the ASI and
# the script needs nothing for them. The other two have no icon to hold, so
# their gates belong to the script, and these are the globals those gates read.
DISTRICT_UNLOCK_BASE = 9603
DISTRICTS = [
    "Ocean Beach", "Washington Beach",
    "Vice Point", "Starfish Island",
    "Prawn Island", "Leaf Links",
    "Downtown", "Little Haiti",
    "Little Havana", "Viceport",
    "Escobar International",
]

# scm.CONTENT_KEYS order, which fixes the class-major stride into the block.
# Pinned by a world test, since reordering it would point every gate at another
# class.
CONTENT_KEYS_ORDER = [
    "hidden packages", "rampages", "stunt jumps", "property purchases",
    "robbable stores",
]
STUNT_JUMPS_CLASS = 2
ROBBABLE_STORES_CLASS = 4
DISTRICT_TOP = DISTRICT_UNLOCK_BASE + len(CONTENT_KEYS_ORDER) * len(DISTRICTS) - 1

# The finale warp flag. The ASI raises it once the hidden-packages goal is met
# and the APFIN watcher launches the finale from it (resolve_finale_facts and
# add_finale_warp above). Mirrors scm.FINALE_WARP_GLOBAL, pinned by a world test.
FINALE_WARP = DISTRICT_TOP + 1


def district_unlock(class_index, district):
    assert district in DISTRICTS, f"unknown district {district!r}"
    return (DISTRICT_UNLOCK_BASE + class_index * len(DISTRICTS)
            + DISTRICTS.index(district))


# Which district each of the 36 unique stunt jumps is in, by the id the USJ
# thread writes to $792, and each of the 15 robbable stores, in
# add_stores_knocked_off order. Transcribed from the world's own generated
# district table and pinned against it by a world test.
STUNT_JUMP_DISTRICTS = [
    "Escobar International", "Escobar International", "Escobar International",
    "Escobar International", "Escobar International", "Escobar International",
    "Escobar International", "Escobar International", "Prawn Island",
    "Vice Point", "Downtown", "Downtown",
    "Downtown", "Downtown", "Little Haiti",
    "Little Haiti", "Little Haiti", "Little Havana",
    "Ocean Beach", "Ocean Beach", "Washington Beach",
    "Ocean Beach", "Ocean Beach", "Ocean Beach",
    "Ocean Beach", "Ocean Beach", "Ocean Beach",
    "Ocean Beach", "Vice Point", "Washington Beach",
    "Washington Beach", "Washington Beach", "Washington Beach",
    "Washington Beach", "Washington Beach", "Starfish Island",
]

STORE_DISTRICTS = [
    "Washington Beach", "Vice Point", "Little Havana",
    "Little Havana", "Downtown", "Downtown",
    "Little Haiti", "Vice Point", "Vice Point",
    "Vice Point", "Vice Point", "Vice Point",
    "Vice Point", "Little Havana", "Little Havana",
]

# Reward global -> the vanilla weapon flag or car generator it drives, in
# reward-global order (body armor, chainsaw, .357, flamethrower, sniper, minigun,
# rocket launcher, sea sparrow, rhino, hunter).
PACKAGE_REWARD_APPLY = [
    (9518, "$1309 = 1"), (9519, "$1310 = 1"), (9520, "$1308 = 1"),
    (9521, "$1311 = 1"), (9522, "$1312 = 1"), (9523, "$1313 = 1"),
    (9524, "$1314 = 1"),
    (9525, "switch_car_generator $1977 cars_to_generate_to 101"),
    (9526, "switch_car_generator $1978 cars_to_generate_to 101"),
    (9527, "switch_car_generator $1979 cars_to_generate_to 101"),
]

# The vanilla :PACKAGE grant blocks: label -> (the lines left to run, the count
# gated out behind them) when packages are shuffled. Every block opens with
# player_made_progress, one of the game's 154 completion points, and that point
# belongs to reaching ten more packages rather than to the reward, so it runs
# whoever owns the reward and the stats menu still reads a hundred percent on a
# finished seed. What follows is the help text and the reward itself, which AP
# owns. The hunter block covers both safehouse branches, and the tenth block
# sleeps before its point, so a shuffled seed runs that wait as well: five
# seconds in a thread that goes on to wait again either way.
PACKAGE_BLOCKS = [
    ("PACKAGE_55", [PROGRESS_LINE], 2), ("PACKAGE_111", [PROGRESS_LINE], 2),
    ("PACKAGE_167", [PROGRESS_LINE], 2), ("PACKAGE_223", [PROGRESS_LINE], 2),
    ("PACKAGE_279", [PROGRESS_LINE], 2), ("PACKAGE_335", [PROGRESS_LINE], 2),
    ("PACKAGE_391", [PROGRESS_LINE], 2), ("PACKAGE_447", [PROGRESS_LINE], 2),
    ("PACKAGE_503", [PROGRESS_LINE], 2),
    ("PACKAGE_559", ["wait 5000", PROGRESS_LINE], 10),
]


def guard_span(index, span, flag, label):
    # Wrap `span` lines starting at `index` in an if-flag-zero guard so the grant
    # fires only when the group is NOT shuffled. Inserts the skip label first (so
    # the guard insert does not shift it).
    lines[index + span:index + span] = [f":{label}"]
    lines[index:index] = ["if ", f"  ${flag} == 0", f"goto_if_false @{label}"]
    guard_labels.append(label)


def suppress_package_grants():
    for label, kept, span in PACKAGE_BLOCKS:
        hits = [i for i, ln in enumerate(lines) if ln == f":{label}"]
        assert len(hits) == 1, f"package suppress: :{label} matched {len(hits)}"
        start = hits[0] + 1
        assert lines[start:start + len(kept)] == kept, (
            f"package suppress: :{label} opens with "
            f"{lines[start:start + len(kept)]}, not {kept}")
        guard_span(start + len(kept), span, PACKAGES_SHUFFLED, f"{label}_APGATE")
    edits.append(f"suppress {len(PACKAGE_BLOCKS)} package grant blocks")


def _guard_unique(anchor, span, label):
    hits = [i for i, ln in enumerate(lines) if ln == anchor]
    assert len(hits) == 1, f"suppress {label}: {anchor!r} matched {len(hits)}"
    guard_span(hits[0], span, EMERGENCY_SHUFFLED, label)


def _guard_after(anchor, require_next, span, label):
    # Disambiguate a repeated opcode by the line that must follow it.
    hits = [i for i in range(len(lines) - 1)
            if lines[i] == anchor and lines[i + 1] == require_next]
    assert len(hits) == 1, f"suppress {label}: {anchor!r} + next matched {len(hits)}"
    guard_span(hits[0], span, EMERGENCY_SHUFFLED, label)


def suppress_emergency_grants():
    # Paramedic grants infinite sprint on two paths; suppress both.
    sprint = "set_player_never_gets_tired $player_char infinite_run_to True"
    hits = [i for i, ln in enumerate(lines) if ln == sprint]
    assert len(hits) == 2, f"emergency suppress: sprint matched {len(hits)}"
    for order, index in enumerate(reversed(hits)):
        guard_span(index, 1, EMERGENCY_SHUFFLED, f"APSPRINT_{order}")
    _guard_unique("make_player_fire_proof $player_char fireproof 1", 1, "APFIRE")
    _guard_unique("set_all_taxis_have_nitro 1", 1, "APTAXI")
    # The two additive stat grants share their opcode with the game-init base-max
    # setup, so anchor on the reward-only line that follows each.
    _guard_after("increase_player_max_armour $player_char max_armour += 50",
                 "add_armour_to_char $player_actor armour_to 150", 2, "APARMOUR")
    _guard_after("increase_player_max_health $player_char max_health += 50",
                 "$389 = 1", 1, "APHEALTH")
    edits.append("suppress emergency grants (sprint x2, fire, taxi, armour, health)")


def add_radio_watcher():
    # Retunes the live radio on ASI request. The ASI fixes a vehicle's station
    # byte itself, but only the script channel switches the playing track, so
    # it posts the station here. Station 9 is the MP3 player, which the game
    # remaps to the city ambience: the radio-off soundscape.
    body = ["", ":APRADIO", "script_name 'APRADIO'", "",
            ":APRADIO_LOOP", "wait 0",
            "if ", f"  ${RADIO_REQUEST} >= 1", "goto_if_false @APRADIO_LOOP",
            f"${RADIO_REQUEST} -= 1",
            f"set_radio_channel ${RADIO_REQUEST} -1",
            f"${RADIO_REQUEST} = 0",
            "goto @APRADIO_LOOP"]
    insert_before(":GEN1", body, "APRADIO retune watcher")
    insert_after("start_new_script @HOT ", ["start_new_script @APRADIO "], "boot start @APRADIO")


def redirect_scripted_stations():
    # The vanilla scripts force a music station in 14 places; each immediate
    # becomes its station's resolve global. The two channel-9 calls restore
    # the city ambience, not a music station, and stay as they are.
    pattern = re.compile(r"^set_radio_channel ([0-8]) -1$")
    replaced = 0
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match is None:
            continue
        lines[index] = f"set_radio_channel ${RADIO_RESOLVE_BASE + int(match.group(1))} -1"
        replaced += 1
    assert replaced == 14, f"radio redirect: {replaced} sites (expected 14)"
    edits.append(f"radio redirect: {replaced} scripted stations")


def add_reward_applier():
    # Boot-started watcher: when a reward group is shuffled, apply each owned
    # reward from its reward global. Booleans re-apply idempotently every loop;
    # the two additive stats apply once via the $9008/$9009 guards.
    body = ["", ":APREWD", "script_name 'APREWD'", "", ":APREWD_LOOP", "wait 1000",
            "if ", f"  ${PACKAGES_SHUFFLED} == 1", "goto_if_false @APREWD_EMERGENCY"]
    for index, (reward, grant) in enumerate(PACKAGE_REWARD_APPLY):
        body += ["if ", f"  ${reward} >= 1", f"goto_if_false @APREWD_PKG_{index}",
                 grant, f":APREWD_PKG_{index}"]
    body += ["", ":APREWD_EMERGENCY",
             "if ", f"  ${EMERGENCY_SHUFFLED} == 1", "goto_if_false @APREWD_LOOP"]
    booleans = [
        (9528, "set_player_never_gets_tired $player_char infinite_run_to True"),
        (9529, "make_player_fire_proof $player_char fireproof 1"),
        (9531, "set_all_taxis_have_nitro 1"),
    ]
    for index, (reward, grant) in enumerate(booleans):
        body += ["if ", f"  ${reward} >= 1", f"goto_if_false @APREWD_ABIL_{index}",
                 grant, f":APREWD_ABIL_{index}"]
    body += ["if ", "  $9530 >= 1", "goto_if_false @APREWD_ARMOUR",
             "if ", "  $9008 == 0", "goto_if_false @APREWD_ARMOUR",
             "increase_player_max_armour $player_char max_armour += 50",
             "add_armour_to_char $player_actor armour_to 150",
             "$9008 = 1", ":APREWD_ARMOUR"]
    body += ["if ", "  $9532 >= 1", "goto_if_false @APREWD_HEALTH",
             "if ", "  $9009 == 0", "goto_if_false @APREWD_HEALTH",
             "increase_player_max_health $player_char max_health += 50",
             "$9009 = 1", ":APREWD_HEALTH"]
    body += ["goto @APREWD_LOOP"]
    insert_before(":GEN1", body, "APREWD reward applier")
    insert_after("start_new_script @HOT ", ["start_new_script @APREWD "], "boot start @APREWD")


# Foundation: initialize the radio resolve map to identity (vanilla until the
# ASI overwrites it) and reference the highest reserved global once so Sanny
# sizes the whole $9000..N block as real zero-initialized globals. The last
# line must equal scm.highest_reserved_global() (now the finale active flag
# $9658: 26 unlocks + 482 completions + 15 reward globals + 3 config flags + 19
# radio globals + 15 ownership globals + the minimap flag and unlock + 4
# class-cash flags + 16 ability globals + 10 content globals + 55 district
# content globals + the warp flag + the active flag, 649 in all, from $9010 up;
# the ten below that are the seed hash and the bookkeeping scratch).
#
# That last line does double duty for the active flag, which is the top: it is
# also the flag's initialization, so a new game starts with the ambient pickup
# layout live. It sits above the boot thread's own loop label, so it runs once
# when the thread starts and cannot clear a flag a running finale has raised.
# add_markers.py anchors on that line.
foundation = [f"${RADIO_RESOLVE_BASE + station} = {station}" for station in range(9)]
foundation += [f"${RADIO_REQUEST} = 0", f"${PROPERTIES_ENABLED} = 0",
               f"${FINALE_WARP} = 0", f"${FINALE_ACTIVE} = 0"]
insert_after("script_name 'HOT'", foundation,
             f"foundation radio identity + ${FINALE_WARP} = 0 + ${FINALE_ACTIVE} = 0")
check_play_order()
check_gate_mainland_terms()
resolve_passed_flags()
resolve_finale_facts()
for launcher, gate_conditions, completion_global in MISSIONS:
    try:
        wire(launcher, gate_conditions, completion_global)
    except NonStandard as reason:
        skipped.append(f"{launcher}: {reason}")
mainland_shared, mainland_crossings, west_gate_open = relocate_mainland_open()
add_area_watcher(mainland_shared, mainland_crossings,
                 sever_starfish_east_open(), west_gate_open)
add_package_watcher()
add_finale_flag()
add_finale_warp()
add_purchase_completions()
defer_safehouse_grants()
check_property_saves()
defer_business_saves()
gate_pole_position_completion()
gate_sunshine_import_lists()
add_store_completions()
add_shop_completions()
# Content-lock gates.
gate_stunt_jumps()
gate_store_robberies()
add_activity_gates()
add_activity_watcher()
suppress_mission_rewards()
suppress_boatyard_first_run_reward()
suppress_side_event_first_wins()
suppress_sunshine_race_first_wins()
suppress_stunt_jump_rewards()
suppress_rampage_rewards()
add_stat_watcher()
add_emergency_instrumentation()
suppress_package_grants()
suppress_emergency_grants()
add_reward_applier()
add_radio_watcher()
redirect_scripted_stations()
audit_cash_sites()

built_progress_points = sum(1 for line in lines if line == PROGRESS_LINE)
assert built_progress_points == source_progress_points, (
    f"the build carries {built_progress_points} completion points where the "
    f"decompile has {source_progress_points}; a suppression is deleting the "
    "percentage the stats menu shows")
guard_line_positions = {}
for index, line in enumerate(lines):
    if line.startswith("goto_if_false @") or line.startswith(":"):
        guard_line_positions.setdefault(line, index)
guarded_points = []
for guard_label in guard_labels:
    opens = guard_line_positions.get(f"goto_if_false @{guard_label}")
    closes = guard_line_positions.get(f":{guard_label}")
    # A guard whose own lines have gone is not an exemption from the one check
    # that catches silent suppression: it means the build no longer reads the way
    # this check assumes, which is exactly when it must speak up.
    assert opens is not None and closes is not None, (
        f"guard {guard_label} has no goto and label pair left in the build, so "
        "what it covers cannot be checked")
    if PROGRESS_LINE in lines[opens:closes]:
        guarded_points.append(guard_label)
assert not guarded_points, (
    f"these guards cover a completion point, so the percentage the stats menu "
    f"shows can no longer reach a hundred: {guarded_points}")

with open(DST, "wb") as handle:
    handle.write(nl.join(lines).encode("latin-1"))

wired = sum(1 for d in edits if d.startswith("completion"))
print(f"wired {wired} missions, skipped {len(skipped)}, {len(edits)} edits total")
if skipped:
    print("SKIPPED (need bespoke handling):")
    for reason in skipped:
        print(f"  - {reason}")
