"""Builds gta_vice_city.apworld with Archipelago's own packaging and installs it.

Links the world into the Archipelago checkout's worlds folder so the core can
discover it, stages the mod payload inside the world package, hands the
packaging itself to Archipelago's "Build APWorlds" launcher component, copies
what the component wrote to dist, and copies that into the frozen install's
custom_worlds folder.

    python scripts/build_apworld.py [output_dir]

The component is the packaging path the apworld format documents, so nothing
here decides what a well formed apworld looks like. It merges the world's own
archipelago.json with the container version fields the format requires, and it
reads its exclusions from Archipelago's GLOBAL.apignore plus the world's
.apignore. What this build produces is what the core's own release build
produces, which is what every Archipelago an outside player runs will accept.

The install target defaults to %ProgramData%/Archipelago/custom_worlds and is
overridable with the AP_CUSTOM_WORLDS environment variable.

The payload it stages carries no copy of the game's script, only the differences
from it: main.scm and every CLEO script go in as bsdiff4 deltas against the
player's own stock main.scm, and only the ASI ships whole. The stock script this build reads defaults to
mod/scm/stock.scm and is overridable with the GTA_VC_STOCK_SCM environment
variable; it is never committed and never packaged.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys

import bsdiff4
from ap_env import WORLD_NAME, WORLD_SOURCE, archipelago_root, link_world

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent

# The world's own manifest, the half of the packaged one the component carries
# over untouched. It holds the world version and the core version floor.
WORLD_MANIFEST = WORLD_SOURCE / "archipelago.json"

# Fields the packaged apworld cannot do without. game names the world to build,
# world_version orders two installed copies of it, and minimum_ap_version keeps
# a core too old to run this world from loading it at all.
REQUIRED_MANIFEST_FIELDS = ("game", "world_version", "minimum_ap_version")

# The mod payload the client's installer deploys, staged into the world package
# under data/mod. Only our own files: the player supplies the ASI loader and
# CLEO. The compiled main.scm gates staging, since without it the mod is not
# playable.
MOD_ASI = REPOSITORY_ROOT / "mod" / "asi" / "plugin" / "bin" / "GTA-VC" / "Release" / "GtaVcAp.VC.asi"
MOD_CLEO_DIR = REPOSITORY_ROOT / "mod" / "cleo"
MOD_SCM = REPOSITORY_ROOT / "mod" / "scm" / "main.scm"

# The stock main.scm every derived payload file is a delta against. It is the
# game's own file, so it is never committed and never packaged: the build reads
# it to compute differences, and the differences are all that ship. The override
# takes the same shape as AP_CUSTOM_WORLDS below, which keeps the machine path
# out of the repository.
STOCK_SCM = REPOSITORY_ROOT / "mod" / "scm" / "stock.scm"
STOCK_SCM_VARIABLE = "GTA_VC_STOCK_SCM"

# The one script the deltas may be taken against. A delta is only applicable to
# the file it was computed from, so a build against anything else would produce a
# payload that installs on the machine that built it and nowhere else, and the
# installer would refuse it on every player's game. Pinning the source here is
# what makes that a build failure instead.
STOCK_SCM_SHA256 = "0fb3fd45b6a6dc21870cb48d9abe983510284b2b09b0c3d0eeac51d5dff338c7"

# Where the payload is staged for the component to pick up. It is written for
# the length of one build and cleared again, so the only copy that outlives a
# build is the one inside the apworld. A copy left in the source tree would be a
# second payload with no freshness gate on it: the installer prefers a local
# data/mod over the packaged one, so a client run from the checkout would deploy
# whatever an older build happened to leave there.
#
# The build owns data/mod and not data, which is where an apworld conventionally
# keeps shipped assets. Clearing destroys only what the build wrote, so a data
# file this world starts committing later survives it.
STAGED_PAYLOAD = WORLD_SOURCE / "data" / "mod"

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

# Runs the launcher component in a process of its own. Loading it here would
# pull every world in the checkout into this one, and the component signs off by
# opening a file browser on its output folder, which a build run from a hook or
# from CI has no use for.
PACKAGE_PROGRAM = """
import sys

import Launcher
from worlds.LauncherComponents import components

Launcher.open_folder = lambda folder: None
component = next((entry for entry in components
                  if entry.display_name == "Build APWorlds"), None)
if component is None:
    sys.exit("Archipelago's Build APWorlds component is not registered. It "
             "lives in a source checkout, not in a frozen install.")
Launcher.run_component(component, sys.argv[1])
"""


def _installer_module():
    # Loads installer.py on its own, without importing the world package, which
    # would need the Archipelago core on the path.
    spec = importlib.util.spec_from_file_location(
        "gta_vice_city_installer", WORLD_SOURCE / "installer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest_game() -> str:
    """The game the component is asked to package, from the world's manifest.

    Refuses a manifest missing any required field rather than packaging around
    it. The component happily writes an apworld when there is no manifest to
    carry over, and that apworld loses its version floor silently: it installs
    into a core too old to run it and fails somewhere else entirely.
    """
    if not WORLD_MANIFEST.is_file():
        raise SystemExit(
            f"Refusing to package: no {WORLD_MANIFEST.name} in the world "
            "package. It carries the game name, the world version, and the "
            "core version floor into the apworld.")
    try:
        manifest = json.loads(WORLD_MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Refusing to package: {WORLD_MANIFEST.name} does not "
                         f"read as json ({error}).") from error
    missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest]
    if missing:
        raise SystemExit(
            f"Refusing to package: {WORLD_MANIFEST.name} names no "
            f"{', '.join(missing)}.")
    return manifest["game"]


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
    """Stops the build before it stages anything when the payload cannot ship.

    Runs before the world package is touched, because refusing later would still
    leave a well formed apworld carrying the world and the manifest and no mod at
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


def stock_script_path() -> pathlib.Path:
    """Where this machine keeps the stock main.scm."""
    override = os.environ.get(STOCK_SCM_VARIABLE)
    return pathlib.Path(override) if override else STOCK_SCM


def stock_script_bytes() -> bytes:
    """The stock main.scm, refusing anything that is not the 1.0 script."""
    path = stock_script_path()
    if not path.is_file():
        raise SystemExit(
            f"Refusing to package: no stock main.scm at {path}. Every payload "
            "file the game loads as script ships as a delta against it, so the "
            "build cannot produce one without it. Copy an original 1.0 "
            f"data/main.scm there, or point {STOCK_SCM_VARIABLE} at one. It is "
            "the game's own file: never commit it.")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != STOCK_SCM_SHA256:
        raise SystemExit(
            f"Refusing to package: {path} hashes {digest}, not the known good "
            f"1.0 script's {STOCK_SCM_SHA256}. A delta against another file "
            "installs nowhere, since the installer patches the player's own 1.0 "
            "script.")
    return data


def _refuse_unpatchable_payload() -> None:
    """Stops the build when the payload cannot ship as deltas.

    Two ways it cannot, and both leave a game folder worse than not installing at
    all. The stock script is missing or is not the 1.0 one, so nothing here knows
    what a player's file looks like. Or the installer in this checkout does not
    reconstruct a delta payload, in which case the client would copy files named
    for a patch format into the game folder and the game would run on no script
    of ours at all. The build packages the installer that sits beside it, so this
    is where the two halves of the payload format are held together.
    """
    if not MOD_SCM.is_file():
        return
    stock_script_bytes()
    installer = _installer_module()
    missing = [name for name in ("DELTA_SUFFIX", "PAYLOAD_MANIFEST_NAME",
                                 "materialize_payload")
               if not hasattr(installer, name)]
    if missing:
        raise SystemExit(
            f"Refusing to package: installer.py names no {', '.join(missing)}, "
            "so it does not know the delta payload this build writes. The two "
            "have to move together.")


def _derived_payload(cleo_scripts: list[pathlib.Path]) -> list[tuple[str, pathlib.Path]]:
    """The payload files that ship as deltas, as (destination, source) pairs.

    Every file the game's script layer loads, which is main.scm and all of CLEO,
    and nothing about whose code each one holds. The six relocated shop threads
    are the game's own and our watchers are not, and no measurement of the bytes
    tells them apart: the shop threads delta to 0.15 of their size and our
    appickup.cs to 0.18. So the rule is the layer, applied to all of it.
    """
    return ([(f"cleo/{script.name}", script) for script in cleo_scripts]
            + [(MOD_SCM.name, MOD_SCM)])


def _write_delta(stock: bytes, source: pathlib.Path, destination: pathlib.Path) -> str:
    """Writes one delta and hands back the sha256 of what it reconstructs.

    The round trip is the gate: the delta that will ship is applied to the stock
    bytes here and has to reproduce the file exactly. That catches a stock script
    that passes its hash but was read wrong, and a pair bsdiff cannot represent,
    at build time rather than in a game folder.
    """
    target = source.read_bytes()
    delta = bsdiff4.diff(stock, target)
    if bsdiff4.patch(stock, delta) != target:
        raise SystemExit(
            f"Refusing to package: the delta for {source.name} does not "
            "reconstruct it from the stock script.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(delta)
    return hashlib.sha256(target).hexdigest()


def clear_staged_payload() -> None:
    """Removes the staged payload from the world package.

    Runs before staging as well as after packaging, so a payload an interrupted
    build left behind is never the one that ships. The data directory the
    staging created goes with it when the build is the only thing in there, and
    stays when it is not.
    """
    if STAGED_PAYLOAD.is_dir():
        shutil.rmtree(STAGED_PAYLOAD)
    container = STAGED_PAYLOAD.parent
    if container.is_dir() and not any(container.iterdir()):
        container.rmdir()


def stage_mod_payload() -> list[str]:
    """Stages the mod payload into the world package, and names its destinations.

    The mod needs both the compiled ASI (the AP communication layer) and the
    compiled main.scm (mission gating) to be playable. Only two states reach
    here: neither present, which ships an apworld with no payload for the
    installer to no-op on, and both present, which stages them. The caller
    refuses the half-built state before this runs.

    What is staged is not what is deployed. The ASI is copied, and every script
    the game loads becomes a delta beside the manifest that says what each one
    reconstructs. The names returned are still the destinations, since those are
    what the removal manifest and the installer are written in terms of.
    """
    clear_staged_payload()
    if not MOD_ASI.is_file() and not MOD_SCM.is_file():
        print("Mod payload not staged (no compiled ASI or main.scm); the apworld "
              "ships without the auto-installer.")
        return []
    installer = _installer_module()
    cleo_scripts = sorted(MOD_CLEO_DIR.glob("*.cs")) if MOD_CLEO_DIR.is_dir() else []
    derived = _derived_payload(cleo_scripts)
    staged = [MOD_ASI.name] + [destination for destination, _ in derived]
    # Every staged file must be on the installer's removal manifest (main.scm is
    # restored from its backup instead), so /uninstall keeps removing every file
    # any payload has ever shipped.
    unlisted = installer.unlisted_payload_paths(staged)
    if unlisted:
        raise SystemExit(
            f"Staged payload files not in installer.SHIPPED_PAYLOAD_PATHS: "
            f"{', '.join(unlisted)}. Append them (never remove entries) so "
            "/uninstall cleans every install.")
    stock = stock_script_bytes()
    STAGED_PAYLOAD.mkdir(parents=True)
    shutil.copyfile(MOD_ASI, STAGED_PAYLOAD / MOD_ASI.name)
    # Every destination, not only the patched ones: the installer asks the
    # manifest whether an install is current, so a file left out of it is a file
    # nobody notices going stale, and the ASI going stale is the whole reason
    # the freshness gate above exists.
    targets = {MOD_ASI.name: hashlib.sha256(MOD_ASI.read_bytes()).hexdigest()}
    for destination, source in derived:
        path = STAGED_PAYLOAD.joinpath(*destination.split("/"))
        targets[destination] = _write_delta(
            stock, source, path.with_name(path.name + installer.DELTA_SUFFIX))
    manifest = {"stock_main_scm_sha256": STOCK_SCM_SHA256, "targets": targets}
    (STAGED_PAYLOAD / installer.PAYLOAD_MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=4) + "\n", encoding="utf-8")
    print(f"Staged mod payload: {', '.join(staged)}. The script layer ships as "
          f"{len(derived)} deltas against the stock main.scm; only the ASI is "
          "copied whole.")
    return staged


def package(root: pathlib.Path, game: str) -> pathlib.Path | None:
    """Runs Archipelago's Build APWorlds component and returns what it wrote.

    The component reads and writes paths relative to the Archipelago root, so it
    runs from there. Its stdin is closed because loading the world registry
    reaches ModuleUpdate, which prompts when a dependency is missing, and a
    prompt nobody can answer is a hang rather than a failure. A world that fails
    to load that way is dropped by the registry, which is what a build of one
    other world wants.

    What the component wrote last time is removed first. A world the registry
    does not hold, because this one failed to import or the link is gone, is a
    line in the component's log and an exit code of zero, so the only thing that
    separates a build from a build that did nothing is whether the file is
    there afterwards. Without this the previous archive would be copied out and
    installed as though it were this run's.
    """
    built = root / "build" / "apworlds" / f"{WORLD_NAME}.apworld"
    built.unlink(missing_ok=True)
    completed = subprocess.run(
        [sys.executable, "-c", PACKAGE_PROGRAM, game],
        cwd=root, stdin=subprocess.DEVNULL, check=False)
    if completed.returncode != 0:
        print(f"Archipelago's Build APWorlds component exited {completed.returncode}.")
        return None
    if not built.is_file():
        print(f"The component wrote no {built}. It packages what the world "
              f"registry holds, so '{game}' either failed to import or is not "
              "linked into the checkout.")
        return None
    return built


def _install_directory() -> pathlib.Path | None:
    override = os.environ.get("AP_CUSTOM_WORLDS")
    if override:
        return pathlib.Path(override)
    program_data = os.environ.get("ProgramData")
    if program_data:
        return pathlib.Path(program_data) / "Archipelago" / "custom_worlds"
    return None


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

    # Before anything is staged, so a refusal leaves the previous apworld in
    # place rather than replacing it with one that has no mod in it.
    game = manifest_game()
    _refuse_unshippable_payload()
    _refuse_oversized_main()
    _refuse_unpatchable_payload()

    # Staging is inside the guard as well as packaging, so a copy that fails
    # part way through leaves no half payload behind. The installer prefers a
    # local data/mod to the packaged one, and half a payload is one the mod
    # cannot run on.
    try:
        stage_mod_payload()
        built = package(root, game)
    finally:
        clear_staged_payload()
    if built is None:
        return 1

    output_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else REPOSITORY_ROOT / "dist"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / built.name
    shutil.copyfile(built, archive)
    print(f"Wrote {archive} ({archive.stat().st_size} bytes).")
    _install(archive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
