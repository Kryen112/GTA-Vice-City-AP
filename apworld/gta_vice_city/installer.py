"""Installs the GTA Vice City mod into a game install, from the client.

A packaged apworld may carry the mod under ``data/mod`` (staged by
build_apworld.py once the mod is complete): the compiled ASI, the CLEO scripts,
and the compiled main.scm. ``deploy`` copies each file to its place in the
install, backing up any stock file it replaces, and is idempotent. It installs
only our own files; the player supplies Ultimate ASI Loader and CLEO.

When the apworld carries no payload, every entry point here is a no-op, so the
installer can ship before the mod does without touching a game install.

``remove`` reverses deploy: it deletes our own files and brings the backed-up
stock main.scm back, returning the install to stock.

Destinations follow the standard GTA Vice City layout:
    GtaVcAp.VC.asi -> the install root, where the ASI loader finds it
    cleo/*.cs      -> CLEO/
    main.scm       -> data/main.scm (the stock file is backed up first)
"""
from __future__ import annotations

import shutil
from pathlib import Path

BACKUP_DIR_NAME = "AP_mod_backup"
ASI_SUFFIX = ".asi"
MAIN_SCM = "main.scm"

# Every relative path any payload has ever deployed, so removal cleans a modded
# install even when this apworld carries no payload of its own. main.scm is
# absent on purpose: it is restored from its backup, never deleted. Append every
# newly shipped file and never remove entries; build_apworld.py refuses to stage
# a payload that outgrows this list.
SHIPPED_PAYLOAD_PATHS = ("GtaVcAp.VC.asi", "cleo/apwatchers.cs")


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
    for relative_path, data in files:
        destination = _destination(install_dir, relative_path)
        try:
            if destination.read_bytes() != data:
                return False
        except OSError:
            return False
    return True


def deploy(install_dir: Path, payload: list[tuple[str, bytes]] | None = None) -> list[str]:
    """Copy the bundled mod into the install, backing up any stock file it
    replaces. Idempotent. Returns log lines."""
    files = payload_files() if payload is None else payload
    if not files:
        raise FileNotFoundError(
            "no mod payload in the apworld; it was packaged without data/mod")
    install_dir = Path(install_dir)
    log: list[str] = []
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
