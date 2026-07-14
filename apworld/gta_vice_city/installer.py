"""Installs the GTA Vice City mod into a game install, from the client.

A packaged apworld may carry the mod under ``data/mod`` (staged by
build_apworld.py once the mod is complete): the compiled ASI, the CLEO scripts,
and the compiled main.scm. ``deploy`` copies each file to its place in the
install, backing up any stock file it replaces, and is idempotent. It installs
only our own files; the player supplies Ultimate ASI Loader and CLEO.

When the apworld carries no payload, every entry point here is a no-op, so the
installer can ship before the mod does without touching a game install.

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
