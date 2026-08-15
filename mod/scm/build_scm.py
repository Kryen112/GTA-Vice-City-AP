"""Apply AP edits to a clean VC decompile: foundation, per-mission gate +
completion write + reward suppression, and the area watcher that opens the
mainland and the two Starfish Island gates on their AP items.

Config per mission is just (launcher_label, gate_conditions, completion_global).
The launcher's guard flag, gate-block label, and loop-back label are derived
from its uniform structure, and the cash/banner reward is auto-detected near the
mission's passed-flag assignment. Every anchor is asserted, so a bad match fails
loudly. Reads SRC, writes DST; line endings preserved.
"""
import re
import sys

SRC, DST = sys.argv[1], sys.argv[2]

# (launcher, [(unlock_global, count), ...], completion_global). Gate list empty
# = free mission. Order mirrors the strands in the spec.
MISSIONS = [
    # Rosenberg (9010)
    ("HOT", [], 9032), ("LAW1", [(9010, 1)], 9033), ("LAW2", [(9010, 2)], 9034),
    ("LAW3", [(9010, 3)], 9035), ("LAW4", [(9010, 4)], 9036),
    # Cortez (9011)
    ("GEN1", [(9011, 1)], 9037), ("GEN2", [(9011, 2)], 9038),
    ("GEN3", [(9011, 3)], 9039), ("GEN4", [(9011, 4)], 9040),
    ("GEN5", [(9011, 5)], 9041),
    # Diaz (9012). Rub Out additionally needs Lance rescued in Death Row.
    ("BAR1", [(9012, 1)], 9042), ("BAR2", [(9012, 2)], 9043),
    ("BAR3", [(9012, 3)], 9044), ("BAR4", [(9012, 4)], 9045),
    ("BAR5", [(9012, 5), (9013, 1)], 9046),
    # Death Row (9013)
    ("KEN1", [(9013, 1)], 9047),
    # Avery (9014): Four Iron, Two Bit Hit, Demolition Man
    ("SER1", [(9014, 1)], 9048), ("SER3", [(9014, 2)], 9049), ("SER2", [(9014, 3)], 9050),
    # Phil Cassidy (9015)
    ("PHI1", [(9015, 1)], 9051), ("PHI2", [(9015, 2)], 9052),
    # Vercetti Protection (9016)
    ("PRO1", [(9016, 1)], 9053),
    ("PRO2", [(9016, 2)], 9054),
    ("PRO3", [(9016, 3)], 9055),
    # Big Mitch Baker (9017)
    ("BIK1", [(9017, 1)], 9056), ("BIK2", [(9017, 2)], 9057), ("BIK3", [(9017, 3)], 9058),
    # Umberto Robina (9018)
    ("CUB1", [(9018, 1)], 9059), ("CUB2", [(9018, 2)], 9060),
    ("CUB3", [(9018, 3)], 9061), ("CUB4", [(9018, 4)], 9062),
    # Auntie Poulet (9019)
    ("HAT1", [(9019, 1)], 9063), ("HAT2", [(9019, 2)], 9064), ("HAT3", [(9019, 3)], 9065),
    # Love Fist (9020)
    ("ROC1", [(9020, 1)], 9066), ("ROC2", [(9020, 2)], 9067), ("ROC3", [(9020, 3)], 9068),
    # Mr. Black (9021)
    ("ASSIN_1", [(9021, 1)], 9069), ("ASSIN_2", [(9021, 2)], 9070), ("ASSIN_3", [(9021, 3)], 9071),
    ("ASSIN_4", [(9021, 4)], 9072), ("ASSIN_5", [(9021, 5)], 9073),
    # Vercetti Finale (9022, after the protection strand 9016>=3). Cap the
    # Collector keeps its vanilla asset prerequisite, read from the vanilla
    # globals: Hit the Courier passed ($273), Cop Land passed ($268), and the
    # owned-asset count $1175 at seven or more (the CELL controller required
    # $1175 > 6). The last mission also mirrors logic's Mainland Access
    # requirement ($9030): its launcher only activates once Cap the Collector
    # passes on the mainland, so the condition is already true whenever it can
    # fire.
    ("FIN1", [(9022, 1), (9016, 3), (268, 1), (273, 1), (1175, 7)], 9074),
    ("FIN2", [(9022, 2), (9016, 3), (9030, 1)], 9075),
    # Venue strands also require their property bought, read from the venue
    # purchase's completion global (set at the buy cutscene, save-persisted),
    # and owned, read from the ownership global its AP item drives.
    # Malibu Club (9023, bought $9337, owned $9405)
    ("BANK1", [(9023, 1), (9337, 1), (9405, 1)], 9347),
    ("BANK2", [(9023, 2), (9337, 1), (9405, 1)], 9348),
    ("BANK3", [(9023, 3), (9337, 1), (9405, 1)], 9349),
    ("BANK4", [(9023, 4), (9337, 1), (9405, 1)], 9350),
    # Film Studio (9024, bought $9334, owned $9402)
    ("PORN1", [(9024, 1), (9334, 1), (9402, 1)], 9351),
    ("PORN2", [(9024, 2), (9334, 1), (9402, 1)], 9352),
    ("PORN3", [(9024, 3), (9334, 1), (9402, 1)], 9353),
    ("PORN4", [(9024, 4), (9334, 1), (9402, 1)], 9354),
    # Printworks (9025, bought $9332, owned $9400)
    ("COU1", [(9025, 1), (9332, 1), (9400, 1)], 9355),
    ("COU2", [(9025, 2), (9332, 1), (9400, 1)], 9356),
    # Kaufman Cabs (9026, bought $9336, owned $9404)
    ("TWAR1", [(9026, 1), (9336, 1), (9404, 1)], 9357),
    ("TWAR2", [(9026, 2), (9336, 1), (9404, 1)], 9358),
    ("TWAR3", [(9026, 3), (9336, 1), (9404, 1)], 9359),
    # Cherry Popper (9027, bought $9335, owned $9403; the buy cutscene is also
    # what starts its launcher). Boatyard (9028) and Sunshine Autos (9029) are
    # activity launchers with no passed-flag guard, wired bespoke in
    # ACTIVITIES; their threads too start only at the buy cutscene, which
    # carries the purchase condition.
    ("ICE1", [(9027, 1), (9335, 1), (9403, 1)], 9360),
]

with open(SRC, "rb") as handle:
    raw = handle.read()
nl = "\r\n" if b"\r\n" in raw else "\n"
lines = raw.decode("latin-1").split(nl)
edits = []


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
        for global_index, count in gate_conditions:
            block += ["if ", f"  ${global_index} >= {count}", f"goto_if_false @{loopback}"]
        insert_after(f":{gate_block}", block, f"gate {launcher} {gate_conditions}")
    edits.append(f"completion {launcher} ${completion_global}")
    # Reward: strip the M_PASS "$N" banner and the positive cash add near each
    # passed-flag assignment.
    removed_total = 0
    for start in [i for i, ln in enumerate(lines) if ln == f"{flag} = 1"]:
        drop = [j for j in range(start + 1, min(start + 19, len(lines)))
                if re.match(r"^print_with_number_big 'M_PASS' number \d+ ", lines[j])
                or re.match(r"^add_score \$player_char money \+= \d+$", lines[j])]
        for j in sorted(drop, reverse=True):
            del lines[j]
        removed_total += len(drop)
    if removed_total:
        edits.append(f"reward {launcher}: removed {removed_total} line(s)")


def relocate_mainland_open():
    # Extracts Phnom Penh's mainland-open routine and splits out the Starfish
    # west-gate piece (the $1779 swap and its bridge-span road switches): the
    # mainland part fires on Mainland Access alone, the west gate only when
    # Starfish Island Access is also held, since that gate is the only barrier
    # on the island's mainland crossing.
    anchor = [i for i, ln in enumerate(lines) if ln == "$passed_COK2_Phnom_Penh_86 = 1"]
    assert len(anchor) == 1, f"mainland: passed anchor matched {len(anchor)}"
    start = next(j for j in range(anchor[0], anchor[0] + 20) if lines[j] == "$847 = 1")
    end = next(j for j in range(start, start + 40) if lines[j] == "play_announcement 1")
    block = lines[start:end + 1]
    assert 20 <= len(block) <= 32 and "delete_object $1781" in block, \
        f"mainland: extracted block looks wrong ({len(block)} lines)"
    del lines[start:end + 1]
    west_start = block.index("delete_object $1779") - 2
    west_gate = block[west_start:west_start + 5]
    assert west_gate[0].startswith("switch_ped_roads_on -787.8") \
        and west_gate[4] == "dont_remove_object $1779", \
        f"mainland: west-gate piece looks wrong ({west_gate})"
    mainland = block[:west_start] + block[west_start + 5:]
    edits.append(f"relocated mainland-open ({len(mainland)} + {len(west_gate)} lines)")
    return mainland, west_gate


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
PURCHASES = [
    ("BUYPRO1", 9332), ("CARBUY1", 9333), ("BUYPRO2", 9334), ("ICECUT", 9335),
    ("TAXCUT", 9336), ("BUYPRO3", 9337), ("BOATBY", 9338), ("BUYPRO4", 9339),
    ("BUYPRO5", 9340), ("LNKVBUY", 9341), ("HYCOBUY", 9342), ("OCHEBUY", 9343),
    ("WASHBUY", 9344), ("VCPTBUY", 9345), ("SKUMBUY", 9346),
]


def add_purchase_completions():
    for label, completion in PURCHASES:
        insert_after(f"script_name '{label}'", [f"${completion} = 1"], f"purchase {label} ${completion}")


# Property ownership globals, indices matching scm.py: one per purchasable
# property in purchase order ($9400 Printworks .. $9414 Skumole Shack), written
# by the ASI when the ownership item arrives (or all stamped to 1 when the
# properties class is off, the vanilla collapse). Every property grant reads
# bought AND owned.
OWNERSHIP_SUNSHINE = 9401
OWNERSHIP_POLE_POSITION = 9407
OWNERSHIP_TOP = 9414

# Safehouse save threads: (save thread, ownership global, garage grant lines
# moved out of the buy cutscene). Each SAVEn thread is started only by its buy
# cutscene and persists inside saves, so gating its body on the ownership
# global defers the save pickup until the property is bought and owned in
# either order, and the garage changes ride the same gate. The buy cutscene
# keeps its camera work, money, blip swap, and owned-property stat.
SAFEHOUSES = [
    ("SAVE1", 9408, ["change_garage_type $663 change_to_type 16"]),   # El Swanko Casa
    ("SAVE2", 9409, ["change_garage_type $655 change_to_type 26"]),   # Links View Apartment
    ("SAVE3", 9410, ["change_garage_type $667 change_to_type 17",     # Hyman Condo
                     "change_garage_type $668 change_to_type 18",
                     "change_garage_type $669 change_to_type 24"]),
    ("SAVE4", 9412, []),                                              # 1102 Washington Street
    ("SAVE5", 9411, ["change_garage_type $659 change_to_type 25"]),   # Ocean Heights Apartment
    ("SAVE6", 9413, []),                                              # Vice Point
    ("SAVE7", 9414, []),                                              # Skumole Shack
]


def defer_safehouse_grants():
    for save_thread, ownership, garage_lines in SAFEHOUSES:
        for grant in garage_lines:
            hits = [i for i, ln in enumerate(lines) if ln == grant]
            assert len(hits) == 1, f"safehouse {save_thread}: {grant!r} matched {len(hits)}"
            del lines[hits[0]]
        gate = [f":AP{save_thread}", "wait 250",
                "if ", f"  ${ownership} >= 1", f"goto_if_false @AP{save_thread}",
                *garage_lines]
        insert_after(f"script_name '{save_thread}'", gate,
                     f"safehouse {save_thread} ownership ${ownership}")


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


def gate_sunshine_import_completion():
    # The Sunshine Autos asset completes when the import garage's last list
    # fills. The recognition branch re-polls every loop, so lists filled
    # before ownership complete once the item arrives.
    anchor = [i for i, ln in enumerate(lines) if ln == ":IMPORT1_87"]
    assert len(anchor) == 1, f"sunshine import: :IMPORT1_87 matched {len(anchor)}"
    i = anchor[0]
    assert lines[i + 1] == "if " and lines[i + 2] == "  $1107 == 0" \
        and lines[i + 3] == "goto_if_false @IMPORT1_822", \
        f"sunshine import: branch shape looks wrong ({lines[i + 1:i + 4]})"
    lines[i + 4:i + 4] = ["if ", f"  ${OWNERSHIP_SUNSHINE} >= 1",
                          "goto_if_false @IMPORT1_822"]
    edits.append(f"sunshine import completion owned ${OWNERSHIP_SUNSHINE}")


def add_store_completions():
    # Each of the 15 store robberies calls add_stores_knocked_off; mark that
    # store's completion right after it. Source order maps to $9317..$9331.
    sites = [i for i, ln in enumerate(lines) if ln == "add_stores_knocked_off 1"]
    assert len(sites) == 15, f"stores: found {len(sites)} sites (expected 15)"
    for k in range(len(sites) - 1, -1, -1):
        lines[sites[k] + 1:sites[k] + 1] = [f"${9317 + k} = 1"]
    edits.append(f"stores: {len(sites)} completions $9317..$9331")


def add_package_watcher():
    # Hidden packages are count-only in the SCM (get_collectable1s_collected),
    # so mark package N's completion global ($9075+N) once at least N are
    # collected. Unrolled per package with a chained early-exit (the counts are
    # cumulative, so the first unmet threshold ends the sweep). VC's script VM
    # does NOT execute Sanny's dynamic global-array access (a read silently
    # drops, a write crashes the game on use), so no array indexing here.
    # $9006 is an unused reserved scratch global.
    body = ["", ":APPKG", "script_name 'APPKG'", "",
            ":APPKG_LOOP", "wait 500",
            "get_collectable1s_collected $9006"]
    for count in range(1, 101):
        body += ["if ", f"  $9006 >= {count}", "goto_if_false @APPKG_DONE", f"${9075 + count} = 1"]
    body += [":APPKG_DONE", "goto @APPKG_LOOP"]
    insert_before(":GEN1", body, "APPKG package watcher")
    insert_after("start_new_script @HOT ", ["start_new_script @APPKG "], "boot start @APPKG")


def add_area_watcher(mainland_block, east_gate, west_gate):
    # One watcher, three independent branches per loop: the mainland opens on
    # Mainland Access ($9030, once-guarded by the vanilla flag $847 it sets);
    # the Starfish east gate opens on Starfish Island Access ($9031); the west
    # gate opens only with both items, since it is the sole barrier on the
    # island's mainland crossing. The gate branches once-guard on the reserved
    # scratch globals $9004 (east) and $9007 (west); the vanilla flag $1157
    # stays with the phone call in CELL, which would block a watcher keyed on
    # it if the call fired first.
    body = ["", ":APAREA", "script_name 'APAREA'", "", ":APAREA_LOOP", "wait 500",
            "if ", "  $9030 >= 1", "goto_if_false @APAREA_STAR",
            "if ", "  $847 == 0", "goto_if_false @APAREA_STAR",
            *mainland_block,
            ":APAREA_STAR",
            "if ", "  $9031 >= 1", "goto_if_false @APAREA_LOOP",
            "if ", "  $9004 == 0", "goto_if_false @APAREA_WEST",
            "$9004 = 1",
            *east_gate,
            ":APAREA_WEST",
            "if ", "  $9030 >= 1", "goto_if_false @APAREA_LOOP",
            "if ", "  $9007 == 0", "goto_if_false @APAREA_LOOP",
            "$9007 = 1",
            *west_gate,
            "goto @APAREA_LOOP"]
    insert_before(":GEN1", body, "APAREA watcher thread")
    insert_after("start_new_script @HOT ", ["start_new_script @APAREA "], "boot start @APAREA")


# Activity launchers (Boatyard's Checkpoint Charlie, Sunshine Autos Races) are
# repeatable and have no passed-flag guard, so they are wired bespoke: a gate at
# the launcher top and completion from the vanilla win flags via the APACT
# watcher. Each also requires its property's ownership global; the purchase
# condition is implicit, since these threads start only at the buy cutscene.
# (launcher-10 label, [(global, count), ...], loop-back label.)
ACTIVITIES = [
    ("COKRUN_10", [(9028, 1), (9406, 1)], "COKRUN_345"),
    ("RACES_10", [(9029, 1), (9401, 1)], "RACES_121"),
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
# Order matches the spec's side_events block ($9303..$9316).
SIDE_EVENTS = [
    (1597, 9303), (1598, 9304), (55, 9305),                  # Hotring, Bloodring, Dirtring
    (1584, 9306), (1585, 9307), (1586, 9308), (1587, 9309),  # chopper checkpoints
    (8241, 9310), (8485, 9311), (8156, 9312),                # RC Bandit, Baron, Raider
    (363, 9313), (364, 9314), (339, 9315), (351, 9316),      # Trial, Test Track, PCJ, Cone
]


def add_activity_watcher():
    # Boot-started watcher that polls vanilla win flags and marks completions:
    # Checkpoint Charlie ($607 -> $9361), the six Sunshine Autos races (all of
    # $1588..$1593 -> $9362), and the 14 side events (each flag -> its global).
    # Each check is independent except the races, which require all six.
    body = ["", ":APACT", "script_name 'APACT'", "",
            ":APACT_LOOP", "wait 1000",
            "if ", "  $607 == 1", "goto_if_false @APACT_RACES",
            "$9361 = 1",
            "", ":APACT_RACES"]
    for race_flag in range(1588, 1594):
        body += ["if ", f"  ${race_flag} == 1", "goto_if_false @APACT_SIDE"]
    body += ["$9362 = 1", "", ":APACT_SIDE"]
    for index, (win_flag, completion_global) in enumerate(SIDE_EVENTS):
        skip = "@APACT_LOOP" if index == len(SIDE_EVENTS) - 1 else f"@APACT_EVENT_{index}"
        body += ["if ", f"  ${win_flag} == 1", f"goto_if_false {skip}", f"${completion_global} = 1"]
        if index != len(SIDE_EVENTS) - 1:
            body += [f":APACT_EVENT_{index}"]
    body += ["goto @APACT_LOOP"]
    insert_before(":GEN1", body, "APACT activity + side-event watcher")
    insert_after("start_new_script @HOT ", ["start_new_script @APACT "], "boot start @APACT")


def suppress_activity_rewards():
    # Checkpoint Charlie pays 5000 then a 6000 time bonus through the M_PASS
    # banner around its win flag ($607 = 1); the AP check is the reward, so strip
    # both like the story missions. Anchored on the unique completion flag, since
    # the mission block itself carries a script_name. Sunshine's per-race prize
    # money is activity winnings, not a mission-pass reward, so it stays.
    anchors = [i for i, ln in enumerate(lines) if ln == "$607 = 1"]
    assert len(anchors) == 1, f"activity reward: $607 = 1 matched {len(anchors)}"
    a = anchors[0]
    drop = [j for j in range(a - 6, a + 9)
            if 0 <= j < len(lines)
            and (re.match(r"^print_with_number_big 'M_PASS' number \d+ ", lines[j])
                 or re.match(r"^add_score \$player_char money \+= \d+$", lines[j]))]
    assert len(drop) == 4, f"activity reward: expected 4 lines, found {len(drop)}"
    for j in sorted(drop, reverse=True):
        del lines[j]
    edits.append(f"activity reward COKERUN: removed {len(drop)} line(s)")


def add_stat_watcher():
    # Rampages and unique stunt jumps each set a dedicated per-instance flag
    # (0->1 on genuine completion, never reset, never reused), so a boot-started
    # watcher copies each flag to its completion global. Checks are UNROLLED per
    # instance: Sanny's dynamic array READ ($dst = $base($idx,Ni)) silently
    # compiles to nothing (only array WRITE round-trips), so a loop cannot read
    # the flags. Rampages $1439..$1473 -> $9176..$9210 (35); stunts $795..$830 ->
    # $9211..$9246 (36); Taxi $369 (persistent career fares) -> $9283..$9292 at
    # every tenth fare.
    body = ["", ":APSTAT", "script_name 'APSTAT'", "", ":APSTAT_LOOP", "wait 1000"]
    checks = ([(f"${1439 + n} == 1", 9176 + n) for n in range(35)]
              + [(f"${795 + n} == 1", 9211 + n) for n in range(36)]
              + [(f"$369 >= {10 * n}", 9282 + n) for n in range(1, 11)])
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
        ("register_ambulance_level $6756", "$6756", 9247, 12, "APAMB_DONE"),
        ("register_fire_level $6848", "$6848", 9271, 12, "APFIR_DONE"),
        ("register_vigilante_level $6938", "$6938", 9259, 12, "APVIG_DONE"),
    ]:
        insert_after(anchor, _level_marks(level_var, base, maxlevel, done), f"emergency {level_var}")
    # Pizza levels 1..9 complete just before $7994 advances (pre-increment value
    # is the completed level); level 10 completes at the win flag $389 = 1.
    insert_before("$7994 += 1", _level_marks("$7994", 9293, 9, "APPIZ_DONE"),
                  "emergency pizza levels 1-9")
    insert_after("$389 = 1", ["$9302 = 1"], "emergency pizza level 10")


# Persistent-reward re-gating (Phase 3). When a reward group is shuffled (the
# ASI stamps its config flag from slot_data), the vanilla grant is suppressed and
# the APREWD applier drives it from the AP reward global instead. Indices match
# scm.py: rewards $9363..$9377, packages_shuffled $9378, emergency_shuffled $9379.
# $9008/$9009 are reserved once-guards for the two additive stat rewards.
PACKAGES_SHUFFLED = 9378
EMERGENCY_SHUFFLED = 9379

# Radio randomization, indices matching scm.py. The ASI writes the nine resolve
# globals (station -> itself when its item is owned, else the next unlocked
# station); the scripted set_radio_channel sites read them, so they need no
# flag check of their own: the foundation initializes the map to identity,
# which is vanilla until the ASI overwrites it. The request global carries an
# ASI-posted retune to the APRADIO watcher, encoded station id plus one so the
# zero-initialized global idles.
RADIO_RESOLVE_BASE = 9390
RADIO_REQUEST = 9399

# Reward global -> the vanilla weapon flag or car generator it drives, in
# reward-global order (body armor, chainsaw, .357, flamethrower, sniper, minigun,
# rocket launcher, sea sparrow, rhino, hunter).
PACKAGE_REWARD_APPLY = [
    (9363, "$1309 = 1"), (9364, "$1310 = 1"), (9365, "$1308 = 1"),
    (9366, "$1311 = 1"), (9367, "$1312 = 1"), (9368, "$1313 = 1"),
    (9369, "$1314 = 1"),
    (9370, "switch_car_generator $1977 cars_to_generate_to 101"),
    (9371, "switch_car_generator $1978 cars_to_generate_to 101"),
    (9372, "switch_car_generator $1979 cars_to_generate_to 101"),
]

# The vanilla :PACKAGE grant blocks: label -> lines after it (progress + help +
# grant) to gate out when packages are shuffled. The hunter block covers both
# safehouse branches.
PACKAGE_BLOCKS = [
    ("PACKAGE_55", 3), ("PACKAGE_111", 3), ("PACKAGE_167", 3),
    ("PACKAGE_223", 3), ("PACKAGE_279", 3), ("PACKAGE_335", 3),
    ("PACKAGE_391", 3), ("PACKAGE_447", 3), ("PACKAGE_503", 3),
    ("PACKAGE_559", 12),
]


def guard_span(index, span, flag, label):
    # Wrap `span` lines starting at `index` in an if-flag-zero guard so the grant
    # fires only when the group is NOT shuffled. Inserts the skip label first (so
    # the guard insert does not shift it).
    lines[index + span:index + span] = [f":{label}"]
    lines[index:index] = ["if ", f"  ${flag} == 0", f"goto_if_false @{label}"]


def suppress_package_grants():
    for label, span in PACKAGE_BLOCKS:
        hits = [i for i, ln in enumerate(lines) if ln == f":{label}"]
        assert len(hits) == 1, f"package suppress: :{label} matched {len(hits)}"
        guard_span(hits[0] + 1, span, PACKAGES_SHUFFLED, f"{label}_APGATE")
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
        (9373, "set_player_never_gets_tired $player_char infinite_run_to True"),
        (9374, "make_player_fire_proof $player_char fireproof 1"),
        (9376, "set_all_taxis_have_nitro 1"),
    ]
    for index, (reward, grant) in enumerate(booleans):
        body += ["if ", f"  ${reward} >= 1", f"goto_if_false @APREWD_ABIL_{index}",
                 grant, f":APREWD_ABIL_{index}"]
    body += ["if ", "  $9375 >= 1", "goto_if_false @APREWD_ARMOUR",
             "if ", "  $9008 == 0", "goto_if_false @APREWD_ARMOUR",
             "increase_player_max_armour $player_char max_armour += 50",
             "add_armour_to_char $player_actor armour_to 150",
             "$9008 = 1", ":APREWD_ARMOUR"]
    body += ["if ", "  $9377 >= 1", "goto_if_false @APREWD_HEALTH",
             "if ", "  $9009 == 0", "goto_if_false @APREWD_HEALTH",
             "increase_player_max_health $player_char max_health += 50",
             "$9009 = 1", ":APREWD_HEALTH"]
    body += ["goto @APREWD_LOOP"]
    insert_before(":GEN1", body, "APREWD reward applier")
    insert_after("start_new_script @HOT ", ["start_new_script @APREWD "], "boot start @APREWD")


# Foundation: initialize the radio resolve map to identity (vanilla until the
# ASI overwrites it) and reference the highest reserved global once so Sanny
# sizes the whole $9000..N block as real zero-initialized globals. The last
# line must equal scm.highest_reserved_global() (now the Skumole Shack
# ownership global $9414: 22 unlocks + 331 completions + 15 reward globals +
# 3 config flags + 19 radio globals + 15 ownership globals above $9000).
# add_markers.py anchors on that line.
foundation = [f"${RADIO_RESOLVE_BASE + station} = {station}" for station in range(9)]
foundation += [f"${RADIO_REQUEST} = 0", f"${OWNERSHIP_TOP} = 0"]
insert_after("script_name 'HOT'", foundation, f"foundation radio identity + ${OWNERSHIP_TOP} = 0")
for launcher, gate_conditions, completion_global in MISSIONS:
    try:
        wire(launcher, gate_conditions, completion_global)
    except NonStandard as reason:
        skipped.append(f"{launcher}: {reason}")
mainland_open, west_gate_open = relocate_mainland_open()
add_area_watcher(mainland_open, sever_starfish_east_open(), west_gate_open)
add_package_watcher()
add_purchase_completions()
defer_safehouse_grants()
gate_pole_position_completion()
gate_sunshine_import_completion()
add_store_completions()
add_activity_gates()
add_activity_watcher()
suppress_activity_rewards()
add_stat_watcher()
add_emergency_instrumentation()
suppress_package_grants()
suppress_emergency_grants()
add_reward_applier()
add_radio_watcher()
redirect_scripted_stations()

with open(DST, "wb") as handle:
    handle.write(nl.join(lines).encode("latin-1"))

wired = sum(1 for d in edits if d.startswith("completion"))
print(f"wired {wired} missions, skipped {len(skipped)}, {len(edits)} edits total")
if skipped:
    print("SKIPPED (need bespoke handling):")
    for reason in skipped:
        print(f"  - {reason}")
