"""Installs the GTA Vice City mod into a game install, from the client.

A packaged apworld may carry the mod under ``data/mod`` (staged by
build_apworld.py once the mod is complete): the compiled ASI, and a bsdiff4
delta for every file the game loads as script, which is main.scm and the CLEO
scripts. The package holds no copy of the game's script, only the differences
from it, so ``deploy`` builds those files from the install's own stock main.scm
before putting each one in its place, backing up any stock file it replaces.
Idempotent. It installs only our own files; the player supplies Ultimate ASI
Loader and CLEO.

An install whose main.scm is not the original 1.0 script cannot be patched, and
that is a refusal (``StockScriptRefused``) naming what was found, never a
best effort: a patch applied to the wrong bytes makes a game that fails
somewhere else entirely. Removal never patches anything, so it works on an
install that cannot be deployed to.

When the apworld carries no payload, every entry point here is a no-op, so the
installer can ship before the mod does without touching a game install.

Deploy also patches the game's text tables, which no payload file can replace:
the pause menu's Archipelago entry and the name a weapon shop gives a stand whose
check is still to be taken are both GXT keys, and a key has to exist in the table
the running game loaded. Every ``TEXT/*.gxt`` gains the keys in ``ADDED_TEXT``,
backed up first like main.scm.

``remove`` reverses deploy: it deletes our own files and brings the backed-up
stock main.scm and text tables back, returning the install to stock.

Destinations follow the standard GTA Vice City layout:
    GtaVcAp.VC.asi -> the install root, where the ASI loader finds it
    cleo/*.cs      -> CLEO/
    main.scm       -> data/main.scm (the stock file is backed up first)
    TEXT/*.gxt     -> patched in place (each stock file is backed up first)
"""
from __future__ import annotations

import bisect
import hashlib
import json
import shutil
import struct
from pathlib import Path


class StockScriptRefused(Exception):
    """The install's own main.scm is not the script the payload patches.

    Carries the whole player-facing message, since every way to raise it has
    something specific to say about what was found and how to put it right.
    """

BACKUP_DIR_NAME = "AP_mod_backup"
ASI_SUFFIX = ".asi"
MAIN_SCM = "main.scm"

# The payload carries no copy of the game's script. Every file the game's script
# layer loads, main.scm and every CLEO script, ships as a bsdiff4 delta against
# the player's own stock main.scm and is reconstructed here at deploy time; only
# the ASI, which is our own compiled code, ships whole. Deltas keep their
# destination's name with this suffix on the end, so the path a delta deploys to
# is its own name with the suffix taken off.
DELTA_SUFFIX = ".bsdiff4"

# What the build writes beside the deltas: the sha256 of the stock main.scm they
# were taken against, and the sha256 each one must reconstruct. Reading the
# hashes from the payload rather than from constants here means a rebuilt payload
# carries its own, and nothing in this file has to be edited to match it.
PAYLOAD_MANIFEST_NAME = "payload.json"

# Every relative path any payload has ever deployed, so removal cleans a modded
# install even when this apworld carries no payload of its own. main.scm is
# absent on purpose: it is restored from its backup, never deleted. Append every
# newly shipped file and never remove entries; build_apworld.py refuses to stage
# a payload that outgrows this list.
SHIPPED_PAYLOAD_PATHS = (
    "GtaVcAp.VC.asi",
    "cleo/apwatchers.cs",
    # Three threads that used to live in main.scm and now ship as their own CLEO
    # scripts, because the MAIN script buffer is fixed and was almost full. Each
    # runs from its own entry point, which is why they are separate files rather
    # than one: two loops in a single .cs would fall through into each other.
    "cleo/aparea.cs",
    "cleo/aprewd.cs",
    "cleo/apradio.cs",
    # The pad warps, which ship the same way and for a second reason besides the
    # buffer: keeping them out of main.scm leaves its size alone, so adding them
    # cannot shift a script offset a save in progress still points at.
    "cleo/appad.cs",
    # The six weapon shop threads, one file each, the same reason as the three
    # above. They gosub subroutines that live in one of the six, so every file
    # carries a copy of that one's body; the copies are reachable only through
    # those gosubs. One file for all six is not possible: starting a thread at a
    # label inside a .cs needs an opcode CLEO does not override.
    "cleo/apammu1.cs",
    "cleo/apammu2.cs",
    "cleo/apammu3.cs",
    "cleo/aphard1.cs",
    "cleo/aphard2.cs",
    "cleo/aphard3.cs",
    # apshops.cs, the one build that shipped those six as a single file, is NOT
    # here. It is on STALE_PAYLOAD_PATHS instead, and remove() reads both lists,
    # so an uninstall still cleans it. On both lists it would resolve to one
    # destination twice, and deploy would write it and then clear it as stale on
    # every run; a test refuses that overlap.

    # Pickup detection: one pass per frame over all 110 ambient slots, asking
    # the game whether each has been collected and latching its completion
    # global. Its own file because a CLEO script runs from its own entry point.
    "cleo/appickup.cs",
)

# Places an earlier build put a payload file that it no longer uses. The ASI
# loader scans both the install root and scripts, so a copy left in scripts is
# loaded as a second instance beside the current one: two frame hooks, two
# pickup pool walks, and two writers to one log. Deploy clears these so an
# install made by an older build heals itself.
STALE_PAYLOAD_PATHS = (
    "scripts/GtaVcAp.VC.asi",
    # One build shipped the six weapon shops as a single apshops.cs. Left in
    # place it runs beside the six that replaced it, so every shop thread exists
    # twice, and it carries the start_new_script the split exists to remove.
    # Listed here as well as in SHIPPED_PAYLOAD_PATHS because that one is only
    # read by remove(); this is the list deploy() clears and is_current() tests.
    #
    # Spelled CLEO, not cleo: these entries are joined literally, so each has to
    # name the folder the build that wrote it actually used, and deploy sends a
    # cleo/ payload path through _destination to CLEO/. Windows would forgive the
    # difference and a case-sensitive filesystem would not.
    "CLEO/apshops.cs",
)

# What a half-written or truncated text table raises on its way through the
# readers below. struct.error is neither OSError nor ValueError, so it has to be
# named: the callers are documented never to raise, and one of them runs inside
# remove() after the payload files are already gone.
UNREADABLE_TABLE = (OSError, ValueError, struct.error)

# The text the pause menu's Archipelago entry and page title read, and the GXT
# key they read it from. A key is eight bytes and no more, which is why the name
# is shortened; the same string is spelled out in the mod's status_page.cpp,
# which looks the key up to decide whether the table was patched.
PANEL_TEXT_KEY = "APSTAT"
PANEL_TEXT = "ARCHIPELAGO"

# What a weapon shop calls a stand whose check is still to be taken. The stand
# wears the AP marker and the name over it has to agree, since a stand calling
# itself "Chainsaw" while it hands nothing over says the opposite. Mirrors
# build_scm.SHOP_PENDING_NAME_KEY, the key the shop threads print, and is pinned
# by check_scm_mirrors.
SHOP_ITEM_TEXT_KEY = "APITEM"
SHOP_ITEM_TEXT = "AP Item"

# What a mission, a checkpoint course and a race say when they are won. The game
# spells the pass line and the reward amount into one string, so suppressing a
# vanilla reward takes the words with the number and a passed mission announces
# itself by its jingle alone; these carry the same words without the amount.
# Mirrors build_scm.PASS_TEXT_KEY, COURSE_TEXT_KEY and WON_TEXT_KEY, the keys the
# built script prints, and is pinned by check_scm_mirrors.
# The course key stops a letter short of the word to stay inside the ground the
# stock data covers: a key record's name field is eight bytes with no terminator
# of its own, and of the 2,451 keys the shipped table carries not one fills all
# eight, so a key that did would be the first the game's own comparison ever
# reads with no NUL in front of it.
PASS_TEXT_KEY = "APPASS"
PASS_TEXT = "MISSION PASSED!"
COURSE_TEXT_KEY = "APCOURS"
COURSE_TEXT = "Course Complete!"
WON_TEXT_KEY = "APWON"
WON_TEXT = "YOU HAVE WON!"

# Every key this mod adds to a text table, by key. The check, the patch and the
# removal all read this rather than naming a key each, so a key added here is
# added, healed and taken back out with the others.
ADDED_TEXT = {PANEL_TEXT_KEY: PANEL_TEXT, SHOP_ITEM_TEXT_KEY: SHOP_ITEM_TEXT,
              PASS_TEXT_KEY: PASS_TEXT, COURSE_TEXT_KEY: COURSE_TEXT,
              WON_TEXT_KEY: WON_TEXT}

TEXT_DIR_NAME = "TEXT"
GXT_SUFFIX = ".gxt"


def _gxt_main_table(raw: bytes) -> tuple[int, int, int, int, int]:
    """Where the MAIN table of a text table file lives: the offset of its TABL
    record, its TKEY body and size, and its TDAT body and size. Raises
    ValueError on anything that is not a Vice City text table.

    Layout: a TABL chunk of 12-byte records (an eight-byte table name and the
    table's absolute file offset), then the tables themselves. MAIN opens
    directly with its TKEY chunk; every later table is preceded by its own name.
    A TKEY record is a TDAT-relative offset and an eight-byte key, and the
    records are sorted by key, which is what lets the game binary-search them.
    """
    if raw[0:4] != b"TABL":
        raise ValueError("not a Vice City text table: no TABL chunk")
    table_size = struct.unpack_from("<I", raw, 4)[0]
    for index in range(table_size // 12):
        record = 8 + index * 12
        if raw[record:record + 8].rstrip(b"\0") != b"MAIN":
            continue
        offset = struct.unpack_from("<I", raw, record + 8)[0]
        if raw[offset:offset + 4] != b"TKEY":
            raise ValueError("the MAIN table does not open with a TKEY chunk")
        key_size = struct.unpack_from("<I", raw, offset + 4)[0]
        key_body = offset + 8
        data_header = key_body + key_size
        if raw[data_header:data_header + 4] != b"TDAT":
            raise ValueError("the MAIN table has no TDAT chunk")
        data_size = struct.unpack_from("<I", raw, data_header + 4)[0]
        return record, key_body, key_size, data_header + 8, data_size
    raise ValueError("the text table has no MAIN table")


def gxt_keys(raw: bytes) -> list[str]:
    """Every key in a file's MAIN table, in the file's own order."""
    _record, key_body, key_size, _data_body, _data_size = _gxt_main_table(raw)
    return [raw[key_body + index * 12 + 4:key_body + index * 12 + 12]
            .rstrip(b"\0").decode("ascii", "replace")
            for index in range(key_size // 12)]


def gxt_value(raw: bytes, key: str) -> str | None:
    """What a MAIN-table key reads, or None when the file has no such key."""
    _record, key_body, key_size, data_body, _data_size = _gxt_main_table(raw)
    for index in range(key_size // 12):
        entry = key_body + index * 12
        if raw[entry + 4:entry + 12].rstrip(b"\0").decode("ascii", "replace") != key:
            continue
        start = data_body + struct.unpack_from("<I", raw, entry)[0]
        # The terminator is a zero character, so the scan steps a character at a
        # time: a zero pair straddling two characters is not the end of the
        # string, only the low byte of one and the high byte of the next.
        end = start
        while end + 2 <= len(raw) and raw[end:end + 2] != b"\x00\x00":
            end += 2
        return raw[start:end].decode("utf-16-le")
    return None


def add_gxt_key(raw: bytes, key: str, value: str) -> bytes:
    """A text table whose MAIN table carries one key reading one value, or the
    same bytes back when it already does.

    The string is appended past the end of the existing text, so every offset
    already in the file stays valid and only one record has to be written. A key
    that is not there yet takes a new record, placed in sort order because the
    game binary-searches the keys; a key already there with some other value has
    its own record repointed at the new string, which is what lets a changed
    value heal a table an earlier build patched. The tables after MAIN move down
    by what MAIN grew, so their TABL offsets move with them.
    """
    key_bytes = key.encode("ascii")
    if not key_bytes or len(key_bytes) > 8:
        raise ValueError(f"a text table key is one to eight bytes, not {key!r}")
    if gxt_value(raw, key) == value:
        return raw
    record_offset, key_body, key_size, data_body, data_size = _gxt_main_table(raw)
    records = [bytearray(raw[key_body + index * 12:key_body + (index + 1) * 12])
               for index in range(key_size // 12)]
    # A key field is NUL-padded and no key holds a NUL, so comparing the padded
    # fields and comparing the trimmed names give the same order.
    names = [bytes(record[4:12]).rstrip(b"\0") for record in records]
    replacing = key_bytes in names
    added_record_bytes = 0 if replacing else 12

    text = value.encode("utf-16-le") + b"\x00\x00"
    # The vanilla file starts every table on a four-byte boundary, so the string
    # is padded to keep that true for the tables after MAIN.
    while (added_record_bytes + len(text)) % 4:
        text += b"\x00\x00"
    if replacing:
        struct.pack_into("<I", records[names.index(key_bytes)], 0, data_size)
    else:
        records.insert(bisect.bisect_left(names, key_bytes),
                       bytearray(struct.pack("<I", data_size) +
                                 key_bytes.ljust(8, b"\x00")))

    patched = bytearray()
    patched += raw[:key_body - 8]
    patched += b"TKEY" + struct.pack("<I", key_size + added_record_bytes)
    for record in records:
        patched += record
    patched += b"TDAT" + struct.pack("<I", data_size + len(text))
    patched += raw[data_body:data_body + data_size]
    patched += text
    patched += raw[data_body + data_size:]

    # Every table below MAIN moved down by what MAIN grew. MAIN's own record is
    # left alone: it is the first table and its offset has not moved.
    shift = added_record_bytes + len(text)
    main_offset = struct.unpack_from("<I", patched, record_offset + 8)[0]
    table_size = struct.unpack_from("<I", patched, 4)[0]
    for index in range(table_size // 12):
        record = 8 + index * 12
        offset = struct.unpack_from("<I", patched, record + 8)[0]
        if offset > main_offset:
            struct.pack_into("<I", patched, record + 8, offset + shift)
    return bytes(patched)


def text_tables(install_dir: Path) -> list[Path]:
    """Every text table file in the install, in a stable order. Empty when the
    folder is missing, which is not this installer's problem to report: a game
    without text tables does not run."""
    text_dir = Path(install_dir) / TEXT_DIR_NAME
    if not text_dir.is_dir():
        return []
    return sorted(path for path in text_dir.iterdir()
                  if path.is_file() and path.suffix.lower() == GXT_SUFFIX)


def text_tables_are_patched(install_dir: Path) -> bool:
    """Whether every text table in the install carries every key this mod adds.
    An install with no readable text table counts as patched, so a folder this
    installer cannot help never holds up an install."""
    for path in text_tables(install_dir):
        try:
            raw = path.read_bytes()
            if any(gxt_value(raw, key) != value
                   for key, value in ADDED_TEXT.items()):
                return False
        except UNREADABLE_TABLE:
            # Unreadable, or not a text table after all: patching it would fail
            # the same way, and reporting it there beats blocking here.
            continue
    return True


def patch_text_tables(install_dir: Path) -> list[str]:
    """Add this mod's keys to every text table in the install, backing each stock
    file up once. Idempotent, and never raises: a file it cannot patch is
    reported and left as it was, which costs the menu entry its label and a
    pending shop stand its name, and nothing else."""
    install_dir = Path(install_dir)
    log: list[str] = []
    for path in text_tables(install_dir):
        try:
            raw = path.read_bytes()
            patched = raw
            for key, value in ADDED_TEXT.items():
                patched = add_gxt_key(patched, key, value)
            if patched == raw:
                continue
            # Only a table carrying NONE of the keys is stock enough to back up.
            # A table already carrying one is one an earlier build patched, and
            # saving that as the stock copy would lose the real one for good.
            if all(gxt_value(raw, key) is None for key in ADDED_TEXT):
                _backup_once(install_dir, path)
            path.write_bytes(patched)
        except UNREADABLE_TABLE as error:
            log.append(f"Could not add the mod's text to {TEXT_DIR_NAME}/{path.name}: "
                       f"{error}.")
            continue
        log.append(f"Added the mod's text to {TEXT_DIR_NAME}/{path.name}.")
    return log


def unlisted_payload_paths(staged_relative_paths: list[str]) -> list[str]:
    """The staged payload paths remove() would not clean: not on the shipped
    list and not main.scm (restored from its backup instead of deleted). The
    build refuses to stage these, so the removal manifest can never drift."""
    return sorted(set(staged_relative_paths) - set(SHIPPED_PAYLOAD_PATHS) - {MAIN_SCM})


def _payload_root():
    """The data/mod directory carried by the apworld, as a source-checkout Path
    or an importlib.resources traversable inside a packaged .apworld. None when
    the apworld was packaged without a mod."""
    local = Path(__file__).parent / "data" / "mod"
    if local.is_dir():
        return local
    from importlib import resources
    root = resources.files(__package__) / "data" / "mod"
    return root if root.is_dir() else None


def _walk(node, prefix: str = "") -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    for entry in node.iterdir():
        name = f"{prefix}{entry.name}"
        if entry.is_dir():
            files.extend(_walk(entry, name + "/"))
        else:
            files.append((name, entry.read_bytes()))
    return files


def _walk_names(node, prefix: str = "") -> list[str]:
    """Every file in the payload by name, without reading any of them."""
    names: list[str] = []
    for entry in node.iterdir():
        name = f"{prefix}{entry.name}"
        if entry.is_dir():
            names.extend(_walk_names(entry, name + "/"))
        else:
            names.append(name)
    return names


def _deployed_path(entry_name: str) -> str | None:
    """The destination a payload entry deploys to, or None when it deploys
    nowhere. The manifest is the one entry that stays behind: it describes the
    payload rather than belonging to the install."""
    if entry_name == PAYLOAD_MANIFEST_NAME:
        return None
    if entry_name.endswith(DELTA_SUFFIX):
        return entry_name[:-len(DELTA_SUFFIX)]
    return entry_name


def payload_paths() -> list[str]:
    """Every destination the bundled payload deploys to, reading no file.

    Removal works in destinations and never needs the bytes, which is what keeps
    /uninstall working on an install this mod cannot patch: the moment the stock
    script is missing or wrong is exactly the moment someone reaches for it.
    """
    root = _payload_root()
    if root is None:
        return []
    return sorted(path for path in (_deployed_path(name) for name in _walk_names(root))
                  if path is not None)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payload_target_sha256() -> dict[str, str]:
    """What each payload file hashes to once built, by destination.

    Read from the manifest, so removal can tell a main.scm this mod installed
    from one the player put there without patching anything. A payload staged by
    hand carries no manifest and its files are already what they deploy as, so
    their own bytes answer the same question. A manifest that will not read
    leaves every destination unrecognized, which keeps removal off files it
    cannot account for.
    """
    root = _payload_root()
    if root is None:
        return {}
    manifest_file = root / PAYLOAD_MANIFEST_NAME
    if not manifest_file.is_file():
        return {name: _sha256(data) for name, data in _walk(root)}
    try:
        manifest = json.loads(manifest_file.read_bytes().decode("utf-8"))
        return dict(manifest["targets"])
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        return {}


def stock_script(install_dir: Path, expected_sha256: str) -> bytes:
    """The install's own stock main.scm, or a refusal naming what was found.

    The backup is the source once it exists, and a backup that is not the stock
    script is refused even when data/main.scm would have passed. Repairing it
    here would mean the mod silently rewriting the only copy of a game file the
    player still has, on its own reasoning about which of two files is real.

    Before there is a backup there is only data/main.scm, which is stock on an
    install this mod has never touched. Deploy backs it up in the same run, so
    this branch is the first install and nothing else.
    """
    backup = install_dir / BACKUP_DIR_NAME / MAIN_SCM
    live = install_dir / "data" / MAIN_SCM
    for path, description in ((backup, f"{BACKUP_DIR_NAME}/{MAIN_SCM}"),
                              (live, f"data/{MAIN_SCM}")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if _sha256(data) == expected_sha256:
            return data
        raise StockScriptRefused(
            f"The mod could not be installed: {description} is not the original "
            f"1.0 script. It hashes {_sha256(data)}, and the mod patches "
            f"{expected_sha256}. Restore data/{MAIN_SCM} from your own copy of "
            f"the game files, and if {BACKUP_DIR_NAME}/{MAIN_SCM} is there and "
            "is not the original, remove it.")
    raise StockScriptRefused(
        f"The mod could not be installed: no data/{MAIN_SCM} in the game "
        "folder to patch. Restore it from your own copy of the game files.")


def _payload_manifest(entries: dict[str, bytes]) -> tuple[str, dict[str, str]]:
    """The stock hash and the target hashes the payload was built with.

    Every way the manifest can fail to say those two things is one refusal, so
    nothing downstream indexes into it: a file that is json but not this json
    would otherwise leave a KeyError to reach the player as an install failure
    with no name on it.
    """
    reinstall = "Reinstall the apworld."
    manifest = entries.get(PAYLOAD_MANIFEST_NAME)
    if manifest is None:
        raise StockScriptRefused(
            f"The mod could not be installed: the apworld's payload carries no "
            f"{PAYLOAD_MANIFEST_NAME}, so nothing says which script its patches "
            f"were made against. {reinstall}")
    try:
        content = json.loads(manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StockScriptRefused(
            f"The mod could not be installed: the payload's "
            f"{PAYLOAD_MANIFEST_NAME} does not read as json ({error}). "
            f"{reinstall}") from error
    stock_sha256 = content.get("stock_main_scm_sha256") if isinstance(content, dict) else None
    targets = content.get("targets") if isinstance(content, dict) else None
    if not isinstance(stock_sha256, str) or not isinstance(targets, dict):
        raise StockScriptRefused(
            f"The mod could not be installed: the payload's "
            f"{PAYLOAD_MANIFEST_NAME} does not name the script its patches were "
            f"made against and what each one builds. {reinstall}")
    return stock_sha256, targets


def materialize_payload(install_dir: Path) -> list[tuple[str, bytes]]:
    """The bundled payload as (destination, bytes), patches applied.

    Every file the game loads as script is a delta against the player's own
    stock main.scm, so this is where the payload becomes files. Reads only, and
    measured at 11 ms for four of the thirteen patches over a 1.27 MB source, so
    deploy pays it once and nothing has to cache it.

    Each result is checked against the hash the build recorded for it, which is
    what turns a patch that applied to the wrong bytes into a refusal rather
    than a game folder full of plausible rubbish. Empty when the apworld carries
    no payload.
    """
    root = _payload_root()
    if root is None:
        return []
    entries = dict(_walk(root))
    deltas = {name: data for name, data in entries.items()
              if name.endswith(DELTA_SUFFIX)}
    if not deltas:
        return sorted((name, data) for name, data in entries.items()
                      if _deployed_path(name) is not None)
    import bsdiff4

    stock_sha256, targets = _payload_manifest(entries)
    stock = stock_script(Path(install_dir), stock_sha256)
    files: list[tuple[str, bytes]] = []
    for name, data in entries.items():
        destination = _deployed_path(name)
        if destination is None:
            continue
        if name not in deltas:
            files.append((destination, data))
            continue
        rebuilt = bsdiff4.patch(stock, data)
        if _sha256(rebuilt) != targets.get(destination):
            # The script this patched was already matched against the hash the
            # payload was built against, so the file it started from is right
            # and the payload is what disagrees with itself.
            raise StockScriptRefused(
                f"The mod could not be installed: patching {destination} from "
                "this install's script did not produce the file the apworld "
                "was built with. Reinstall the apworld.")
        files.append((destination, rebuilt))
    return sorted(files)


def _destination(install_dir: Path, relative_path: str) -> Path:
    parts = relative_path.split("/")
    if relative_path.endswith(ASI_SUFFIX):
        destination = install_dir / parts[-1]
    elif parts[0] == "cleo":
        destination = install_dir.joinpath("CLEO", *parts[1:])
    elif relative_path == MAIN_SCM:
        destination = install_dir / "data" / MAIN_SCM
    else:
        destination = install_dir.joinpath(*parts)
    # A payload path must stay inside the install, never escape it.
    root = install_dir.resolve()
    resolved = destination.resolve()
    if resolved != root and root not in resolved.parents:
        raise RuntimeError(f"payload path {relative_path} escapes the install folder")
    return destination


def _clear_stale_paths(install_dir: Path) -> list[str]:
    """Delete every place an earlier build left a payload file it no longer
    uses. Returns log lines. The paths are fixed literals under the install, and
    the resolve check holds that guarantee rather than trusting the constant.
    Never raises: a path it cannot take is reported and left alone."""
    log: list[str] = []
    root = install_dir.resolve()
    for stale_path in STALE_PAYLOAD_PATHS:
        stale = install_dir.joinpath(*stale_path.split("/"))
        try:
            inside = root in stale.resolve().parents
        except OSError:
            inside = False
        if not inside:
            # A junctioned folder puts the path somewhere else on the disk,
            # which is not ours to delete.
            log.append(f"Left {stale_path} alone, it resolves outside the install.")
            continue
        if not stale.is_file():
            continue
        try:
            stale.unlink()
        except OSError as error:
            # The running game holds its loaded plugins open. Reporting beats
            # raising: mod_is_current stays false, so the next launch retries.
            log.append(f"Could not remove {stale_path}: {error}.")
            continue
        log.append(f"Removed {stale_path}, which an earlier build left behind.")
    return log


def _backup_once(install_dir: Path, path: Path) -> None:
    backup_dir = install_dir / BACKUP_DIR_NAME
    backup_dir.mkdir(exist_ok=True)
    destination = backup_dir / path.name
    if path.is_file() and not destination.exists():
        shutil.copy2(path, destination)


def mod_is_current(install_dir: Path, payload: list[tuple[str, bytes]] | None = None) -> bool:
    """Whether the install already runs this apworld's mod, byte for byte. An
    apworld packaged without a mod counts as current, so it never triggers an
    install loop.

    Answered from the hashes the payload records, so it never patches anything
    and never needs the stock script. Building the payload to answer would make
    an install that is already correct read as stale the moment its backup went
    missing, and deploy would then refuse to rebuild what is already in place
    and hold the game shut over a file nobody needs any more.
    """
    if payload is not None:
        return _install_matches(install_dir, [(relative, _sha256(data))
                                              for relative, data in payload])
    return _install_matches(install_dir, sorted(payload_target_sha256().items()))


def _install_matches(install_dir: Path, expected: list[tuple[str, str]]) -> bool:
    """Whether every destination holds the file the payload would put there,
    each named by the sha256 it has to have."""
    if not expected:
        return True
    install_dir = Path(install_dir)
    # A leftover copy from an earlier build is loaded as a second instance, so
    # an install carrying one is not current however well its own files match:
    # the client skips deploy on current, which would keep the duplicate.
    for stale_path in STALE_PAYLOAD_PATHS:
        if install_dir.joinpath(*stale_path.split("/")).is_file():
            return False
    for relative_path, expected_sha256 in expected:
        destination = _destination(install_dir, relative_path)
        try:
            if _sha256(destination.read_bytes()) != expected_sha256:
                return False
        except OSError:
            return False
    # The mod's text is part of the install, and it lives in game files rather
    # than in payload files, so a table missing any key in ADDED_TEXT is not
    # current.
    return text_tables_are_patched(install_dir)


def deploy(install_dir: Path, payload: list[tuple[str, bytes]] | None = None) -> list[str]:
    """Build the bundled mod from the install's own script and put it in place,
    backing up any stock file it replaces. Idempotent. Returns log lines.

    Raises StockScriptRefused when the install's main.scm is not the script the
    payload patches, with the whole message for the player in it. A payload
    handed in directly skips that check, since it is already files rather than
    patches: the tests are what pass one, and it is the one way left to record a
    backup nothing verified.
    """
    files = materialize_payload(install_dir) if payload is None else payload
    if not files:
        raise FileNotFoundError(
            "no mod payload in the apworld; it was packaged without data/mod")
    install_dir = Path(install_dir)
    log: list[str] = []
    log.extend(_clear_stale_paths(install_dir))
    # Counted rather than listed. The payload is one mod in a dozen files, and a
    # player reading this wants to know it is in place, not which files carry it.
    # A file the install already has is not counted, so a run that changes
    # nothing still says so.
    installed = 0
    for relative_path, data in files:
        destination = _destination(install_dir, relative_path)
        if destination.is_file() and destination.read_bytes() == data:
            continue
        # Only main.scm is a stock file we replace, so only it is backed up; the
        # ASI and CLEO scripts are our own additions.
        if destination.is_file() and relative_path == MAIN_SCM:
            _backup_once(install_dir, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        installed += 1
    if installed:
        log.append("Installed the mod into the game folder.")
    log.extend(patch_text_tables(install_dir))
    if not log:
        log.append("The mod is already up to date.")
    return log


def remove(install_dir: Path, payload: list[tuple[str, bytes]] | None = None) -> list[str]:
    """Take the deployed mod back out of the install, reversing deploy: our own
    files are deleted and the backed-up stock main.scm comes back. Removal
    covers the bundled payload plus every file the mod has ever shipped, so an
    apworld packaged without a payload still cleans a modded install. Missing
    pieces are skipped, so a partial install cleans up the same way. Idempotent.
    Returns log lines; an empty list means the install was already stock.

    Reads the payload's destinations and the hash of the main.scm it would have
    installed, never the payload's bytes, so an install whose script cannot be
    patched still uninstalls. That is the install a player most wants to undo.
    """
    if payload is None:
        payload_destinations = payload_paths()
        payload_scm_sha256 = payload_target_sha256().get(MAIN_SCM)
    else:
        payload_destinations = [relative for relative, _ in payload]
        payload_scm_bytes = dict(payload).get(MAIN_SCM)
        payload_scm_sha256 = (None if payload_scm_bytes is None
                              else _sha256(payload_scm_bytes))
    install_dir = Path(install_dir)
    log: list[str] = []

    log.extend(_clear_stale_paths(install_dir))
    relative_paths = sorted(set(payload_destinations) | set(SHIPPED_PAYLOAD_PATHS))
    # Counted, like the install. The paths an earlier build left behind stay
    # named individually below, since one of those is news rather than routine.
    removed = 0
    for relative_path in relative_paths:
        # main.scm is a stock file: it is restored from its backup below,
        # never deleted.
        if relative_path == MAIN_SCM:
            continue
        destination = _destination(install_dir, relative_path)
        if destination.is_file():
            destination.unlink()
            removed += 1
    if removed:
        log.append("Removed the mod from the game folder.")

    # Removing the CLEO folder only when empty can never take a player file;
    # the player's own CLEO runtime files and scripts keep it alive.
    cleo_dir = install_dir / "CLEO"
    if cleo_dir.is_dir() and not any(cleo_dir.iterdir()):
        cleo_dir.rmdir()
        log.append("Removed the empty CLEO folder.")

    # main.scm is restored from its backup only over a file this mod put there
    # (or none at all). An unrecognized file is player-authored, so it stays,
    # and so does the backup for a by-hand restore.
    backup_dir = install_dir / BACKUP_DIR_NAME
    backup = backup_dir / MAIN_SCM
    installed_scm = install_dir / "data" / MAIN_SCM
    installed_bytes = installed_scm.read_bytes() if installed_scm.is_file() else None
    installed_is_ours = (installed_bytes is not None
                         and _sha256(installed_bytes) == payload_scm_sha256)
    keep_backup = False
    if backup.is_file():
        if installed_bytes == backup.read_bytes():
            pass  # already stock; only the backup is left to clean up
        elif installed_bytes is None or installed_is_ours:
            installed_scm.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, installed_scm)
            log.append("Restored the stock main.scm.")
        else:
            keep_backup = True
            log.append("data/main.scm was not recognized, so it was left alone; "
                       f"the stock backup stays in {BACKUP_DIR_NAME}.")
    elif installed_is_ours:
        log.append("No main.scm backup found, so the modded main.scm is still "
                   "in place. Restore data/main.scm from your own copy of the "
                   "game files.")

    # The text tables come back from their backups, and only over a file that
    # still carries a key this mod added: anything else is the player's own
    # file, and it stays.
    for path in text_tables(install_dir):
        table_backup = backup_dir / path.name
        try:
            raw = path.read_bytes()
            was_patched = any(gxt_value(raw, key) is not None
                              for key in ADDED_TEXT)
        except UNREADABLE_TABLE as error:
            log.append(f"Could not read {TEXT_DIR_NAME}/{path.name}: {error}.")
            continue
        if not was_patched:
            # Stock already, whether this mod never patched it or the player put
            # their own copy back. Only its backup is left to clean up.
            if table_backup.is_file():
                table_backup.unlink()
            continue
        if not table_backup.is_file():
            log.append(f"No backup for {TEXT_DIR_NAME}/{path.name}, so the text "
                       "this mod added to it stays. Nothing reads those keys "
                       "without the mod.")
            continue
        try:
            shutil.copy2(table_backup, path)
            table_backup.unlink()
        except OSError as error:
            log.append(f"Could not restore {TEXT_DIR_NAME}/{path.name}: {error}.")
            continue
        log.append(f"Restored the stock {TEXT_DIR_NAME}/{path.name}.")

    # Only the known backup file goes, and the folder only when empty, so a
    # stray file parked there (or a backup this version does not know about)
    # survives.
    if not keep_backup:
        if backup.is_file():
            backup.unlink()
        if backup_dir.is_dir() and not any(backup_dir.iterdir()):
            backup_dir.rmdir()
            log.append("Removed the mod backup folder.")
    return log
