"""Offline mod installer. Player supplies ASI Loader and CLEO.

The ASI ships whole. script deltas rebuild from stock main.scm.
Validate the executable and stock script before installing."""
from __future__ import annotations

import bisect
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path


def game_process_running() -> bool:
    """Check for gta-vc.exe"""
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq gta-vc.exe", "/NH"],
            capture_output=True, timeout=3, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return True
    # Match the ASCII name regardless of tasklist locale.
    return result.returncode != 0 or not result.stdout or b"gta-vc.exe" in result.stdout.lower()


class InstallRefused(Exception):
    """Installation refusal with a player-facing reason."""


class StockScriptRefused(InstallRefused):
    """Stock main.scm does not match the payload."""


class GameBuildRefused(InstallRefused):
    """Unsupported game executable."""


BACKUP_DIR_NAME = "AP_mod_backup"
ASI_SUFFIX = ".asi"
MAIN_SCM = "main.scm"

# Script deltas patch stock main.scm. Strip the suffix for the destination.
DELTA_SUFFIX = ".bsdiff4"

# Build manifest: stock hash and reconstructed file hashes.
PAYLOAD_MANIFEST_NAME = "payload.json"

# Uninstall manifest. Add shipped files
# main.scm restores separately.
SHIPPED_PAYLOAD_PATHS = (
    "GtaVcAp.VC.asi",
    "cleo/apwatchers.cs",
    # Separate CLEO entry points keep MAIN within its buffer limit.
    "cleo/aparea.cs",
    "cleo/aprewd.cs",
    "cleo/apradio.cs",
    # Separate script preserves main.scm save offsets.
    "cleo/appad.cs",
    # One script per shop thread, each includes shared gosub code.
    "cleo/apammu1.cs",
    "cleo/apammu2.cs",
    "cleo/apammu3.cs",
    "cleo/aphard1.cs",
    "cleo/aphard2.cs",
    "cleo/aphard3.cs",
    # Poll pickup completion each frame.
    "cleo/appickup.cs",
)

# Remove obsolete copies to prevent duplicate mod threads.
STALE_PAYLOAD_PATHS = (
    "scripts/GtaVcAp.VC.asi",
    # Keep original path casing for case-sensitive filesystems.
    "CLEO/apshops.cs",
)

# Unreadable or malformed GXT tables.
UNREADABLE_TABLE = (OSError, ValueError, struct.error)

# Pause-menu text, matches status_page.cpp.
PANEL_TEXT_KEY = "APSTAT"
PANEL_TEXT = "ARCHIPELAGO"

# Pending shop check label, matches build_scm.py.
SHOP_ITEM_TEXT_KEY = "APITEM"
SHOP_ITEM_TEXT = "AP Item"

# Completion messages without cash amounts. Matches build_scm.py.
# Keep keys under eight bytes for a NUL terminator.
PASS_TEXT_KEY = "APPASS"
PASS_TEXT = "MISSION PASSED!"
COURSE_TEXT_KEY = "APCOURS"
COURSE_TEXT = "Course Complete!"
WON_TEXT_KEY = "APWON"
WON_TEXT = "YOU HAVE WON!"

# Shared keys for patching, validation and removal.
ADDED_TEXT = {PANEL_TEXT_KEY: PANEL_TEXT, SHOP_ITEM_TEXT_KEY: SHOP_ITEM_TEXT,
              PASS_TEXT_KEY: PASS_TEXT, COURSE_TEXT_KEY: COURSE_TEXT,
              WON_TEXT_KEY: WON_TEXT}

TEXT_DIR_NAME = "TEXT"
GXT_SUFFIX = ".gxt"


def _gxt_main_table(raw: bytes) -> tuple[int, int, int, int, int]:
    """Return MAIN's TABL record, TKEY body/size and TDAT body/size.

    TABL/TKEY records are 12 bytes. TKEY sorts by key. Offsets are TDAT-relative."""
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
    """MAIN-table keys in file order."""
    _record, key_body, key_size, _data_body, _data_size = _gxt_main_table(raw)
    return [raw[key_body + index * 12 + 4:key_body + index * 12 + 12]
            .rstrip(b"\0").decode("ascii", "replace")
            for index in range(key_size // 12)]


def gxt_value(raw: bytes, key: str) -> str | None:
    """MAIN-table value, or None if absent."""
    _record, key_body, key_size, data_body, _data_size = _gxt_main_table(raw)
    for index in range(key_size // 12):
        entry = key_body + index * 12
        if raw[entry + 4:entry + 12].rstrip(b"\0").decode("ascii", "replace") != key:
            continue
        start = data_body + struct.unpack_from("<I", raw, entry)[0]
        # Scan UTF-16 code units, not overlapping byte pairs.
        end = start
        while end + 2 <= len(raw) and raw[end:end + 2] != b"\x00\x00":
            end += 2
        return raw[start:end].decode("utf-16-le")
    return None


def add_gxt_key(raw: bytes, key: str, value: str) -> bytes:
    """Add or replace a MAIN-table key.

    Append text, keep keys sorted, and shift later table offsets."""
    key_bytes = key.encode("ascii")
    if not key_bytes or len(key_bytes) > 8:
        raise ValueError(f"a text table key is one to eight bytes, not {key!r}")
    if gxt_value(raw, key) == value:
        return raw
    record_offset, key_body, key_size, data_body, data_size = _gxt_main_table(raw)
    records = [bytearray(raw[key_body + index * 12:key_body + (index + 1) * 12])
               for index in range(key_size // 12)]
    # NUL padding preserves key order.
    names = [bytes(record[4:12]).rstrip(b"\0") for record in records]
    replacing = key_bytes in names
    added_record_bytes = 0 if replacing else 12

    text = value.encode("utf-16-le") + b"\x00\x00"
    # Keep following tables four-byte aligned.
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

    # Shift later tables. MAIN stays put.
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
    """Sorted TEXT/*.gxt files. Empty if TEXT is missing."""
    text_dir = Path(install_dir) / TEXT_DIR_NAME
    if not text_dir.is_dir():
        return []
    return sorted(path for path in text_dir.iterdir()
                  if path.is_file() and path.suffix.lower() == GXT_SUFFIX)


def text_tables_are_patched(install_dir: Path) -> bool:
    """Check readable tables for all mod keys, ignore unreadable tables."""
    for path in text_tables(install_dir):
        try:
            raw = path.read_bytes()
            if any(gxt_value(raw, key) != value
                   for key, value in ADDED_TEXT.items()):
                return False
        except UNREADABLE_TABLE:
            # patch_text_tables reports unreadable files.
            continue
    return True


def patch_text_tables(install_dir: Path) -> list[str]:
    """Add mod keys. back up stock tables once. Log failures."""
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
            # Never back up an already patched table as stock.
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
    """Staged paths missing from the uninstall manifest, excluding main.scm."""
    return sorted(set(staged_relative_paths) - set(SHIPPED_PAYLOAD_PATHS) - {MAIN_SCM})


def _payload_root():
    """Bundled data/mod directory, or None if missing."""
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
    """List payload files without reading their contents."""
    names: list[str] = []
    for entry in node.iterdir():
        name = f"{prefix}{entry.name}"
        if entry.is_dir():
            names.extend(_walk_names(entry, name + "/"))
        else:
            names.append(name)
    return names


def _deployed_path(entry_name: str) -> str | None:
    """Strip the delta suffix, skip the manifest."""
    if entry_name == PAYLOAD_MANIFEST_NAME:
        return None
    if entry_name.endswith(DELTA_SUFFIX):
        return entry_name[:-len(DELTA_SUFFIX)]
    return entry_name


def payload_paths() -> list[str]:
    """List install destinations without rebuilding scripts."""
    root = _payload_root()
    if root is None:
        return []
    return sorted(path for path in (_deployed_path(name) for name in _walk_names(root))
                  if path is not None)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payload_target_sha256() -> dict[str, str]:
    """Target hashes by destination. Without a manifest, hash the files.

    Malformed manifests return no hashes, preventing an unsafe main.scm restore."""
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
    """Read and verify stock main.scm."""
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


def _read_virtual_uint32(image: bytes, virtual_address: int) -> int | None:
    """Read a uint32 at a PE virtual address"""
    try:
        if image[:2] != b"MZ":
            return None
        headers = struct.unpack_from("<I", image, 0x3C)[0]
        if (image[headers:headers + 4] != b"PE\0\0"
                or struct.unpack_from("<H", image, headers + 4)[0] != 0x14C
                or struct.unpack_from("<H", image, headers + 24)[0] != 0x10B):
            return None
        sections, = struct.unpack_from("<H", image, headers + 6)
        optional_size, = struct.unpack_from("<H", image, headers + 20)
        image_base, = struct.unpack_from("<I", image, headers + 24 + 28)
        table = headers + 24 + optional_size
        relative = virtual_address - image_base
        for index in range(sections):
            entry = table + index * 40
            _virtual_size, address, raw_size, raw_offset = struct.unpack_from(
                "<IIII", image, entry + 8)
            # Virtual zero-fill has no bytes on disk.
            offset = relative - address
            if 0 <= offset and offset + 4 <= raw_size:
                return struct.unpack_from("<I", image, raw_offset + offset)[0]
    except struct.error:
        return None
    return None


# Match plugin-sdk/shared/GameVersion.cpp prologue checks.
# Read on-disk bytes.
GAME_EXECUTABLE = "gta-vc.exe"
GAME_BUILD_PROLOGUE = 0x53E58955
GAME_BUILD_ADDRESSES: dict[str, int] = {
    "1.0 English": 0x667BF0,
    "1.1 English": 0x667C40,
    "Steam": 0x666BA0,
}
GAME_BUILD_SUPPORTED = "1.0 English"


def detect_game_build(install_dir: Path) -> str | None:
    """Recognized executable build, or None."""
    executable = Path(install_dir) / GAME_EXECUTABLE
    try:
        image = executable.read_bytes()
    except OSError:
        return None
    for name, address in GAME_BUILD_ADDRESSES.items():
        if _read_virtual_uint32(image, address) == GAME_BUILD_PROLOGUE:
            return name
    return None


def require_supported_game_build(install_dir: Path) -> None:
    """Require classic 1.0 English."""
    build = detect_game_build(install_dir)
    if build == GAME_BUILD_SUPPORTED:
        return
    if build is None:
        raise GameBuildRefused(
            f"Could not confirm {GAME_EXECUTABLE} as classic {GAME_BUILD_SUPPORTED}. "
            "Installation stopped. The file may be compressed, modified, damaged, or unsupported. "
            "Choose a game folder with a recognizable classic 1.0 English executable.")
    raise GameBuildRefused(
        f"The mod could not be installed: {GAME_EXECUTABLE} is the {build} build, "
        f"and the mod runs on the classic {GAME_BUILD_SUPPORTED} executable only. "
        "It attaches to that build and to no other, so installing here would "
        "leave you with a game that looks fine and sends no checks. This is the "
        "classic PC release and not the Definitive Edition.")


def _payload_manifest(entries: dict[str, bytes]) -> tuple[str, dict[str, str]]:
    """Read stock and target hashes"""
    reinstall = "Download and run the standalone installer again."
    manifest = entries.get(PAYLOAD_MANIFEST_NAME)
    if manifest is None:
        raise StockScriptRefused(
            f"The mod could not be installed: the installer's payload carries no "
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
    """Rebuild scripts from stock main.scm and verify target hashes.

    Return (destination, bytes) pairs"""
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
            # Stock hash passed. rebuilt mismatch means a bad payload
            raise StockScriptRefused(
                f"The mod could not be installed: patching {destination} from "
                "this install's script did not produce the file the installer "
                "was built with. Download and run the standalone installer again.")
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
    # Reject paths outside the game folder.
    root = install_dir.resolve()
    resolved = destination.resolve()
    if resolved != root and root not in resolved.parents:
        raise RuntimeError(f"payload path {relative_path} escapes the install folder")
    return destination


def _clear_stale_paths(install_dir: Path) -> list[str]:
    """Remove obsolete mod files. Log failures, leave outside paths alone."""
    log: list[str] = []
    root = install_dir.resolve()
    for stale_path in STALE_PAYLOAD_PATHS:
        stale = install_dir.joinpath(*stale_path.split("/"))
        try:
            inside = root in stale.resolve().parents
        except OSError:
            inside = False
        if not inside:
            # Do not follow junctions outside the install.
            log.append(f"Left {stale_path} alone, it resolves outside the install.")
            continue
        if not stale.is_file():
            continue
        try:
            stale.unlink()
        except OSError as error:
            # Loaded plugins may be locked
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
    """Check supported build, payload hashes and text keys.

    No payload counts as current. No stock script or patching required."""
    expected = ([(relative, _sha256(data)) for relative, data in payload]
                if payload is not None
                else sorted(payload_target_sha256().items()))
    if not expected:
        return True
    if detect_game_build(install_dir) != GAME_BUILD_SUPPORTED:
        return False
    return _install_matches(install_dir, expected)


def _install_matches(install_dir: Path, expected: list[tuple[str, str]]) -> bool:
    """Check installed files against target hashes."""
    if not expected:
        return True
    install_dir = Path(install_dir)
    # Duplicate legacy files make the install stale.
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
    # Text tables must contain all mod keys.
    return text_tables_are_patched(install_dir)


def deploy(install_dir: Path, payload: list[tuple[str, bytes]] | None = None) -> list[str]:
    """Install payload, back up stock files and patch text tables. Return logs.

    Refuse unsupported builds or scripts before writes.
    Prebuilt payloads skip script validation."""
    files = materialize_payload(install_dir) if payload is None else payload
    if not files:
        raise FileNotFoundError(
            "no mod payload in the installer. it was packaged without data/mod")
    require_supported_game_build(install_dir)
    install_dir = Path(install_dir)
    log: list[str] = []
    log.extend(_clear_stale_paths(install_dir))
    # Count changed files only.
    installed = 0
    for relative_path, data in files:
        destination = _destination(install_dir, relative_path)
        if destination.is_file() and destination.read_bytes() == data:
            continue
        # Only main.scm replaces a stock payload file.
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
    """Remove current and legacy mod files, then restore stock backups. Return logs.

    Use paths and hashes only. No patchable game files required."""
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
    # Count removed files, log stale paths separately.
    removed = 0
    for relative_path in relative_paths:
        # Restore main.scm below.
        if relative_path == MAIN_SCM:
            continue
        destination = _destination(install_dir, relative_path)
        if destination.is_file():
            destination.unlink()
            removed += 1
    if removed:
        log.append("Removed the mod from the game folder.")

    # Keep CLEO if user files remain
    cleo_dir = install_dir / "CLEO"
    if cleo_dir.is_dir() and not any(cleo_dir.iterdir()):
        cleo_dir.rmdir()
        log.append("Removed the empty CLEO folder.")

    # Restore only over our main.scm or a missing file
    # Preserve unknown files and backups
    backup_dir = install_dir / BACKUP_DIR_NAME
    backup = backup_dir / MAIN_SCM
    installed_scm = install_dir / "data" / MAIN_SCM
    installed_bytes = installed_scm.read_bytes() if installed_scm.is_file() else None
    installed_is_ours = (installed_bytes is not None
                         and _sha256(installed_bytes) == payload_scm_sha256)
    keep_backup = False
    if backup.is_file():
        if installed_bytes == backup.read_bytes():
            pass  # Already stock
        elif installed_bytes is None or installed_is_ours:
            installed_scm.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, installed_scm)
            log.append("Restored the stock main.scm.")
        else:
            keep_backup = True
            log.append("data/main.scm was not recognized, so it was left alone. "
                       f"the stock backup stays in {BACKUP_DIR_NAME}.")
    elif installed_is_ours:
        log.append("No main.scm backup found, so the modded main.scm is still "
                   "in place. Restore data/main.scm from your own copy of the "
                   "game files.")

    # Restore only tables carrying our keys.
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
            # Already stock, remove the leftover backup.
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

    # Delete only known backupsF
    if not keep_backup:
        if backup.is_file():
            backup.unlink()
        if backup_dir.is_dir() and not any(backup_dir.iterdir()):
            backup_dir.rmdir()
            log.append("Removed the mod backup folder.")
    return log
