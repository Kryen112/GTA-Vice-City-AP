"""Builds gta_vice_city.apworld with Archipelago's own packaging and installs it.

Links the world into the Archipelago checkout's worlds folder so the core can
discover it, packages it into an .apworld using Archipelago's own
APWorldContainer to write the archipelago.json manifest, writes it to dist, and
copies it into the frozen install's custom_worlds folder. Test caches and
compiled files stay out of the archive.

    python scripts/build_apworld.py [output_dir]

The install target defaults to %ProgramData%/Archipelago/custom_worlds and is
overridable with the AP_CUSTOM_WORLDS environment variable.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import zipfile

from ap_env import WORLD_NAME, WORLD_SOURCE, archipelago_root, link_world

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent

# The world version stamped into the apworld manifest.
WORLD_VERSION = "0.1.0"

EXCLUDED_DIRECTORIES = {"__pycache__", "test", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}

# The mod payload the client's installer deploys, staged into the apworld under
# data/mod. Only our own files: the player supplies the ASI loader and CLEO. The
# compiled main.scm gates staging, since without it the mod is not playable.
MOD_ASI = REPOSITORY_ROOT / "mod" / "asi" / "plugin" / "bin" / "GTA-VC" / "Release" / "GtaVcAp.VC.asi"
MOD_CLEO_DIR = REPOSITORY_ROOT / "mod" / "cleo"
MOD_SCM = REPOSITORY_ROOT / "mod" / "scm" / "main.scm"


def _included(path: pathlib.Path) -> bool:
    if any(part in EXCLUDED_DIRECTORIES for part in path.relative_to(WORLD_SOURCE).parts):
        return False
    return path.suffix not in EXCLUDED_SUFFIXES


def _stage_mod_payload(bundle: zipfile.ZipFile) -> None:
    # The mod needs both the compiled ASI (the AP communication layer) and the
    # compiled main.scm (mission gating) to be playable. Ship a payload only
    # when both are present, so an incomplete mod never reaches a player; with
    # neither, the apworld ships without a payload and the installer no-ops.
    if not MOD_ASI.is_file() and not MOD_SCM.is_file():
        print("Mod payload not staged (no compiled ASI or main.scm); the apworld "
              "ships without the auto-installer.")
        return
    if not (MOD_ASI.is_file() and MOD_SCM.is_file()):
        missing = "the compiled ASI" if not MOD_ASI.is_file() else "mod/scm/main.scm"
        print(f"Mod payload not staged: {missing} is missing, so the payload would "
              "be incomplete. Fix the build before shipping the mod.")
        return
    base = pathlib.PurePosixPath(WORLD_NAME) / "data" / "mod"
    staged = [MOD_ASI.name, "main.scm"]
    bundle.write(MOD_ASI, str(base / MOD_ASI.name))
    bundle.write(MOD_SCM, str(base / "main.scm"))
    if MOD_CLEO_DIR.is_dir():
        for script in sorted(MOD_CLEO_DIR.glob("*.cs")):
            bundle.write(script, str(base / "cleo" / script.name))
            staged.append(f"cleo/{script.name}")
    print(f"Staged mod payload: {', '.join(staged)}.")


def _install_directory() -> pathlib.Path | None:
    override = os.environ.get("AP_CUSTOM_WORLDS")
    if override:
        return pathlib.Path(override)
    program_data = os.environ.get("ProgramData")
    if program_data:
        return pathlib.Path(program_data) / "Archipelago" / "custom_worlds"
    return None


def _build_manifest() -> tuple[dict, str]:
    # Use Archipelago's own container so the manifest fields match the installed
    # core exactly. Pin the minimum core version to this checkout and leave the
    # maximum unset so newer cores still load the world.
    from Utils import tuplize_version, version_tuple
    from worlds.Files import APWorldContainer
    from worlds.gta_vice_city import GTAViceCityWorld

    container = APWorldContainer()
    container.game = GTAViceCityWorld.game
    container.world_version = tuplize_version(WORLD_VERSION)
    container.minimum_ap_version = version_tuple
    manifest_path = f"{WORLD_NAME}/archipelago.json"
    return container.get_manifest(), manifest_path


def _install(archive: pathlib.Path) -> None:
    destination_dir = _install_directory()
    if destination_dir is None:
        print("No custom_worlds folder resolved; set AP_CUSTOM_WORLDS to install it.")
        return
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / archive.name
        shutil.copyfile(archive, destination)
    except OSError as error:
        print(f"Could not install to {destination_dir}: {error}")
        return
    print(f"Installed to {destination}.")


def main() -> int:
    if not WORLD_SOURCE.is_dir():
        print(f"No world package at {WORLD_SOURCE}.")
        return 1
    root = archipelago_root()
    if root is None:
        print("No Archipelago checkout found. Set AP_ROOT or clone 0.6.7 as a sibling directory.")
        return 1
    if link_world(root) is None:
        return 1
    sys.path.insert(0, str(root))

    manifest, manifest_path = _build_manifest()

    output_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else REPOSITORY_ROOT / "dist"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{WORLD_NAME}.apworld"

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(WORLD_SOURCE.rglob("*")):
            if not path.is_file() or not _included(path):
                continue
            arcname = pathlib.PurePosixPath(WORLD_NAME) / path.relative_to(WORLD_SOURCE).as_posix()
            bundle.write(path, str(arcname))
        bundle.writestr(manifest_path, json.dumps(manifest))
        _stage_mod_payload(bundle)

    print(f"Wrote {archive} ({archive.stat().st_size} bytes).")
    _install(archive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
