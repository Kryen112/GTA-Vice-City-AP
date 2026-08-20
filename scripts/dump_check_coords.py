"""Generate the check coordinate table from a clean VC decompile.

Every check the game places in the world has a position in the SCM, and the
PopTracker pack pins each check on the Vice City map from it, so no pin is
placed by hand. This scanner extracts those positions.

Where each class's position comes from:

- story and venue missions: the launcher thread's own locate call, the same
  coordinate mod/scm/add_markers.py hands the mission's marker, keyed to the
  mission name by the launch line's comment. Two Sunshine Autos groups are
  bespoke: the showroom launches one mission for all six street races, so each
  race takes the showroom launcher's own locate, and the four import garage
  lists have no launcher at all, so they take the garage door the import
  opcodes name.
- rampages: the 35 #KILLFRENZY pickup creations in the RAMPAGE controller,
  whose order is the flag order and so the check order.
- property purchases: the 15 for-sale asset pickups, keyed by their GXT label.
- robbable stores: the locate or area test guarding each of the 15
  add_stores_knocked_off sites, in source order, the order the check names
  follow.
- side events: the launcher of the mission each event's thread belongs to,
  resolved through the decompile's own mission numbering.

Hidden packages are deliberately absent: package_data.py already owns their 100
positions in the same create_collectable1 order, so re-emitting them would make
two tables to keep in step. They are still extracted, and disagreeing with
package_data.py fails the run.

The emergency vehicle milestones place nothing anywhere and so get no
coordinate: a level completes wherever the last fare or fire happens to be.

The stunt jumps are not in the SCM either, and not in the executable: the game
builds their table on the heap at game start and writes it down nowhere. The
mod's ASI recovers it from live memory on its dump key and writes
gtavc_ap_stuntjumps.txt beside the executable; pass that file as the optional
third argument and its jumps join the table, each pinned at the middle of its
start box, which is where the run-up begins. A run without it carries whatever
table is already there rather than emptying it, since the dump comes from a game
session and not from the decompile, and the tracker lists the jumps instead of
pinning them only while no dump has ever been folded in.

Three of the four classes are index-ordered lists whose index IS the check
order, so a single dropped entry would shift every later pin silently. Nothing
is written unless every count, every name, and every cross-check passes; the
names and counts come from the world's own data.py, and a mission position is
checked against the game's own marker creations. On any failure this reports
what broke, writes nothing, and exits non-zero.

Coordinate operands are sometimes globals rather than literals. A global
resolves only when the whole file writes it exactly once, as a float literal,
and never through an opcode store.

The decompile is the player's own, generated locally and never committed, so
run this against the clean.txt produced for the SCM build.

Usage:
    python scripts/dump_check_coords.py clean.txt ../GTAVC_AP_Poptracker/data/check_coords.py
    python scripts/dump_check_coords.py clean.txt out.py gtavc_ap_stuntjumps.txt
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
import types
from collections import Counter

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORLD_PACKAGE = REPOSITORY_ROOT / "apworld" / "gta_vice_city"

NUMBER = r"-?\d+(?:\.\d+)?"
OPERAND = rf"(?:{NUMBER}|\$\d+)"

SCRIPT_NAME = re.compile(r"^script_name '(\S+)'$")
MISSION_HEADER = re.compile(r"^//-+Mission (\d+)-+$")
GLOBAL_ASSIGNMENT = re.compile(r"^\$(\d+) (?:=|\+=|-=|\*=|/=) (.*)$")
FLOAT_LITERAL = re.compile(rf"^{NUMBER}$")
GLOBAL_REFERENCE = re.compile(r"\$(\d+)")
LAUNCH = re.compile(r"^\s*load_and_launch_mission_internal (\d+)\s*//\s*(.+?)\s*$")
# The locate opcodes vary in three ways, so the operands are read by position
# rather than by one pattern: the name ends in 2d or 3d and says how many
# coordinates there are, what sits between the player and the position differs
# (a plain flag, or `sphere 0 near_point_in_car`), and a test may be negated.
# The name also says what is being located: a _char_ or _car_ variant locates
# against another entity's handle and carries no position at all, so those are
# left out rather than read as coordinates.
LOCATE = re.compile(
    r"^\s*(?:not )?locate_(?:stopped_)?player_(?:any_means|on_foot|in_car)_(2|3)d"
    r" \$player_char (.*?) radius\b")
# An area test is the flag then two opposite corners, three coordinates each in
# 3d and two in 2d.
AREA = re.compile(r"^\s*(?:not )?is_player_in_area_(2|3)d \$player_char (.*)$")
OPERAND_ONLY = re.compile(rf"^{OPERAND}$")
BLOCK_START = re.compile(r"^if\b")
MARKER_CREATE = re.compile(
    r"^add_sprite_blip_for_contact_point \$\d+ = create_icon_marker_and_sphere \S+"
    rf" at ({OPERAND}) ({OPERAND}) ({OPERAND})$")
COLLECTABLE = re.compile(rf"^create_collectable1 ({NUMBER}) ({NUMBER}) ({NUMBER})$")
KILL_FRENZY = re.compile(
    rf"^create_pickup \$(\d+) = create_pickup #KILLFRENZY type 3"
    rf" at ({NUMBER}) ({NUMBER}) ({NUMBER})$")
IMPORT_GARAGE_SLOT = re.compile(
    r"^\s*has_import_garage_slot_been_filled (\$\d+) contains_neededcar \d+$")
GARAGE_DOOR = re.compile(
    r"^set_garage (\$\d+) = create_garage_type \d+ door (\S+) (\S+) (\S+) to ")
FOR_SALE = re.compile(
    rf"^create_forsale_property_pickup \$\w+ = create_available_asset_pickup '(\w+)'"
    rf" at ({OPERAND}) ({OPERAND}) ({OPERAND}) price")
STORE_ROBBED = "add_stores_knocked_off 1"

# Property purchase check name per for-sale pickup GXT label. The eight
# businesses front the venue strands plus Pole Position; the seven safehouses
# are named for the district or street they stand on.
PROPERTY_BY_LABEL = {
    "PRNT_L": "Printworks Purchase",
    "CAR_L": "Sunshine Autos Purchase",
    "PORN_L": "Film Studio Purchase",
    "ICE_L": "Cherry Popper Purchase",
    "TAXI_L": "Kaufman Cabs Purchase",
    "BANK_L": "Malibu Club Purchase",
    "BOAT_L": "Boatyard Purchase",
    "STRP_L": "Pole Position Purchase",
    "NBMN_L": "El Swanko Casa Purchase",
    "LNKV_L": "Links View Apartment Purchase",
    "HYCO_L": "Hyman Condo Purchase",
    "OCHE_L": "Ocean Heights Apartment Purchase",
    "WASH_L": "1102 Washington Street Purchase",
    "VCPT_L": "3321 Vice Point Purchase",
    "SKUM_L": "Skumole Shack Purchase",
}

# Side event check name per thread that runs it. The thread belongs to a
# numbered mission, and that mission's launcher carries the trigger position.
SIDE_EVENT_BY_THREAD = {
    "OVALRNG": "Hotring",
    "MM": "Bloodring",
    "KICKST": "Dirtring",
    "HELI1SC": "Downtown Chopper Checkpoint",
    "HELI2SC": "Ocean Beach Chopper Checkpoint",
    "HELI3SC": "Vice Point Chopper Checkpoint",
    "HELI4SC": "Little Haiti Chopper Checkpoint",
    "RCRACE1": "RC Bandit Race",
    "RCPLNE1": "RC Baron Race",
    "RCHELI": "RC Raider Pickup",
    "BMX_1": "Trial by Dirt",
    "BMX_2": "Test Track",
    "T4X4_1": "PCJ Playground",
    "CARPRK1": "Cone Crazy",
}

# Mission check name per launch comment, where the decompile's comment spells
# the mission differently from the world's location name.
MISSION_NAME_BY_COMMENT = {
    "Keep your Friends Close...": "Keep Your Friends Close...",
}

# Launch comments that are not mission checks. The side events are launched as
# missions too but belong in their own table, keyed by check name; the rest
# either are not checks at all or are covered by another class's position (each
# property Buy mission by its for-sale icon, each emergency activity by nothing,
# since a level completes wherever the last fare or fire happens to be).
NON_MISSION_LAUNCH_COMMENTS = frozenset({
    "Initial", "Intro", "Weapon Range",
    "HOTRING", "BLOODRING", "DIRTRING",
    "TAXI DRIVER", "PARAMEDIC", "FIREFIGHTER", "VIGILANTE", "PIZZA BOY",
})

# The property buy cutscenes share this comment suffix, and all take their
# position from the for-sale icon rather than a launcher locate. "Sunshine
# Autos" is the one buy launch the decompile spells without it, and the race
# showroom's launch comment carries "Races", so the two never collide.
BUY_LAUNCH_COMMENT_SUFFIX = " Buy"
BUY_LAUNCH_COMMENTS = frozenset({"Sunshine Autos"})

# The one launch comment standing for more than one check: the showroom launches
# a single mission for all six street races and its menu picks which one runs,
# so every race takes the showroom launcher's own position.
RACE_LAUNCH_COMMENT = "Sunshine Autos Races"

# Missions the game gives no map marker, so their position cannot be checked
# against a marker creation. The first Rosenberg mission starts on a new game
# with no marker at all; the venue activities start at their property's buy
# cutscene, which is the for-sale icon rather than a marker; and the import
# garage lists are entered by driving a car through the garage door.
MISSIONS_WITHOUT_A_MARKER = frozenset({
    "An Old Friend", "Distribution", "Checkpoint Charlie",
    "Sunshine Autos Import List 1", "Sunshine Autos Import List 2",
    "Sunshine Autos Import List 3", "Sunshine Autos Import List 4",
    "Sunshine Autos Race: Terminal Velocity",
    "Sunshine Autos Race: Ocean Drive",
    "Sunshine Autos Race: Border Run",
    "Sunshine Autos Race: Capital Cruise",
    "Sunshine Autos Race: Tour!",
    "Sunshine Autos Race: V.C. Endurance",
})

# The rampage controller's 35 pickup handles, in flag order.
RAMPAGE_HANDLE_FIRST = 1404
# How far above an add_stores_knocked_off site its guarding test can sit. The
# scan also stops at the enclosing block, so this only bounds a site whose
# block opener is missing.
STORE_SCAN_LINES = 12


def load_world_data():
    """The world's own content tables, for the names and counts to check against.

    data.py imports nothing outside its own package, so a synthetic package with
    its path set is enough and no Archipelago checkout is needed.
    """
    package = types.ModuleType("gta_vice_city")
    package.__path__ = [str(WORLD_PACKAGE)]
    sys.modules["gta_vice_city"] = package
    from gta_vice_city import data
    return data


class Decompile:
    """The decompile as lines, with the lookups the scanners share."""

    def __init__(self, text: str) -> None:
        self.lines = text.split("\n")
        self.globals = self._resolvable_globals()
        self.thread_starts = self._thread_starts()
        self.mission_headers = self._mission_headers()

    def _resolvable_globals(self) -> dict[int, float]:
        # A coordinate global is written once at init. Anything written more than
        # once, written from another variable, or written through an opcode store
        # could hold something else by the time it is read, so only a global whose
        # single write in the whole file is a float literal resolves.
        assignments: dict[int, list[str]] = {}
        store_targets: set[int] = set()
        for line in self.lines:
            match = GLOBAL_ASSIGNMENT.match(line)
            if match:
                assignments.setdefault(int(match.group(1)), []).append(match.group(2))
            if "store_to" in line:
                store_targets.update(
                    int(index) for index in GLOBAL_REFERENCE.findall(line))
        return {
            index: float(values[0])
            for index, values in assignments.items()
            if len(values) == 1
            and FLOAT_LITERAL.match(values[0])
            and index not in store_targets
        }

    def _thread_starts(self) -> dict[str, int]:
        starts: dict[str, int] = {}
        for index, line in enumerate(self.lines):
            match = SCRIPT_NAME.match(line)
            if match and match.group(1) not in starts:
                starts[match.group(1)] = index
        return starts

    def _mission_headers(self) -> list[tuple[int, int]]:
        return [
            (index, int(match.group(1)))
            for index, line in enumerate(self.lines)
            if (match := MISSION_HEADER.match(line))
        ]

    def mission_number_at(self, line_index: int) -> int | None:
        """The numbered mission block a line sits in."""
        number = None
        for header_index, header_number in self.mission_headers:
            if header_index > line_index:
                break
            number = header_number
        return number

    def thread_span(self, name: str) -> range | None:
        """The lines of one thread, ending where the next thread names itself."""
        start = self.thread_starts.get(name)
        if start is None:
            return None
        for index in range(start + 1, len(self.lines)):
            if SCRIPT_NAME.match(self.lines[index]):
                return range(start, index)
        return range(start, len(self.lines))

    def resolve(self, operand: str) -> float | None:
        if operand.startswith("$"):
            return self.globals.get(int(operand[1:]))
        return float(operand)

    def resolve_all(self, operands: tuple[str, ...]) -> tuple[float, ...] | None:
        values = tuple(self.resolve(operand) for operand in operands)
        if any(value is None for value in values):
            return None
        return values  # type: ignore[return-value]

    def position_test(self, line: str) -> tuple[float, float, float] | None:
        """One player-position test as a point, or None if the line is not one.

        A locate is already a point and an area test is a box, so the box's
        centre stands in for it. A 2d test names no height, which the pins do
        not use, so its height reads as zero.
        """
        locate = LOCATE.match(line)
        if locate:
            wanted = int(locate.group(1))
            operands = self._operands(locate.group(2))
            # The coordinates are the last operands before the radius; whatever
            # precedes them says how the player is being located, not where.
            if len(operands) >= wanted:
                position = self.resolve_all(tuple(operands[-wanted:]))
                if position is not None:
                    return (position[0], position[1],
                            position[2] if wanted == 3 else 0.0)
        area = AREA.match(line)
        if area:
            axes = int(area.group(1))
            operands = self._operands(area.group(2))
            # The flag comes first, then the two opposite corners.
            if len(operands) >= 2 * axes + 1:
                corners = self.resolve_all(tuple(operands[1:2 * axes + 1]))
                if corners is not None:
                    centre = [
                        (corners[axis] + corners[axis + axes]) / 2
                        for axis in range(axes)
                    ]
                    return (centre[0], centre[1], centre[2] if axes == 3 else 0.0)
        return None

    def trigger_position(self, span: range) -> tuple[float, float, float] | None:
        """The first player-position test in a span. A launcher thread's own test
        is where the mission is offered, which is where its marker stands."""
        for index in span:
            position = self.position_test(self.lines[index])
            if position is not None:
                return position
        return None

    @staticmethod
    def _operands(text: str) -> list[str]:
        return [token for token in text.split() if OPERAND_ONLY.match(token)]

    def marker_positions(self) -> set[tuple[float, float, float]]:
        """Every position the game creates a mission marker at."""
        positions: set[tuple[float, float, float]] = set()
        for line in self.lines:
            match = MARKER_CREATE.match(line)
            if match:
                position = self.resolve_all(match.groups())
                if position is not None:
                    positions.add(position)
        return positions


def thread_name_at(decompile: Decompile, line_index: int) -> str | None:
    """The thread a line belongs to, found by scanning back to its name."""
    for index in range(line_index, -1, -1):
        match = SCRIPT_NAME.match(decompile.lines[index])
        if match:
            return match.group(1)
    return None


def package_positions(decompile: Decompile) -> list[tuple[float, float, float]]:
    positions = []
    for line in decompile.lines:
        match = COLLECTABLE.match(line)
        if match:
            positions.append(tuple(float(value) for value in match.groups()))
    return positions  # type: ignore[return-value]


def rampage_positions(decompile: Decompile,
                      count: int) -> tuple[list[tuple[float, float, float]], list[str]]:
    """The rampage icons in handle order, which is the check order."""
    by_handle: dict[int, tuple[float, float, float]] = {}
    for line in decompile.lines:
        match = KILL_FRENZY.match(line)
        if match:
            by_handle[int(match.group(1))] = tuple(
                float(value) for value in match.groups()[1:])
    wanted = range(RAMPAGE_HANDLE_FIRST, RAMPAGE_HANDLE_FIRST + count)
    missing = [f"${handle}" for handle in wanted if handle not in by_handle]
    problems = ([f"rampage pickup handles with no creation: {', '.join(missing)}"]
                if missing else [])
    return [by_handle[handle] for handle in wanted if handle in by_handle], problems


def property_positions(
    decompile: Decompile,
) -> tuple[dict[str, tuple[float, float, float]], list[str]]:
    positions: dict[str, tuple[float, float, float]] = {}
    problems: list[str] = []
    for line in decompile.lines:
        match = FOR_SALE.match(line)
        if not match:
            continue
        label = match.group(1)
        name = PROPERTY_BY_LABEL.get(label)
        if name is None:
            problems.append(f"for-sale label {label} names no property purchase")
            continue
        position = decompile.resolve_all(match.groups()[1:])
        if position is None:
            problems.append(f"{name}: its coordinate globals do not resolve")
            continue
        positions[name] = position
    return positions, problems


def store_positions(
    decompile: Decompile,
) -> tuple[list[tuple[float, float, float]], list[str]]:
    """Each robbery site's guarding position test, in source order.

    The 15 sites are one shared proximity sweep, each inside its own condition
    block, so the position test is the one between the block's opener and the
    site. Bounding the scan by that opener keeps a site whose own test is
    missing from silently borrowing the store above it.
    """
    positions: list[tuple[float, float, float]] = []
    problems: list[str] = []
    for index, line in enumerate(decompile.lines):
        if line.strip() != STORE_ROBBED:
            continue
        position = None
        for back in range(index - 1, max(index - STORE_SCAN_LINES, -1), -1):
            position = decompile.position_test(decompile.lines[back])
            if position is not None:
                break
            if BLOCK_START.match(decompile.lines[back]):
                break
        if position is None:
            thread = thread_name_at(decompile, index)
            problems.append(
                f"the robbery site at line {index + 1} (thread {thread}) has no"
                " position test in its own condition block")
            continue
        positions.append(position)
    return positions, problems


def launch_positions_by_number(
    decompile: Decompile,
) -> tuple[dict[int, tuple[float, float, float]], dict[int, str], list[str]]:
    """Mission number -> its launcher's position, and -> its launch comment."""
    positions: dict[int, tuple[float, float, float]] = {}
    names: dict[int, str] = {}
    problems: list[str] = []
    for index, line in enumerate(decompile.lines):
        match = LAUNCH.match(line)
        if not match:
            continue
        number = int(match.group(1))
        comment = match.group(2).strip()
        if number in names and names[number] != comment:
            problems.append(
                f"mission {number} is launched as both {names[number]!r} and"
                f" {comment!r}, so its position is ambiguous")
        names[number] = comment
        thread = thread_name_at(decompile, index)
        span = decompile.thread_span(thread) if thread else None
        position = decompile.trigger_position(span) if span else None
        if position is not None:
            positions.setdefault(number, position)
    return positions, names, problems


def side_event_positions(
    decompile: Decompile,
    launch_positions: dict[int, tuple[float, float, float]],
) -> tuple[dict[str, tuple[float, float, float]], list[str]]:
    """Each side event's trigger, from the launcher of the mission its thread
    belongs to."""
    positions: dict[str, tuple[float, float, float]] = {}
    problems: list[str] = []
    for thread, name in SIDE_EVENT_BY_THREAD.items():
        start = decompile.thread_starts.get(thread)
        if start is None:
            problems.append(f"{name}: no thread named {thread}")
            continue
        number = decompile.mission_number_at(start)
        position = launch_positions.get(number) if number is not None else None
        if position is None:
            problems.append(
                f"{name}: the launcher of mission {number} has no position")
            continue
        positions[name] = position
    return positions, problems


def is_mission_check(comment: str) -> bool:
    return (comment not in NON_MISSION_LAUNCH_COMMENTS
            and comment not in BUY_LAUNCH_COMMENTS
            and comment not in frozenset(SIDE_EVENT_BY_THREAD.values())
            and not comment.endswith(BUY_LAUNCH_COMMENT_SUFFIX))


def mission_positions(
    decompile: Decompile,
    launch_positions: dict[int, tuple[float, float, float]],
    launch_names: dict[int, str],
    race_names: list[str],
) -> tuple[dict[str, tuple[float, float, float]], list[str]]:
    positions: dict[str, tuple[float, float, float]] = {}
    problems: list[str] = []
    for number, comment in sorted(launch_names.items()):
        if not is_mission_check(comment):
            continue
        names = ([MISSION_NAME_BY_COMMENT.get(comment, comment)]
                 if comment != RACE_LAUNCH_COMMENT else list(race_names))
        position = launch_positions.get(number)
        if position is None:
            problems.append(
                f"{names[0]} (mission {number}): its launcher has no position")
            continue
        for name in names:
            positions[name] = position
    return positions, problems


def import_list_positions(
    decompile: Decompile,
    list_names: list[str],
) -> tuple[dict[str, tuple[float, float, float]], list[str]]:
    """The import garage lists, all at the garage door the deliveries go through.

    The garage is derived rather than named: the slot opcode says which garage
    takes the import deliveries, and that garage's own creation says where its
    door is. Every list is the same garage, so the four share one position and
    the tracker merges them into one marker.
    """
    problems: list[str] = []
    handles = {match.group(1) for match in
               (IMPORT_GARAGE_SLOT.match(line) for line in decompile.lines) if match}
    if len(handles) != 1:
        return {}, [f"import garage: the slot opcode names {sorted(handles)}"]
    handle = handles.pop()
    doors = [match.groups()[1:] for match in
             (GARAGE_DOOR.match(line) for line in decompile.lines)
             if match and match.group(1) == handle]
    if len(doors) != 1:
        return {}, [f"import garage: {handle} has {len(doors)} door creations"]
    position = decompile.resolve_all(doors[0])
    if position is None:
        return {}, [f"import garage: {handle}'s door is not a literal position"]
    return dict.fromkeys(list_names, position), problems


def check_against_markers(
    positions: dict[str, tuple[float, float, float]],
    markers: set[tuple[float, float, float]],
) -> list[str]:
    """A mission's position has to be where the game creates its marker.

    This reconciles the scan with mod/scm/add_markers.py, which reads the same
    launcher locate and requires a marker at those exact coordinates. A mission
    the game gives no marker is listed instead, so a new one shows up here
    rather than passing quietly.
    """
    problems: list[str] = []
    for name, position in sorted(positions.items()):
        has_marker = position in markers
        if has_marker and name in MISSIONS_WITHOUT_A_MARKER:
            problems.append(
                f"{name} is listed as having no marker but its position is one")
        elif not has_marker and name not in MISSIONS_WITHOUT_A_MARKER:
            problems.append(
                f"{name} at {position} is not where the game creates a marker")
    return problems


# One dumped stunt jump record: two box corners, two more, the camera, the
# reward. The pin takes the middle of the start box.
STUNT_JUMP_FLOATS = 15


def carried_stunt_jumps(
    destination: str,
) -> tuple[list[tuple[float, float, float]], list[str]]:
    """The stunt jump table an earlier run already wrote.

    The dump comes from a game session rather than from the decompile, so a run
    without it must leave the jumps as they were: rewriting the table empty
    would silently unpin all 36 the next time the pack is generated.
    """
    path = pathlib.Path(destination)
    if not path.is_file():
        return [], []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return [], [f"{destination} exists but does not parse, so the stunt jumps"
                    " it holds cannot be carried forward; pass a dump or delete it"]
    for statement in tree.body:
        target = None
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            target = statement.target.id
        elif isinstance(statement, ast.Assign) and isinstance(statement.targets[0], ast.Name):
            target = statement.targets[0].id
        if target != "STUNT_JUMP_COORDS":
            continue
        try:
            return [tuple(entry) for entry in ast.literal_eval(statement.value)], []
        except (TypeError, ValueError):
            return [], [f"{destination} holds a STUNT_JUMP_COORDS that is not a"
                        " table of positions"]
    return [], []


def stunt_jump_positions(
    path: str, expected: int,
) -> tuple[list[tuple[float, float, float]], list[str]]:
    """The dumped stunt jump table as one position per jump, in the array's own
    order, which is the engine's jump order and so the check order."""
    positions: list[tuple[float, float, float]] = []
    problems: list[str] = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = stripped.split()
            if len(fields) != STUNT_JUMP_FLOATS + 2:
                problems.append(f"{path} line {number}: {len(fields)} fields, "
                                f"expected {STUNT_JUMP_FLOATS + 2}")
                continue
            try:
                values = [float(field) for field in fields[1:1 + STUNT_JUMP_FLOATS]]
            except ValueError:
                problems.append(f"{path} line {number}: a field is not a number")
                continue
            # The dump keeps both corners in the order the game stores them, so
            # the middle stands in whichever came first.
            positions.append(tuple(
                (values[axis] + values[axis + 3]) / 2 for axis in range(3)))
    problems += check_count("stunt jumps", len(positions), expected)
    outside = [
        position for position in positions
        if not all(abs(value) < 2100.0 for value in position[:2])
    ]
    if outside:
        problems.append(f"stunt jump positions outside the world: {outside}")
    if len(set(positions)) != len(positions):
        problems.append("two stunt jumps share a position")
    return positions, problems


def check_names(label: str, found: set[str], expected: set[str]) -> list[str]:
    problems = []
    if missing := sorted(expected - found):
        problems.append(f"{label} with no position: {missing}")
    if extra := sorted(found - expected):
        problems.append(f"{label} the world does not know: {extra}")
    return problems


def check_count(label: str, found: int, expected: int) -> list[str]:
    if found == expected:
        return []
    return [f"{label}: found {found} positions, the world expects {expected}"]


def render_module(
    missions: dict[str, tuple[float, float, float]],
    rampages: list[tuple[float, float, float]],
    properties: dict[str, tuple[float, float, float]],
    stores: list[tuple[float, float, float]],
    side_events: dict[str, tuple[float, float, float]],
    stunt_jumps: list[tuple[float, float, float]],
) -> str:
    def rows(entries: list[tuple[str, tuple[float, float, float]]]) -> str:
        return "\n".join(
            f'    "{name}": ({x}, {y}, {z}),' for name, (x, y, z) in entries)

    def points(entries: list[tuple[float, float, float]]) -> str:
        return "\n".join(f"    ({x}, {y}, {z})," for x, y, z in entries)

    stunt_jump_note = (
        "Stunt jumps carry the middle of each start box, read from the game's own\n"
        "table by the mod's runtime dump; the game defines them nowhere else."
        if stunt_jumps else
        "Stunt jumps are absent: the game builds their table only while it runs, so\n"
        "they arrive from the mod's runtime dump or not at all."
    )

    return f'''"""Check world positions, generated by scripts/dump_check_coords.py.

Each entry is the game position the PopTracker pack pins a check at. Missions
carry their launcher's trigger position, rampages their pickup, purchases their
for-sale icon, stores their robbery trigger, and side events their launcher.

Hidden packages are absent: their positions live in the world's own
package_data.py, in the same order, so the generator reads them from there.
Emergency vehicle milestones are absent because they have no position at all.
{stunt_jump_note}

Indexed classes are lists in check order, the order that fixes location ids and
names; the rest are keyed by check name. A 2d position test names no height, so
some heights read as zero; the pins use only x and y.
"""

from __future__ import annotations

MISSION_COORDS: dict[str, tuple[float, float, float]] = {{
{rows(sorted(missions.items()))}
}}

RAMPAGE_COORDS: list[tuple[float, float, float]] = [
{points(rampages)}
]

PROPERTY_COORDS: dict[str, tuple[float, float, float]] = {{
{rows(sorted(properties.items()))}
}}

STORE_COORDS: list[tuple[float, float, float]] = [
{points(stores)}
]

SIDE_EVENT_COORDS: dict[str, tuple[float, float, float]] = {{
{rows(sorted(side_events.items()))}
}}

STUNT_JUMP_COORDS: list[tuple[float, float, float]] = [
{points(stunt_jumps)}
]
'''


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print(__doc__, file=sys.stderr)
        return 2
    source, destination = sys.argv[1], sys.argv[2]
    stunt_jump_dump = sys.argv[3] if len(sys.argv) == 4 else None
    data = load_world_data()
    with open(source, "rb") as handle:
        text = handle.read().decode("latin-1").replace("\r\n", "\n")
    decompile = Decompile(text)

    launch_positions, launch_names, problems = launch_positions_by_number(decompile)
    race_names = data.VENUE_ACTIVITIES["Sunshine Autos"]
    missions, mission_problems = mission_positions(
        decompile, launch_positions, launch_names, race_names)
    import_lists, import_list_problems = import_list_positions(
        decompile, data.VENUE_STRANDS["Sunshine Autos"])
    missions.update(import_lists)
    mission_problems += import_list_problems
    packages = package_positions(decompile)
    rampages, rampage_problems = rampage_positions(decompile, data.RAMPAGE_COUNT)
    properties, property_problems = property_positions(decompile)
    stores, store_problems = store_positions(decompile)
    side_events, side_event_problems = side_event_positions(decompile, launch_positions)
    problems += (mission_problems + rampage_problems + property_problems
                 + store_problems + side_event_problems)

    expected_missions = {
        mission
        for strand in (data.STORY_GIVERS, data.VENUE_STRANDS, data.VENUE_ACTIVITIES)
        for missions_in_strand in strand.values()
        for mission in missions_in_strand
    }
    problems += check_names(
        "story and venue missions and venue activities",
        set(missions), expected_missions)
    problems += check_against_markers(missions, decompile.marker_positions())
    problems += check_names(
        "property purchases", set(properties), set(data.PROPERTY_PURCHASES))
    problems += check_names("side events", set(side_events), set(data.SIDE_EVENTS))
    problems += check_count("rampages", len(rampages), data.RAMPAGE_COUNT)
    problems += check_count("robbable stores", len(stores), data.ROBBABLE_STORE_COUNT)
    problems += check_count("hidden packages", len(packages), data.HIDDEN_PACKAGE_COUNT)
    # The packages are re-extracted only to hold package_data.py to account, so a
    # change in either place has to be a change in both.
    if packages and packages != [tuple(coord) for coord in data.PACKAGE_COORDS]:
        problems.append(
            "the extracted hidden package positions disagree with package_data.py")
    repeated = [position for position, times in Counter(stores).items() if times > 1]
    if repeated:
        problems.append(f"two robbable stores share a position: {repeated}")

    if stunt_jump_dump is not None:
        stunt_jumps, stunt_jump_problems = stunt_jump_positions(
            stunt_jump_dump, data.STUNT_JUMP_COUNT)
    else:
        stunt_jumps, stunt_jump_problems = carried_stunt_jumps(destination)
        # A carried table is re-emitted rather than re-read from the game, so it
        # is held to the same count as a fresh one: a table left short by an
        # older run would otherwise survive every regeneration.
        if stunt_jumps:
            stunt_jump_problems += check_count(
                "carried stunt jumps", len(stunt_jumps), data.STUNT_JUMP_COUNT)
    problems += stunt_jump_problems

    if problems:
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        print(f"{len(problems)} problems; nothing written", file=sys.stderr)
        return 1

    module = render_module(missions, rampages, properties, stores, side_events,
                           stunt_jumps)
    with open(destination, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(module)

    print(f"missions           {len(missions):>4}")
    print(f"rampages           {len(rampages):>4}")
    print(f"property purchases {len(properties):>4}")
    print(f"robbable stores    {len(stores):>4}")
    print(f"side events        {len(side_events):>4}")
    print(f"hidden packages    {len(packages):>4} checked against package_data.py")
    if stunt_jump_dump:
        print(f"stunt jumps        {len(stunt_jumps):>4}")
    elif stunt_jumps:
        print(f"stunt jumps        {len(stunt_jumps):>4} carried from the "
              "previous table")
    else:
        print("stunt jumps           0 (no dump yet; they stay unpinned)")
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
