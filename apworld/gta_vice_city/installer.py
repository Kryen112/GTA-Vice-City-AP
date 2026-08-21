"""Installs the GTA Vice City mod into a game install, from the client.

A packaged apworld may carry the mod under ``data/mod`` (staged by
build_apworld.py once the mod is complete): the compiled ASI, the CLEO scripts,
and the compiled main.scm. ``deploy`` copies each file to its place in the
install, backing up any stock file it replaces, and is idempotent. It installs
only our own files; the player supplies Ultimate ASI Loader and CLEO.

When the apworld carries no payload, every entry point here is a no-op, so the
installer can ship before the mod does without touching a game install.

Deploy also patches the game's text tables, which no payload file can replace:
the pause menu's Archipelago entry is a GXT key, and the key has to exist in the
table the running game loaded. Every ``TEXT/*.gxt`` gains one key, backed up
first like main.scm.

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
import shutil
import struct
from pathlib import Path

BACKUP_DIR_NAME = "AP_mod_backup"
ASI_SUFFIX = ".asi"
MAIN_SCM = "main.scm"

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
)

# Places an earlier build put a payload file that it no longer uses. The ASI
# loader scans both the install root and scripts, so a copy left in scripts is
# loaded as a second instance beside the current one: two frame hooks, two
# pickup pool walks, and two writers to one log. Deploy clears these so an
# install made by an older build heals itself.
STALE_PAYLOAD_PATHS = ("scripts/GtaVcAp.VC.asi",)

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
    """Whether every text table in the install carries the panel key. An install
    with no readable text table counts as patched, so a folder this installer
    cannot help never holds up an install."""
    for path in text_tables(install_dir):
        try:
            if gxt_value(path.read_bytes(), PANEL_TEXT_KEY) != PANEL_TEXT:
                return False
        except UNREADABLE_TABLE:
            # Unreadable, or not a text table after all: patching it would fail
            # the same way, and reporting it there beats blocking here.
            continue
    return True


def patch_text_tables(install_dir: Path) -> list[str]:
    """Add the panel key to every text table in the install, backing each stock
    file up once. Idempotent, and never raises: a file it cannot patch is
    reported and left as it was, which costs the menu entry its label and
    nothing else."""
    install_dir = Path(install_dir)
    log: list[str] = []
    for path in text_tables(install_dir):
        try:
            raw = path.read_bytes()
            if gxt_value(raw, PANEL_TEXT_KEY) == PANEL_TEXT:
                continue
            patched = add_gxt_key(raw, PANEL_TEXT_KEY, PANEL_TEXT)
            # Only a table without the key at all is stock enough to back up. A
            # table already carrying it with some other value is one an earlier
            # build patched, and saving that as the stock copy would lose the real
            # one for good.
            if gxt_value(raw, PANEL_TEXT_KEY) is None:
                _backup_once(install_dir, path)
            path.write_bytes(patched)
        except UNREADABLE_TABLE as error:
            log.append(f"Could not add the menu text to {TEXT_DIR_NAME}/{path.name}: "
                       f"{error}.")
            continue
        log.append(f"Added the menu text to {TEXT_DIR_NAME}/{path.name}.")
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


def payload_files() -> list[tuple[str, bytes]]:
    """Every file in the bundled mod payload, as (posix relative path, bytes).
    Empty when the apworld carries no payload."""
    root = _payload_root()
    if root is None:
        return []
    return sorted(_walk(root))


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
    install loop."""
    files = payload_files() if payload is None else payload
    if not files:
        return True
    install_dir = Path(install_dir)
    # A leftover copy from an earlier build is loaded as a second instance, so
    # an install carrying one is not current however well its own files match:
    # the client skips deploy on current, which would keep the duplicate.
    for stale_path in STALE_PAYLOAD_PATHS:
        if install_dir.joinpath(*stale_path.split("/")).is_file():
            return False
    for relative_path, data in files:
        destination = _destination(install_dir, relative_path)
        try:
            if destination.read_bytes() != data:
                return False
        except OSError:
            return False
    # The menu text is part of the install, and it lives in a game file rather
    # than in a payload file, so a table still missing the key is not current.
    return text_tables_are_patched(install_dir)


def deploy(install_dir: Path, payload: list[tuple[str, bytes]] | None = None) -> list[str]:
    """Copy the bundled mod into the install, backing up any stock file it
    replaces. Idempotent. Returns log lines."""
    files = payload_files() if payload is None else payload
    if not files:
        raise FileNotFoundError(
            "no mod payload in the apworld; it was packaged without data/mod")
    install_dir = Path(install_dir)
    log: list[str] = []
    log.extend(_clear_stale_paths(install_dir))
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
        log.append(f"Installed {relative_path}.")
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
    Returns log lines; an empty list means the install was already stock."""
    files = payload_files() if payload is None else payload
    install_dir = Path(install_dir)
    log: list[str] = []

    log.extend(_clear_stale_paths(install_dir))
    relative_paths = sorted({relative for relative, _ in files} | set(SHIPPED_PAYLOAD_PATHS))
    for relative_path in relative_paths:
        # main.scm is a stock file: it is restored from its backup below,
        # never deleted.
        if relative_path == MAIN_SCM:
            continue
        destination = _destination(install_dir, relative_path)
        if destination.is_file():
            destination.unlink()
            log.append(f"Removed {relative_path}.")

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
    payload_scm = dict(files).get(MAIN_SCM)
    installed_bytes = installed_scm.read_bytes() if installed_scm.is_file() else None
    keep_backup = False
    if backup.is_file():
        if installed_bytes == backup.read_bytes():
            pass  # already stock; only the backup is left to clean up
        elif installed_bytes is None or installed_bytes == payload_scm:
            installed_scm.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, installed_scm)
            log.append("Restored the stock main.scm.")
        else:
            keep_backup = True
            log.append("data/main.scm was not recognized, so it was left alone; "
                       f"the stock backup stays in {BACKUP_DIR_NAME}.")
    elif payload_scm is not None and installed_bytes == payload_scm:
        log.append("No main.scm backup found, so the modded main.scm is still "
                   "in place. Restore data/main.scm from your own copy of the "
                   "game files.")

    # The text tables come back from their backups, and only over a file that
    # still carries the key this mod added: anything else is the player's own
    # file, and it stays.
    for path in text_tables(install_dir):
        table_backup = backup_dir / path.name
        try:
            was_patched = gxt_value(path.read_bytes(), PANEL_TEXT_KEY) is not None
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
            log.append(f"No backup for {TEXT_DIR_NAME}/{path.name}, so the menu "
                       "text this mod added to it stays. Nothing reads that key "
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
