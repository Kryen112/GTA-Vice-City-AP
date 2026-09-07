"""Offline installation using Archipelago's bundled runtime and folder picker."""

from pathlib import Path

import Utils

from . import installer

TITLE = "GTA Vice City Setup"
CONNECTION_TEMPLATE = "[archipelago]\nserver=127.0.0.1:38281\nslot=\npassword=\n"


def install(install_dir: Path) -> list[str]:
    if not (install_dir / "gta-vc.exe").is_file():
        raise installer.InstallRefused("Choose the game folder containing gta-vc.exe.")
    if installer.game_process_running():
        raise installer.InstallRefused("Close Vice City before running setup.")
    log = installer.deploy(install_dir)
    settings_path = install_dir / "GtaVcAp.VC.ini"
    try:
        with settings_path.open("x", encoding="utf-8") as settings_file:
            settings_file.write(CONNECTION_TEMPLATE)
    except FileExistsError:
        pass
    log.append(f"Set your server and slot in {settings_path}, then launch Vice City directly.\n"
               "No Python client or room connection is needed for setup.")
    return log


def launch(install_folder: str = "") -> None:
    try:
        folder = install_folder or Utils.open_directory("Select the folder containing gta-vc.exe")
        if not folder:
            return
        log = install(Path(folder))
    except Exception as error:
        Utils.messagebox(TITLE, str(error), error=True)
        return
    Utils.messagebox(TITLE, "\n\n".join(log))
