"""Generate the ambient pickup table from a clean VC decompile.

The randomize_pickups option permutes the ambient world pickups: street
weapons, health hearts, body armors, adrenaline pills, and police bribes.
This scanner extracts their placements into pickup_data.py. The eligible
sites are exactly:

- the #BRIBE creations in the MAIN section (every other allowlisted MAIN
  creation is a safehouse package reward the APREWD watcher re-gates),
- every allowlisted creation in the Mission 0 block, the init mission that
  places the ambient world items at a new game, and
- every PERMANENT creation in any other mission block: a literal-coordinate
  creation of a respawning or in-shop type whose handle global is never passed
  to remove_pickup, so the pickup it makes outlives the mission that made it
  and stands in the world for the rest of the game.

The third rule is derived and not a list, which is what keeps it honest: a
creation qualifies by what the script does with it rather than by having been
noticed. Everything else in a mission block is transient (the type-3 drops a
mission places and clears) and stays vanilla. Lines with variable operands are
mission logic and never match.

Permanent creations split two ways. Most append to PICKUP_SLOTS and become
ambient slots like any other. The four standing in Phil's Place are in-shop
stands that the shop class owns instead, so they are emitted separately as
SHOP_STAND_SLOTS and cross-checked against shop_data.py, which is where their
prices and names are hand-written.

The decompile is the player's own, generated locally and never committed, so
run this against the clean.txt produced for the SCM build. The emitted
module holds coordinates, model and pickup-type ids, the global each creation
stores its pickup handle in, and the in-game name of each model that appears, so
that the world can name a location after what stands there.

One table in it is NOT derived. PICKUP_NAMES is the hand audit's own and lives
nowhere else, so a run carries the existing one forward and refuses when its
length no longer matches the slot table.

Usage:
    python scripts/dump_pickups.py path/to/clean.txt apworld/gta_vice_city/pickup_data.py
"""

from __future__ import annotations

import importlib.util
import math
import pathlib
import re
import sys

MISSION_HEADER = re.compile(r"^//-------------Mission (\d+)---------------$")
CREATE_PICKUP = re.compile(
    r"^create_pickup \$\w+ = create_pickup (#\w+|\d+) type (\d+)"
    r" at (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)$")
CREATE_WEAPON_PICKUP = re.compile(
    r"^create_pickup_with_ammo \$\w+ = create_weapon_pickup (\d+) (\d+) ammo (\d+)"
    r" at (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)$")

# Every ambient creation stores its pickup handle in a global, which is the
# game's own name for a slot and so the thing detection will be built on. Read
# with its own pattern so the two creation patterns above keep their group
# numbers.
CREATED_HANDLE = re.compile(r"^create_pickup(?:_with_ammo)? \$(\w+) = ")

# A creation is PERMANENT when nothing ever takes its pickup away again, so
# the removals are collected across the whole script before any creation is
# judged.
REMOVE_PICKUP = re.compile(r"^remove_pickup \$(\w+)$")

# The pickup types that outlive the mission creating them: the in-shop stand,
# which charges and comes straight back, and the two street types, which come
# back on a timer. Every other type a mission uses is a transient drop it
# clears at cleanup, and the removal test catches those anyway; this narrows
# the question to the types whose whole point is to keep standing there.
PERSISTENT_PICKUP_TYPES = frozenset({1, 2, 15})

# The permanent creations the SHOP class owns rather than the pickup class:
# the four in-shop stands Boomshine Saigon racks at Phil's Place. Curated,
# because nothing in the script says a stand is a shop. What is DERIVED is
# that these four are permanent, and a run refuses when a handle here is not
# among the permanent creations it found, so this list cannot quietly name
# something that has moved.
SHOP_STAND_HANDLES = (4345, 4346, 4347, 4348)

# The type every shop stand must be: the one that charges. A stand that came
# back as anything else would hand its weapon over for nothing.
SHOP_STAND_PICKUP_TYPE = 1

# Two positions this close are one slot re-created rather than two pickups,
# which is what a foreign-separation measurement has to know: the VCPD
# nightstick is created twice at one spot, by Mission 0 and again by the
# mission that borrows its room.
SAME_POSITION_EPSILON = 0.01

NAMED_MODELS = {"#HEALTH": 366, "#ADRENALINE": 367, "#BODYARMOUR": 368, "#BRIBE": 375}
WEAPON_MODEL_FIRST = 259
WEAPON_MODEL_LAST = 291
MINIMUM_SLOT_SEPARATION = 1.5

MODEL_NAMES = {
    259: "Brass Knuckles",
    260: "Screwdriver",
    261: "Golf Club",
    262: "Nightstick",
    263: "Knife",
    264: "Baseball Bat",
    265: "Hammer",
    266: "Meat Cleaver",
    267: "Machete",
    268: "Katana",
    269: "Chainsaw",
    270: "Grenades",
    271: "Tear Gas",
    272: "Molotov Cocktails",
    274: "Colt .45",
    275: ".357",
    276: "Kruger",
    277: "Chrome Shotgun",
    278: "S.P.A.S. 12",
    279: "Stubby Shotgun",
    280: "M4",
    281: "Tec-9",
    282: "Uzi",
    283: "Ingram Mac 10",
    284: "MP",
    285: "Sniper Rifle",
    286: ".308 Sniper",
    287: "Rocket Launcher",
    288: "Flamethrower",
    289: "M60",
    290: "Minigun",
    291: "Detonator Grenades",
    366: "Health",
    367: "Adrenaline",
    368: "Body Armor",
    375: "Police Bribe",
}

MODULE_DOCSTRING = '''"""Ambient pickup data, generated by scripts/dump_pickups.py.

Each row is one eligible world pickup slot in decompile order:
(x, y, z, pickup type, vanilla model, vanilla ammo). The randomize_pickups
option permutes the (model, ammo) pairs across the slots; the position and
the pickup type stay with the slot. Type 1 is the in-shop type, which charges,
and bribes never land on a type 1 slot: an in-shop bribe would be free, since a
bribe's weapon-type field is zero and so is the cost table's zeroth entry, and
each bribe takes a star off the wanted level, so a free one that respawns is an
endless supply of them.
"""'''


def parse_model(token: str) -> int | None:
    if token in NAMED_MODELS:
        return NAMED_MODELS[token]
    if token.startswith("#"):
        return None
    model = int(token)
    if WEAPON_MODEL_FIRST <= model <= WEAPON_MODEL_LAST:
        return model
    return None


def handle_of(line: str) -> int:
    """The global a creation stores its handle in.

    Every eligible creation has one, so a line without one is a line this
    extractor has misread rather than a slot with no handle, and it refuses
    rather than inventing a global number the watcher would then read.
    """
    match = CREATED_HANDLE.match(line)
    if match is None or not match.group(1).isdigit():
        raise SystemExit(f"creation stores no numeric handle: {line}")
    return int(match.group(1))


def parse_creation(line: str):
    """One literal-operand pickup creation, or None for anything else.

    Returns (position, pickup type, model, ammo, model token). The model is None
    when the token names something outside the allowlist, which is how a
    briefcase, a keycard, a save disc or a rampage icon falls out.
    """
    plain = CREATE_PICKUP.match(line)
    if plain:
        return ((float(plain.group(3)), float(plain.group(4)),
                 float(plain.group(5))), int(plain.group(2)),
                parse_model(plain.group(1)), 0, plain.group(1))
    weapon = CREATE_WEAPON_PICKUP.match(line)
    if weapon:
        model = int(weapon.group(1))
        return ((float(weapon.group(4)), float(weapon.group(5)),
                 float(weapon.group(6))), int(weapon.group(2)),
                model if WEAPON_MODEL_FIRST <= model <= WEAPON_MODEL_LAST else None,
                int(weapon.group(3)), weapon.group(1))
    return None


def removed_handles(lines: list[str]) -> set[str]:
    """Every handle global the script ever takes a pickup away through.

    Read across the WHOLE file rather than per mission, because a removal is
    what makes a creation transient wherever it stands: a mission that hands
    its cleanup to a later block still removes what it made.
    """
    removals = set()
    for raw_line in lines:
        match = REMOVE_PICKUP.match(raw_line.strip())
        if match:
            removals.add(match.group(1))
    return removals


def extract(lines: list[str]) -> tuple[
        list[tuple[float, float, float, int, int, int]], list[int],
        list[tuple[float, float, float, int, int, int, int]],
        list[tuple[tuple[float, float, float], int]], int]:
    headers = [(int(MISSION_HEADER.match(line).group(1)), index)
               for index, line in enumerate(lines) if MISSION_HEADER.match(line)]
    boundaries = dict(headers)
    mission_zero_start = boundaries[0]
    mission_zero_end = boundaries[1]
    removals = removed_handles(lines)

    slots: list[tuple[float, float, float, int, int, int]] = []
    handles: list[int] = []
    # The permanent mission creations, kept apart from the ambient walk above so
    # that they append AFTER every Mission 0 slot whatever order the script puts
    # them in. Appending is what keeps every existing location id and completion
    # global where it is.
    permanent: list[tuple[tuple[float, float, float], int, int, int, int]] = []
    # Every literal creation in the script, for the foreign-separation
    # measurement. A pickup no table of ours owns still stands in the world, and
    # the matcher has to tell it from a slot.
    creations: list[tuple[tuple[float, float, float], int]] = []
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        creation = parse_creation(line)
        if creation is None:
            continue
        position, pickup_type, model, ammo, token = creation
        creations.append((position, pickup_type))
        in_main = index < mission_zero_start
        in_mission_zero = mission_zero_start <= index < mission_zero_end

        if in_main:
            # Every other allowlisted MAIN creation is a safehouse package
            # reward, which the APREWD watcher re-gates instead.
            if model is None or token != "#BRIBE":
                continue
            slots.append((*position, pickup_type, model, ammo))
            handles.append(handle_of(line))
            continue

        if in_mission_zero:
            if model is None:
                continue
            slots.append((*position, pickup_type, model, ammo))
            handles.append(handle_of(line))
            continue

        # Any other mission block: permanent creations only.
        if model is None or pickup_type not in PERSISTENT_PICKUP_TYPES:
            continue
        handle = handle_of(line)
        if str(handle) in removals:
            continue
        permanent.append((position, pickup_type, model, ammo, handle))

    shop_handles = set(SHOP_STAND_HANDLES)
    found = {handle for _p, _t, _m, _a, handle in permanent}
    missing = sorted(shop_handles - found)
    if missing:
        raise SystemExit(
            f"# SHOP_STAND_HANDLES names {missing}, which this run did not find "
            f"among the permanent mission creations. Either the stands moved or "
            f"a mission now removes them, and either way the shop table is "
            f"describing something that is no longer there.")
    shop_stands = [(*position, pickup_type, model, ammo, handle)
                   for position, pickup_type, model, ammo, handle in permanent
                   if handle in shop_handles]
    # Where the permanent creations start in the slot table. Everything below it
    # is placed by Mission 0 or the MAIN section at a new game; everything from
    # it up has a handle global that reads zero until its mission passes, which
    # is a difference the watcher has to know about.
    mission_created_first = len(slots)
    for position, pickup_type, model, ammo, handle in permanent:
        if handle in shop_handles:
            continue
        slots.append((*position, pickup_type, model, ammo))
        handles.append(handle)
    return slots, handles, shop_stands, creations, mission_created_first


def check_foreign_separation(
        slots: list[tuple[float, float, float, int, int, int]],
        shop_stands: list[tuple[float, float, float, int, int, int, int]],
        creations: list[tuple[tuple[float, float, float], int]]) -> float:
    """How close a same-type pickup NO table owns gets to one this table does.

    The upper bound on the matcher's position tolerance, and the reason it is
    measured rather than stated: the matcher finds a slot's pool entry by
    position and type, so a foreign pickup of the same type inside the tolerance
    is a slot the matcher could rewrite the wrong pickup for. A creation at a
    slot's own position is that slot being re-created, not a foreign pickup.
    """
    owned = [(row[:3], row[3]) for row in slots]
    owned += [(row[:3], row[3]) for row in shop_stands]
    minimum = math.inf
    for position, pickup_type in owned:
        for other_position, other_type in creations:
            if other_type != pickup_type:
                continue
            distance = math.dist(position, other_position)
            if distance <= SAME_POSITION_EPSILON:
                continue
            minimum = min(minimum, distance)
    return minimum


def check_separation(slots: list[tuple[float, float, float, int, int, int]]) -> float:
    minimum = math.inf
    for first in range(len(slots)):
        for second in range(first + 1, len(slots)):
            distance = math.dist(slots[first][:3], slots[second][:3])
            minimum = min(minimum, distance)
    return minimum


NAME_TABLE = re.compile(r"^PICKUP_NAMES: list\[str\] = \[\n(.*?)^\]$",
                        re.MULTILINE | re.DOTALL)
NAME_ROW = re.compile(r'^    "(.*)",$', re.MULTILINE)


def carried_names(output_path: str, expected: int) -> list[str]:
    """The hand-audited PICKUP_NAMES already in the module, carried forward.

    The names come from the walk of all 110 slots and are in no decompile, so
    there is nothing to re-derive them from. A run that dropped them would
    destroy the audit silently; instead they are read back out of the file being
    replaced, and anything short of a table this run can reproduce refuses the
    run rather than writing one that has slipped against its coordinates.

    Three ways to lose them and only one is a count: a table the wrong length, a
    table this cannot see at all, and a row a hand edit or a formatter wrapped
    across two lines, which reads as one row whose name is the tail fragment.
    All three refuse, which is why every line inside the table has to match and
    not merely enough of them. Writing the module for the first time is the one
    quiet case, and it is the one where the file is not there at all.
    """
    source = pathlib.Path(output_path)
    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    table = NAME_TABLE.search(text)
    if table is None:
        raise SystemExit(
            f"# {output_path} is there and holds no PICKUP_NAMES this can read, "
            f"so the hand audit would be dropped. Restore the table, or delete "
            f"the file if the names really are meant to go.")
    body = [line for line in table.group(1).splitlines() if line.strip()]
    names = NAME_ROW.findall(table.group(1))
    if len(names) != len(body):
        raise SystemExit(
            f"# {output_path} has {len(body) - len(names)} line(s) inside "
            f"PICKUP_NAMES this cannot read as a name, most likely a row wrapped "
            f"across two lines, and reading past them would truncate a name")
    if len(names) != expected:
        raise SystemExit(
            f"# {output_path} holds {len(names)} pickup names for {expected} "
            f"slots, refusing rather than writing a table out of step")
    return names


def render_module(slots: list[tuple[float, float, float, int, int, int]],
                  handles: list[int], names: list[str],
                  shop_stands: list[tuple[float, float, float, int, int, int, int]],
                  closest_slot_pair: float, nearest_foreign: float,
                  mission_created_first: int) -> str:
    lines = [MODULE_DOCSTRING, "", "from __future__ import annotations", ""]
    lines.append("PICKUP_SLOTS: list[tuple[float, float, float, int, int, int]] = [")
    for x, y, z, pickup_type, model, ammo in slots:
        lines.append(f"    ({x}, {y}, {z}, {pickup_type}, {model}, {ammo}),")
    lines.append("]")
    lines.append("")
    lines.append("PICKUP_MODEL_NAMES: dict[int, str] = {")
    lines.extend(f'    {model}: "{MODEL_NAMES[model]}",'
                 for model in sorted({slot[4] for slot in slots}))
    lines.append("}")
    lines.append("")
    lines.append("# The global each slot's creation stores its pickup handle in, in")
    lines.append("# PICKUP_SLOTS order. Vanilla globals, so they never move. The APPICK")
    lines.append("# watcher polls every one of them; a handle is the game's own name")
    lines.append("# for a slot and there is nothing else to detect a taken pickup by.")
    lines.append("#")
    lines.append("# Two things a reader has to know. Two slots have their pickup")
    lines.append("# re-created by a mission, and one of those re-creations puts it")
    lines.append("# somewhere else, so a reader has to check that the pickup a handle")
    lines.append("# resolves to still stands where the slot does. And every handle from")
    lines.append("# MISSION_CREATED_FIRST_SLOT up reads ZERO until its mission runs,")
    lines.append("# which is a state the collected test must never be asked about. See")
    lines.append("# data.py.")
    lines.append("PICKUP_HANDLE_GLOBALS: list[int] = [")
    for start in range(0, len(handles), 10):
        row = ", ".join(str(handle) for handle in handles[start:start + 10])
        lines.append(f"    {row},")
    lines.append("]")
    lines.append("")
    if names:
        lines.append(
            "# The name of each slot, from the hand audit of every location, in\n"
            "# PICKUP_SLOTS order. Not from the decompile, which says nothing about\n"
            "# where a slot is in words: this table is carried forward across a\n"
            "# regeneration. The district half is the audit's own, so\n"
            "# district_data.PICKUP_DISTRICTS says the same one.")
        lines.append("PICKUP_NAMES: list[str] = [")
        lines.extend(f'    "{name}",' for name in names)
        lines.append("]")
        lines.append("")
    lines.append("# The permanent mission creations the SHOP class owns rather than")
    lines.append("# the pickup class: the four in-shop stands Boomshine Saigon racks")
    lines.append("# at Phil's Place. Each row is (x, y, z, pickup type, vanilla")
    lines.append("# model, vanilla ammo, handle global). They are here because this")
    lines.append("# is what reads the decompile; their prices and display names are")
    lines.append("# hand-written in shop_data.py, which a run cross-checks against")
    lines.append("# these coordinates.")
    lines.append(
        "SHOP_STAND_SLOTS: list[tuple[float, float, float, int, int, int, int]] = [")
    for x, y, z, pickup_type, model, ammo, handle in shop_stands:
        lines.append(f"    ({x}, {y}, {z}, {pickup_type}, {model}, {ammo}, {handle}),")
    lines.append("]")
    lines.append("")
    lines.append("# The two measurements that bound how far apart a position match")
    lines.append("# may look, both taken over the decompile rather than written down.")
    lines.append("#")
    lines.append("# The matcher pairs a slot with a pool entry by position and type,")
    lines.append("# so the tolerance has to sit BELOW the closest same-type pickup no")
    lines.append("# table of ours owns, or the matcher could pair a slot with that")
    lines.append("# one, and it may sit anywhere below the closest pair of slots. The")
    lines.append("# foreign bound is the tight one and it is not comfortable: the")
    lines.append("# body armour Rub Out leaves in the estate courtyard and the Tec-9")
    lines.append("# the finale places to be survived with are both street type and")
    lines.append("# less than a unit apart. The finale holds the whole layout off the")
    lines.append("# pool while it runs, so that pair never actually meets, but the")
    lines.append("# tolerance is kept under it anyway rather than resting on that.")
    lines.append(f"CLOSEST_SLOT_PAIR = {closest_slot_pair:.2f}")
    lines.append(f"NEAREST_FOREIGN_PICKUP = {nearest_foreign:.2f}")
    lines.append("")
    lines.append("# The first slot a MISSION creates rather than the init mission.")
    lines.append("# Everything below it exists from a new game; everything from it up has")
    lines.append("# a handle global reading zero until its mission passes.")
    lines.append("#")
    lines.append("# Whatever polls a handle has to skip the zeros, and not as a")
    lines.append("# tidiness: has_pickup_been_collected (0x441880) does not look at the")
    lines.append("# pickup pool at all. It scans the twenty-entry ring of recently")
    lines.append("# collected handles, returns true on a match and CLEARS the entry it")
    lines.append("# matched. The ring is zeroed at boot and every read leaves a zero")
    lines.append("# behind, so asking about handle zero matches a spent entry and")
    lines.append("# answers true. A slot polled before its mission runs would report")
    lines.append("# itself collected on the first frame.")
    lines.append(f"MISSION_CREATED_FIRST_SLOT = {mission_created_first}")
    lines.append("")
    lines.append("BRIBE_MODEL = 375")
    lines.append("SHOP_PICKUP_TYPE = 1")
    lines.append("")
    return "\n".join(lines)


def cross_check_shop_stands(
        output_path: str,
        shop_stands: list[tuple[float, float, float, int, int, int, int]]) -> None:
    """Refuse when shop_data.py describes these stands as standing elsewhere.

    The stands are pickups, so their coordinates, model and type come from the
    decompile; their price and display name are the hand-written shop table's.
    Two files holding half a row each is exactly where a silent drift lives, so
    the halves are compared here, on the one run that can see both.

    Loaded by path rather than imported as part of the package, because
    importing the package pulls in Archipelago and this script does not need it.
    """
    module_path = pathlib.Path(output_path).with_name("shop_data.py")
    specification = importlib.util.spec_from_file_location(
        "gta_vice_city_shop_data", module_path)
    if specification is None or specification.loader is None:
        raise SystemExit(f"# cannot read {module_path} to cross-check the stands")
    shop_data = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(shop_data)
    by_handle = {item.script_global: item for item in shop_data.SHOP_ITEMS
                 if item.thread in shop_data.SHOP_PICKUP_THREADS}
    if sorted(by_handle) != sorted(row[6] for row in shop_stands):
        raise SystemExit(
            f"# shop_data.py holds pickup stands {sorted(by_handle)} and the "
            f"decompile holds {sorted(row[6] for row in shop_stands)}; one of "
            f"the two is out of step and the shop table would name a stand that "
            f"is not there")
    for x, y, z, pickup_type, model, _ammo, handle in shop_stands:
        item = by_handle[handle]
        placed = (round(item.x, 4), round(item.y, 4), round(item.z, 4))
        if placed != (round(x, 4), round(y, 4), round(z, 4)):
            raise SystemExit(
                f"# shop_data.py puts stand ${handle} at {placed} and the "
                f"decompile puts it at {(x, y, z)}")
        if item.model != model:
            raise SystemExit(
                f"# shop_data.py sells model {item.model} at stand ${handle} "
                f"and the decompile racks model {model} there")
        if pickup_type != SHOP_STAND_PICKUP_TYPE:
            raise SystemExit(
                f"# stand ${handle} is pickup type {pickup_type} and not the "
                f"in-shop type, so it would not charge for what it hands over")


def main(source_path: str, output_path: str) -> int:
    with open(source_path, "rb") as handle:
        raw = handle.read()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    lines = raw.decode("latin-1").split(newline)

    slots, handles, shop_stands, creations, mission_created_first = extract(lines)
    cross_check_shop_stands(output_path, shop_stands)
    if len(handles) != len(slots):
        print("# a slot without a handle, refusing", file=sys.stderr)
        return 1
    if len(set(handles)) != len(handles):
        print("# two slots sharing a handle global, refusing", file=sys.stderr)
        return 1
    separation = check_separation(slots)
    families: dict[str, int] = {}
    for slot in slots:
        name = MODEL_NAMES[slot[4]]
        family = name if slot[4] >= 366 else "Weapon"
        families[family] = families.get(family, 0) + 1
    print(f"# {len(slots)} slots, families {families}, "
          f"closest pair {separation:.2f} units", file=sys.stderr)
    if separation < MINIMUM_SLOT_SEPARATION:
        print("# pair closer than the matching tolerance allows, refusing",
              file=sys.stderr)
        return 1
    foreign = check_foreign_separation(slots, shop_stands, creations)
    print(f"# {len(shop_stands)} shop stands, nearest same-type pickup no table "
          f"owns {foreign:.2f} units from one a table does", file=sys.stderr)
    if foreign <= 0.0:
        print("# a foreign pickup sits on top of a slot, refusing", file=sys.stderr)
        return 1
    # Read before the open below truncates the file the names are in.
    names = carried_names(output_path, len(slots))
    print(f"# carried {len(names)} audited names forward", file=sys.stderr)

    # CRLF unconditionally, matching the tree. Writing LF into a CRLF tree makes
    # a regenerated file a whole-file diff that hides the real change. Reading
    # the existing file to decide would preserve a wrong state as faithfully as
    # a right one, so one checkout with autocrlf=input would perpetuate LF on
    # that machine forever. The decompile is read the other way, detecting its
    # endings, because that file belongs to someone else; this one is ours.
    with open(output_path, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(render_module(slots, handles, names, shop_stands,
                                   separation, foreign, mission_created_first))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
