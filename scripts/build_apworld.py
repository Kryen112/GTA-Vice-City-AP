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

import importlib.util
import json
import os
import pathlib
import shutil
import struct
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

# What the ASI is compiled from, for the staleness check below. The harness is
# left out because it builds its own binaries and is named by no ClCompile entry,
# and nothing under src includes it. The vendored header IS in, since protocol.hpp
# includes json.hpp and the project puts third_party on the include path, so a
# vendored bump is a real recompile. Everything else the compile reads lives
# outside the repository or is not a compile input: the plugin SDK headers and
# import library, the solution file, and the per machine vcxproj.user.
ASI_SOURCE_GLOBS = (
    "mod/asi/src/**/*.cpp",
    "mod/asi/src/**/*.hpp",
    "mod/asi/third_party/**/*.hpp",
    "mod/asi/plugin/GtaVcAp.vcxproj",
)


def _included(path: pathlib.Path) -> bool:
    if any(part in EXCLUDED_DIRECTORIES for part in path.relative_to(WORLD_SOURCE).parts):
        return False
    return path.suffix not in EXCLUDED_SUFFIXES


def _installer_module():
    # Loads installer.py on its own, without importing the world package, which
    # would need the Archipelago core on the path.
    spec = importlib.util.spec_from_file_location(
        "gta_vice_city_installer", WORLD_SOURCE / "installer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stale_sources(artifact: pathlib.Path, root: pathlib.Path,
                  globs: tuple[str, ...]) -> list[str]:
    """Repository paths of sources newer than a built artifact, newest first.

    A compiled artifact can be older than the code it is built from and nothing
    about the file says which. That matters more here than an ordinary stale
    build would: the client installs this payload into the game folder on every
    run, so a stale one silently replaces a freshly built one, and the game then
    reads as a patch that does not work rather than a package that is out of
    date. An absent artifact is not stale; the caller decides what to do about a
    missing one.

    Compares timestamps, not content, so it errs toward refusing: anything that
    bumps an mtime without changing what compiles, a checkout for instance,
    reads as stale. That is the safe direction for a binary and the wrong one for
    a generated script, which is why only the ASI is checked this way.
    """
    if not artifact.is_file():
        return []
    built = artifact.stat().st_mtime
    newer = [(path.stat().st_mtime, path)
             for glob in globs
             for path in root.glob(glob)
             if path.is_file()]
    newer = [entry for entry in newer if entry[0] > built]
    newer.sort(reverse=True, key=lambda entry: entry[0])
    return [path.relative_to(root).as_posix() for _, path in newer]


# The game reads the compiled script's MAIN section into a buffer of this size,
# fixed in the executable. A larger MAIN is not rejected by anything: Sanny
# compiles it, the pipeline reports success, and the tail of the script, which is
# where the audio threads sit, is simply not there in game.
MAIN_SECTION_BUFFER = 225512

# The three-byte goto the script header opens each jump with.
GOTO_PREFIX = bytes((0x02, 0x00, 0x01))


def compiled_main_size(scm: pathlib.Path) -> int | None:
    """The MAIN section size the compiled script records, or None if unreadable.

    The header opens with three gotos; the second target is the mission segment,
    which stores the MAIN size as a dword after its own goto and a pad byte.
    """
    data = scm.read_bytes()
    offset, targets = 0, []
    try:
        for _ in range(3):
            if data[offset:offset + 3] != GOTO_PREFIX:
                return None
            targets.append(struct.unpack_from("<I", data, offset + 3)[0])
            offset = targets[-1]
        return struct.unpack_from("<I", data, targets[1] + 8)[0]
    except (IndexError, struct.error):
        return None


def _refuse_oversized_main() -> None:
    """Stops a compiled script the game would silently truncate.

    Measured rather than trusted: a build that went 3471 bytes over shipped
    through every other gate in this repo, because compiling it succeeds and
    nothing downstream reads the size.
    """
    if not MOD_SCM.is_file():
        return
    size = compiled_main_size(MOD_SCM)
    if size is None:
        raise SystemExit(
            f"Refusing to package: {MOD_SCM.name} does not read as a compiled "
            "script, so its MAIN section cannot be measured.")
    if size > MAIN_SECTION_BUFFER:
        raise SystemExit(
            f"Refusing to package: the compiled MAIN section is {size} bytes "
            f"against the game's {MAIN_SECTION_BUFFER} byte buffer, over by "
            f"{size - MAIN_SECTION_BUFFER}. The game loads what fits and drops "
            "the rest, so the tail of the script would not be there. Make room "
            "in MAIN before shipping this.")


def _refuse_unshippable_payload() -> None:
    """Stops the build before it writes anything when the payload cannot ship.

    Runs before the archive is opened, because raising inside it would still
    close a well formed apworld carrying the world and the manifest and no mod at
    all. The installer reads an empty payload as nothing to manage, so that
    archive would not merely be incomplete, it would stop replacing the stale ASI
    it was meant to fix.

    main.scm and the CLEO scripts ship through the same payload and are NOT
    gated: they are generated, and their generators are routinely edited without
    changing what those generators emit, so a timestamp here refuses correct
    output. Confirmed on 2026-08-24, when main.scm was older than its generators
    and its content was current.
    """
    # An INCOMPLETE payload is refused here too, not merely reported. Shipping
    # neither file is a real state, a checkout with no build in it, and the
    # installer no-ops on it. Shipping one without the other is a failed build,
    # and packaging it replaces a working apworld with one whose payload the
    # client reads as nothing to manage, so the mod silently stops being
    # installed. Measured, not theorised: a rebuild that failed mid-session
    # produced exactly that archive.
    if MOD_ASI.is_file() != MOD_SCM.is_file():
        missing = "the compiled ASI" if not MOD_ASI.is_file() else "mod/scm/main.scm"
        raise SystemExit(
            f"Refusing to package: {missing} is missing, so the payload would be "
            "incomplete. Build it, or remove both to ship an apworld with no "
            "payload on purpose.")
    stale = stale_sources(MOD_ASI, REPOSITORY_ROOT, ASI_SOURCE_GLOBS)
    if not stale:
        return
    shown = ", ".join(stale[:5])
    more = f" and {len(stale) - 5} more" if len(stale) > 5 else ""
    raise SystemExit(
        f"Refusing to package: the compiled ASI is older than {len(stale)} of "
        f"its own sources, newest first: {shown}{more}. Rebuild it first, "
        "because the client installs this payload over the game folder on every "
        "run, so shipping the older one puts it back. Build the plugin project "
        "with MSBuild, target Rebuild, configuration 'Release GTA-VC', platform "
        "Win32.")


def _stage_mod_payload(bundle: zipfile.ZipFile) -> None:
    # The mod needs both the compiled ASI (the AP communication layer) and the
    # compiled main.scm (mission gating) to be playable. Only two states reach
    # here: neither present, which ships an apworld with no payload for the
    # installer to no-op on, and both present, which stages them. The caller
    # refuses the half-built state before anything is written, so this function
    # would raise part way through an archive if it were ever called without it.
    if not MOD_ASI.is_file() and not MOD_SCM.is_file():
        print("Mod payload not staged (no compiled ASI or main.scm); the apworld "
              "ships without the auto-installer.")
        return
    cleo_scripts = sorted(MOD_CLEO_DIR.glob("*.cs")) if MOD_CLEO_DIR.is_dir() else []
    staged = [MOD_ASI.name] + [f"cleo/{script.name}" for script in cleo_scripts] + ["main.scm"]
    # Every staged file must be on the installer's removal manifest (main.scm is
    # restored from its backup instead), so /uninstall keeps removing every file
    # any payload has ever shipped.
    unlisted = _installer_module().unlisted_payload_paths(staged)
    if unlisted:
        raise SystemExit(
            f"Staged payload files not in installer.SHIPPED_PAYLOAD_PATHS: "
            f"{', '.join(unlisted)}. Append them (never remove entries) so "
            "/uninstall cleans every install.")
    base = pathlib.PurePosixPath(WORLD_NAME) / "data" / "mod"
    bundle.write(MOD_ASI, str(base / MOD_ASI.name))
    bundle.write(MOD_SCM, str(base / "main.scm"))
    for script in cleo_scripts:
        bundle.write(script, str(base / "cleo" / script.name))
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

    # Before the archive is opened, so a refusal leaves the previous apworld in
    # place rather than replacing it with one that has no mod in it.
    _refuse_unshippable_payload()
    _refuse_oversized_main()

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
