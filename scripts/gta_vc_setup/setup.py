"""Offline installation shared by the launcher and standalone setup."""

import configparser
import os
import subprocess
import sys
from pathlib import Path

from . import installer

TITLE = "GTA Vice City Setup"
CONNECTION_TEMPLATE = "[archipelago]\nserver=127.0.0.1:38281\nslot=\npassword=\n"


def check_folder(install_dir: Path) -> None:
    if not (install_dir / "gta-vc.exe").is_file():
        raise installer.InstallRefused("Choose the game folder containing gta-vc.exe.")
    if installer.game_process_running():
        raise installer.InstallRefused("Close Vice City before running setup.")


def install(install_dir: Path, before_install=None) -> list[str]:
    check_folder(install_dir)
    installer.require_supported_game_build(install_dir)
    if before_install is not None:
        installer.materialize_payload(install_dir)
        before_install(install_dir)
    log = installer.deploy(install_dir)
    log.insert(0, f"Confirmed gta-vc.exe: classic {installer.GAME_BUILD_SUPPORTED}.")
    settings_path = Path(os.environ["LOCALAPPDATA"]) / "GtaVcAp" / "connection.ini"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if not settings_path.exists():
        legacy = configparser.ConfigParser(interpolation=None)
        legacy.read(install_dir / "GtaVcAp.VC.ini", encoding="utf-8-sig")
        settings = configparser.ConfigParser(interpolation=None)
        settings.read_string(CONNECTION_TEMPLATE)
        for key in settings["archipelago"]:
            if legacy.has_option("archipelago", key):
                settings["archipelago"][key] = legacy.get("archipelago", key)
        try:
            with settings_path.open("x", encoding="utf-8") as settings_file:
                settings.write(settings_file, space_around_delimiters=False)
        except FileExistsError:
            pass
    shortcut = install_dir / "Archipelago Connection Settings.lnk"
    try:
        if sys.platform == "win32":
            subprocess.run([
                "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                ("$ErrorActionPreference = 'Stop'; "
                 "$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($env:GTAVC_SETTINGS_LINK); "
                 "$shortcut.TargetPath = $env:GTAVC_SETTINGS_FILE; $shortcut.Save()"),
            ], env={**os.environ, "GTAVC_SETTINGS_LINK": str(shortcut.resolve()),
                    "GTAVC_SETTINGS_FILE": str(settings_path.resolve())},
                check=True, capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
            log.append(f"Connection settings shortcut: {shortcut}")
    except (OSError, subprocess.SubprocessError):
        log.append(f"Could not create the shortcut. Open {settings_path} directly.")
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
    window.wait_window()
    return result


def launch(install_folder: str = "", *, open_directory, messagebox,
           before_install=None) -> None:
    try:
        folder = install_folder or open_directory("Select the folder containing gta-vc.exe")
        if not folder:
            return
        install_dir = Path(folder)
        action = choose_action() if (install_dir / "GtaVcAp.VC.asi").exists() else "install"
        if not action:
            return
        log = (uninstall(install_dir) if action == "uninstall"
               else install(install_dir, before_install=before_install))
    except Exception as error:
        messagebox(TITLE, str(error), error=True)
        return
    messagebox(TITLE, "\n\n".join(log))
