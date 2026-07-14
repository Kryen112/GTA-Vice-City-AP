"""Per-seed save isolation for GTA: Vice City.

Layout inside the GTA Vice City User Files folder:
    *.b                 the save slots the game reads (GTAVC1.b and so on)
    gta_vc.set          controls and display settings, left untouched
    AP_Career/          the player's normal saves, stashed while a seed is active
    AP_Seeds/<seed>/    one folder per Archipelago seed
    AP_state.json       what is stashed and which seed is active (crash recovery)

A swap moves the loose save files one at a time, not a whole directory, so it
is not atomic. Save files are only ever moved, never overwritten (a collision
raises), so a crash mid-swap preserves every save; it may leave a split set
that AP_state.json describes for a manual fix. gta_vc.set stays in place, so
the player keeps one set of controls and display settings across every seed.
"""
from __future__ import annotations

import ctypes
import json
import re
import sys
from pathlib import Path

SAVE_GLOB = "*.b"
USER_FILES_NAME = "GTA Vice City User Files"


def documents_directory() -> Path | None:
    """The user's Documents folder, following any redirection, the way the game
    finds it (SHGetFolderPath with CSIDL_PERSONAL)."""
    if sys.platform != "win32":
        return None
    personal = 5  # CSIDL_PERSONAL
    current = 0  # SHGFP_TYPE_CURRENT
    buffer = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, personal, None, current, buffer) != 0:
        return None
    return Path(buffer.value)


def user_files_directory() -> Path | None:
    documents = documents_directory()
    if documents is None:
        return None
    folder = documents / USER_FILES_NAME
    return folder if folder.is_dir() else None


def seed_folder_name(seed: str) -> str:
    """A filesystem-safe folder name for a seed."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", seed or "")
    return cleaned or "unnamed"


class SaveManager:
    def __init__(self, user_files: Path) -> None:
        self.user_files = Path(user_files)
        self.career = self.user_files / "AP_Career"
        self.seeds_root = self.user_files / "AP_Seeds"
        self.state_path = self.user_files / "AP_state.json"

    def _read_state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write_state(self, career_stashed: bool, active_seed: str | None) -> None:
        self.state_path.write_text(
            json.dumps({"career_stashed": career_stashed, "active_seed": active_seed}),
            encoding="utf-8")

    def is_isolated(self) -> bool:
        return bool(self._read_state().get("career_stashed"))

    def active_seed(self) -> str | None:
        return self._read_state().get("active_seed")

    def _seed_dir(self, seed: str) -> Path:
        return self.seeds_root / seed_folder_name(seed)

    def _saves_in(self, directory: Path) -> list[Path]:
        return sorted(directory.glob(SAVE_GLOB)) if directory.is_dir() else []

    def _move_saves(self, source: Path, destination: Path) -> int:
        saves = self._saves_in(source)
        if not saves:
            return 0
        destination.mkdir(parents=True, exist_ok=True)
        for save in saves:
            target = destination / save.name
            if target.exists():
                raise RuntimeError(f"{target} exists; refusing to overwrite a save.")
            save.rename(target)
        return len(saves)

    def isolate(self, seed: str) -> str:
        """Stash the normal saves (once), persist any other active seed, then
        load this seed (resume) or start it fresh. Returns a status line."""
        state = self._read_state()
        stashed = bool(state.get("career_stashed"))
        active = state.get("active_seed")
        folder = seed_folder_name(seed)

        if stashed and active == folder:
            return f"Already on Archipelago seed '{folder}'."

        if not stashed:
            if self._saves_in(self.career):
                raise RuntimeError(
                    f"{self.career} holds saves but state says the normal saves are "
                    "not stashed; refusing to overwrite them.")
            self._move_saves(self.user_files, self.career)
            self._write_state(True, None)
        elif active:
            destination = self._seed_dir(active)
            if self._saves_in(destination):
                raise RuntimeError(f"{destination} holds saves; cannot persist the active seed.")
            self._move_saves(self.user_files, destination)
            self._write_state(True, None)

        if self._saves_in(self.user_files):
            raise RuntimeError(f"{self.user_files} still holds saves; cannot load '{folder}'.")
        seed_dir = self._seed_dir(seed)
        if self._saves_in(seed_dir):
            self._move_saves(seed_dir, self.user_files)
            result = f"Resumed Archipelago seed '{folder}'."
        else:
            result = f"Started a fresh save set for Archipelago seed '{folder}'."
        self._write_state(True, folder)
        return result

    def restore(self) -> str:
        """Persist the active seed and move the normal saves back."""
        state = self._read_state()
        if not state.get("career_stashed"):
            return "Your normal saves are already in place; nothing to restore."
        active = state.get("active_seed")
        if self._saves_in(self.user_files):
            if not active:
                raise RuntimeError(
                    f"{self.user_files} holds saves but no active seed is recorded; not "
                    "overwriting. Resolve by hand.")
            destination = self._seed_dir(active)
            if self._saves_in(destination):
                raise RuntimeError(f"{destination} holds saves; cannot persist the seed.")
            self._move_saves(self.user_files, destination)
        self._move_saves(self.career, self.user_files)
        self._write_state(False, None)
        return "Restored your normal saves."
