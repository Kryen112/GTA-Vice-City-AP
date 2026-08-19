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
# = free mission. Order mirrors the strands in the spec. The first gate of a
# gated mission is always its own strand's progressive unlock, and those unlocks
# occupy this block, which check_play_order uses to group the table by strand.
UNLOCK_FIRST, UNLOCK_LAST = 9010, 9029
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
    # Avery (9014): Four Iron, Demolition Man, Two Bit Hit. The mission threads
    # are named out of order (SERG1, SERG3, SERG2), the launchers are not.
    ("SER1", [(9014, 1)], 9048), ("SER2", [(9014, 2)], 9049), ("SER3", [(9014, 3)], 9050),
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


def _content_unlocked_guard(lock_flag, unlock, label):
    # A content class is held while its lock flag is set and its unlock global
    # is still zero. Passing means either: the seed never selected the key, or
    # the item has arrived. At zero flags every gate falls through, the toggle
    # invariant.
    return ["if or", f"  ${lock_flag} == 0", f"  ${unlock} >= 1",
            f"goto_if_false @{label}"]


def gate_stunt_jumps():
    # The USJ thread resolves a jump at one point: `if $794 == 1`, reached only
    # through @USJ_5369, which clears $794 as each attempt begins. Everything
    # that credits a jump sits behind that test, so one guard in front of it
    # holds the whole class: no per-jump flag ($795..$830) sets, so the APSTAT
    # watcher never sees one and no check fires; the 36-counter $791 does not
    # advance; player_made_progress and register_unique_jump_found do not run,
    # so the vanilla completion percentage and jump stat do not move either; and
    # the pass text and cash never print. The jump still flies and the slow-motion camera
    # still resolves, since the guard sits after set_time_scale and
    # restore_camera_jumpcut. @USJ_7497 is the thread's own did-not-land path,
    # straight back to the loop, so a held jump reads exactly as a failed one
    # and stays re-doable forever.
    anchor = "  $794 == 1"
    hits = [i for i, ln in enumerate(lines) if ln == anchor]
    assert len(hits) == 1, f"stunt jump gate: {anchor!r} matched {len(hits)}"
    index = hits[0] - 1
    assert lines[index] == "if ", f"stunt jump gate: expected `if ` at {index}"
    assert lines[hits[0] + 1] == "goto_if_false @USJ_7497", \
        f"stunt jump gate: unexpected false target {lines[hits[0] + 1]!r}"
    lines[index:index] = _content_unlocked_guard(
        STUNT_JUMPS_LOCK_FLAG, STUNT_JUMPS_UNLOCK, "USJ_7497")
    edits.append("stunt jump credit gated on the content lock")


def gate_store_robberies():
    # The 15 stores are two thread families sharing two robbery handlers:
    # @SHOP5_1010 for the 12 street stores (gosub'd from SHOP1..SHOP5) and
    # @HARD3_2856 for the 3 hardware stores (from HARD1..HARD3). Each handler
    # opens on `not is_char_dead` and then tests
    # `is_player_targetting_char` against its shopkeeper, and that aim is the
    # whole trigger: it freezes the clerk into the hands-up state,
    # zeroes TIMERA and starts the 50/100/250/600 payout ladder, whose first
    # tier gosubs the proximity sweep that calls add_stores_knocked_off. One
    # guard in front of each aim check therefore holds all 15.
    #
    # Each guard branches to that check's own false target, the handler's
    # not-aiming path, so a held store reads exactly as the player not aiming:
    # the clerk still spawns, still tracks the player, and killing him still
    # raises the wanted level, all vanilla.
    targets = [("$1532", "SHOP5_1636"), ("$854", "HARD3_3454")]
    for actor, label in targets:
        anchor = f"  is_player_targetting_char $player_char aiming_at_actor {actor}"
        hits = [i for i, ln in enumerate(lines) if ln == anchor]
        assert len(hits) == 1, f"store gate {actor}: {anchor!r} matched {len(hits)}"
        index = hits[0] - 1
        assert lines[index] == "if ", f"store gate {actor}: expected `if ` at {index}"
        assert lines[hits[0] + 1] == f"goto_if_false @{label}", \
            f"store gate {actor}: unexpected false target {lines[hits[0] + 1]!r}"
        lines[index:index] = _content_unlocked_guard(
            ROBBABLE_STORES_LOCK_FLAG, ROBBABLE_STORES_UNLOCK, label)
    edits.append(f"store robbery gated on the content lock at {len(targets)} handlers")


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


# Vanilla cash suppression. The AP check replaces each check's one-time
# completion cash; repeatable earnings (fares, per-action pay, replay prizes,
# race winnings, till cash) stay vanilla. Story mission pass cash is deleted
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


def guard_replay(index, span, completion):
    # Wrap `span` lines so they run when the side-events class is off OR the
    # event's completion global is already set (a replay). Only the first
    # completion while the class is on skips the payout: the payout and the
    # win-flag write share one script frame, and the APACT watcher marks the
    # completion global at least a frame later, so the global is still zero
    # exactly on the run the AP check eats.
    label = next_apcash_label()
    lines[index + span:index + span] = [f":{label}"]
    lines[index:index] = ["if or", f"  ${SIDE_EVENTS_ENABLED} == 0",
                          f"  ${completion} == 1", f"goto_if_false @{label}"]


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
        unlock, count = gate_conditions[0]
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


def suppress_boatyard_first_run_reward():
    # Checkpoint Charlie is replayable with escalating prizes ($8582 counts
    # runs); only the first run is the check, paying 5000 and setting $607.
    # That banner and cash gate on the properties flag; the replay tiers
    # (6000 and up) stay vanilla winnings. Sunshine's per-race prize money
    # also stays, as activity winnings.
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
    ("Hotring", 79, 9303, [
        "print_with_number_big 'HOTR_29' number 5000 time 6000 style 6",
        "add_score $player_char money += 5000",
    ]),
    ("Bloodring", 80, 9304, [
        "print_with_number_big 'BLOD_09' number 1000 time 6000 style 6",
        "add_score $player_char money += 1000",
    ]),
    ("Dirtring", 81, 9305, [
        "print_with_number_big 'M_PASS' number 50000 time 5000 style 1",
        "add_score $player_char money += 50000",
        "print_with_number_big 'M_PASS' number 10000 time 5000 style 1",
        "add_score $player_char money += 10000",
        "print_with_number_big 'M_PASS' number 5000 time 5000 style 1",
        "add_score $player_char money += 5000",
    ]),
    ("Downtown Chopper Checkpoint", 84, 9306, [
        "print_with_number_big 'HELI_1B' number 100 time 5000 style 1",
        "add_score $player_char money += 100",
    ]),
    ("Ocean Beach Chopper Checkpoint", 85, 9307, [
        "print_with_number_big 'HELI_1B' number 100 time 5000 style 1",
        "add_score $player_char money += 100",
    ]),
    ("Vice Point Chopper Checkpoint", 86, 9308, [
        "print_with_number_big 'HELI_1B' number 100 time 5000 style 1",
        "add_score $player_char money += 100",
    ]),
    ("Little Haiti Chopper Checkpoint", 87, 9309, [
        "print_with_number_big 'HELI_1B' number 100 time 5000 style 1",
        "add_score $player_char money += 100",
    ]),
    ("Trial by Dirt", 88, 9313, [
        "print_with_number_big 'M_PASS' number $1756 time 5000 style 1",
        "add_score $player_char money += $1756",
    ]),
    ("Test Track", 89, 9314, [
        "print_with_number_big 'M_PASS' number $1774 time 5000 style 1",
        "add_score $player_char money += $1774",
    ]),
    ("PCJ Playground", 90, 9315, [
        "print_with_number_big 'M_PASS' number $1612 time 5000 style 1",
        "add_score $player_char money += $1612",
    ]),
    # Cone Crazy pays from two sites. A completion that sets a record, which the
    # first one always does, gosubs to the record subroutine and is paid $7926
    # there (200, doubling per record); a replay that sets no record is paid a
    # flat literal 200 in the win branch itself, behind an already-completed
    # test. So the first-win payout is the $7926 pair, and the literal 200 pair
    # is replay winnings that stay vanilla.
    ("Cone Crazy", 91, 9316, [
        "print_with_number_big 'M_PASS' number $7926 time 5000 style 1",
        "add_score $player_char money += $7926",
    ]),
    ("RC Raider Pickup", 93, 9312, [
        "print_with_number_big 'M_PASS' number 100 time 5000 style 1",
        "add_score $player_char money += 100",
    ]),
    ("RC Bandit Race", 94, 9310, [
        "add_score $player_char money += 100",
        "print_with_number_big 'M_PASS' number 100 time 5000 style 1",
    ]),
    ("RC Baron Race", 95, 9311, [
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
            guard_replay(index, 1, completion)
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
    ("M82", "add_score $player_char money += 400"): 1,
    ("M82", "add_score $player_char money += 2000"): 1,
    ("M82", "add_score $player_char money += 4000"): 1,
    ("M82", "add_score $player_char money += 8000"): 1,
    ("M82", "add_score $player_char money += 20000"): 1,
    ("M82", "add_score $player_char money += 40000"): 1,
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

# The minimap unlock global, index matching scm.py. ASI-facing only (its
# shuffled flag sits at $9415 and this unlock at $9416; no gate reads either):
# the ASI hides the radar disc while the flag is set and this global is zero.
MINIMAP_UNLOCK = 9416

# Class-cash config flags, indices matching scm.py. The ASI stamps each to one
# when its check class is enabled, so the class's one-time completion cash is
# suppressed (the AP check is the reward); at zero everything pays vanilla.
# The properties flag gates the venue mission pass cash and Checkpoint
# Charlie's first run.
SIDE_EVENTS_ENABLED = 9417
STUNT_JUMPS_ENABLED = 9418
RAMPAGES_ENABLED = 9419
PROPERTIES_ENABLED = 9420

# The ability lock block, indices matching scm.py: eight lock flags at
# $9421..$9428 then eight unlock globals at $9429..$9436, all ASI-facing only
# (no gate reads them; the ASI enforces the locks per frame and they persist
# inside saves), so the script names none of them.
#
# The content lock block follows it in the same shape: five lock flags at
# $9437..$9441 then five unlock globals at $9442..$9446, in scm.CONTENT_KEYS
# order (hidden packages, rampages, stunt jumps, property purchases, robbable
# stores). The top unlock is the highest reserved global, so the foundation's
# sizing line references it; add_markers.py anchors on that line.
CONTENT_LOCK_FLAG_BASE = 9437
CONTENT_UNLOCK_BASE = 9442
CONTENT_TOP = 9446

# Three of the five classes are pickups, so holding them belongs to the ASI and
# the script needs nothing for them. The other two have no icon to hold, so
# their gates belong to the script, and these are the globals those gates read.
# The offsets into the block are pinned by a world test, since reordering
# scm.CONTENT_KEYS would point both gates at another class.
STUNT_JUMPS_LOCK_FLAG = CONTENT_LOCK_FLAG_BASE + 2
STUNT_JUMPS_UNLOCK = CONTENT_UNLOCK_BASE + 2
ROBBABLE_STORES_LOCK_FLAG = CONTENT_LOCK_FLAG_BASE + 4
ROBBABLE_STORES_UNLOCK = CONTENT_UNLOCK_BASE + 4

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
# line must equal scm.highest_reserved_global() (now the top content unlock
# $9446: 22 unlocks + 331 completions + 15 reward globals + 3 config flags +
# 19 radio globals + 15 ownership globals + the minimap flag and unlock + 4
# class-cash flags + 16 ability globals + 10 content globals above $9000).
# add_markers.py anchors on that line.
foundation = [f"${RADIO_RESOLVE_BASE + station} = {station}" for station in range(9)]
foundation += [f"${RADIO_REQUEST} = 0", f"${PROPERTIES_ENABLED} = 0", f"${CONTENT_TOP} = 0"]
insert_after("script_name 'HOT'", foundation, f"foundation radio identity + ${CONTENT_TOP} = 0")
check_play_order()
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
# Content-lock gates.
gate_stunt_jumps()
gate_store_robberies()
add_activity_gates()
add_activity_watcher()
suppress_mission_rewards()
suppress_boatyard_first_run_reward()
suppress_side_event_first_wins()
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

with open(DST, "wb") as handle:
    handle.write(nl.join(lines).encode("latin-1"))

wired = sum(1 for d in edits if d.startswith("completion"))
print(f"wired {wired} missions, skipped {len(skipped)}, {len(edits)} edits total")
if skipped:
    print("SKIPPED (need bespoke handling):")
    for reason in skipped:
        print(f"  - {reason}")
