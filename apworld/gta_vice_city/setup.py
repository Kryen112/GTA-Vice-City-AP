"""Offline installation using Archipelago's bundled runtime and folder picker."""

from pathlib import Path

import Utils

from . import installer

TITLE = "GTA Vice City Setup"
CONNECTION_TEMPLATE = "[archipelago]\nserver=127.0.0.1:38281\nslot=\npassword=\n"


def check_folder(install_dir: Path) -> None:
    if not (install_dir / "gta-vc.exe").is_file():
        raise installer.InstallRefused("Choose the game folder containing gta-vc.exe.")
    if installer.game_process_running():
        raise installer.InstallRefused("Close Vice City before running setup.")


def install(install_dir: Path) -> list[str]:
    check_folder(install_dir)
    log = installer.deploy(install_dir)
    settings_path = install_dir / "GtaVcAp.VC.ini"
    try:
        with settings_path.open("x", encoding="utf-8") as settings_file:
            settings_file.write(CONNECTION_TEMPLATE)
    except FileExistsError:
        pass
    log.append("Launch Vice City and press F8 for connection settings and chat.\n"
               f"INI settings are also available at {settings_path}.\n"
               "No Python client or room connection is needed for setup.")
    return log


def uninstall(install_dir: Path) -> list[str]:
    check_folder(install_dir)
    log = installer.remove(install_dir)
    log.append("Archipelago saves and connection settings have been kept.")
    return log


def choose_action() -> str:
    """Only setup has an external window; the running client lives in the ASI."""
    import tkinter as tk
    from tkinter import ttk

    window = tk.Tk()
    window.title(TITLE)
    window.resizable(False, False)
    result = ""

    def select(action: str) -> None:
        nonlocal result
        result = action
        window.destroy()

    frame = ttk.Frame(window, padding=20)
    frame.pack()
    ttk.Label(frame, text="Vice City already has the Archipelago mod installed.").pack(pady=(0, 16))
    for label, action in (("Install / update", "install"), ("Uninstall mod", "uninstall"), ("Cancel", "")):
        ttk.Button(frame, text=label, command=lambda choice=action: select(choice)).pack(fill="x", pady=3)
    window.mainloop()
    return result


def launch(install_folder: str = "") -> None:
    try:
        folder = install_folder or Utils.open_directory("Select the folder containing gta-vc.exe")
        if not folder:
            return
        install_dir = Path(folder)
        action = choose_action() if (install_dir / "GtaVcAp.VC.asi").exists() else "install"
        if not action:
            return
        log = uninstall(install_dir) if action == "uninstall" else install(install_dir)
    except Exception as error:
        Utils.messagebox(TITLE, str(error), error=True)
        return
    Utils.messagebox(TITLE, "\n\n".join(log))
