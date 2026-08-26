"""Tests for the packaging script's freshness gate.

The gate stands between a stale compiled ASI and a player's game folder, since
the client installs the packaged payload over that folder on every run. It is
pure and parameterized on the root and the globs so it can be driven from a
temporary directory instead of the repository.
"""

import json
import os
import pathlib
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_apworld  # noqa: E402
from build_apworld import stale_sources  # noqa: E402

GLOBS = ("src/**/*.cpp", "src/**/*.hpp", "plugin/project.vcxproj")


def _write(path: pathlib.Path, mtime: float) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_absent_artifact_is_not_stale(tmp_path: pathlib.Path) -> None:
    # A missing build is the caller's problem, not this function's: the presence
    # checks refuse it earlier, and reporting it as stale would say the wrong
    # thing about a payload that is simply not being shipped.
    _write(tmp_path / "src" / "a.cpp", 2000)
    assert stale_sources(tmp_path / "nothing.asi", tmp_path, GLOBS) == []


def test_a_newer_source_is_reported(tmp_path: pathlib.Path) -> None:
    artifact = _write(tmp_path / "out.asi", 1000)
    _write(tmp_path / "src" / "newer.cpp", 2000)
    _write(tmp_path / "src" / "older.cpp", 500)
    assert stale_sources(artifact, tmp_path, GLOBS) == ["src/newer.cpp"]


def test_sources_all_older_are_silent(tmp_path: pathlib.Path) -> None:
    artifact = _write(tmp_path / "out.asi", 3000)
    _write(tmp_path / "src" / "a.cpp", 1000)
    _write(tmp_path / "src" / "nested" / "b.hpp", 2000)
    _write(tmp_path / "plugin" / "project.vcxproj", 2999)
    assert stale_sources(artifact, tmp_path, GLOBS) == []


def test_equal_timestamps_are_not_stale(tmp_path: pathlib.Path) -> None:
    # The compiler stamps its output after reading its inputs, so equal is fresh.
    # Treating it as stale would refuse every build whose copy is fast enough.
    artifact = _write(tmp_path / "out.asi", 1500)
    _write(tmp_path / "src" / "a.cpp", 1500)
    assert stale_sources(artifact, tmp_path, GLOBS) == []


def test_report_is_newest_first(tmp_path: pathlib.Path) -> None:
    # The message shows only the first few, so the order decides what a reader
    # is told to look at.
    artifact = _write(tmp_path / "out.asi", 1000)
    _write(tmp_path / "src" / "middle.cpp", 2000)
    _write(tmp_path / "src" / "newest.cpp", 3000)
    _write(tmp_path / "src" / "nested" / "oldest.hpp", 1500)
    assert stale_sources(artifact, tmp_path, GLOBS) == [
        "src/newest.cpp", "src/middle.cpp", "src/nested/oldest.hpp"]


def test_a_glob_matching_nothing_is_harmless(tmp_path: pathlib.Path) -> None:
    artifact = _write(tmp_path / "out.asi", 1000)
    _write(tmp_path / "src" / "a.cpp", 2000)
    assert stale_sources(artifact, tmp_path, ("nowhere/**/*.c",)) == []
    assert stale_sources(artifact, tmp_path, GLOBS) == ["src/a.cpp"]


def test_one_file_missing_refuses(tmp_path: pathlib.Path, monkeypatch) -> None:
    # A failed build leaves one of the two behind. Packaging that replaces a
    # working apworld with one whose payload the client reads as nothing to
    # manage, so the mod silently stops being installed.
    asi = _write(tmp_path / "GtaVcAp.VC.asi", 1000)
    monkeypatch.setattr(build_apworld, "MOD_ASI", asi)
    monkeypatch.setattr(build_apworld, "MOD_SCM", tmp_path / "absent.scm")
    monkeypatch.setattr(build_apworld, "REPOSITORY_ROOT", tmp_path)
    try:
        build_apworld._refuse_unshippable_payload()
    except SystemExit as refusal:
        assert "main.scm" in str(refusal)
    else:
        raise AssertionError("a half-missing payload must refuse to package")


def test_the_other_file_missing_refuses(tmp_path: pathlib.Path, monkeypatch) -> None:
    scm = _write(tmp_path / "main.scm", 1000)
    monkeypatch.setattr(build_apworld, "MOD_ASI", tmp_path / "absent.asi")
    monkeypatch.setattr(build_apworld, "MOD_SCM", scm)
    monkeypatch.setattr(build_apworld, "REPOSITORY_ROOT", tmp_path)
    try:
        build_apworld._refuse_unshippable_payload()
    except SystemExit as refusal:
        assert "ASI" in str(refusal)
    else:
        raise AssertionError("a half-missing payload must refuse to package")


def test_both_absent_is_allowed(tmp_path: pathlib.Path, monkeypatch) -> None:
    # A checkout with no build in it is a real state: the apworld ships without
    # a payload and the installer no-ops, which is documented behaviour.
    monkeypatch.setattr(build_apworld, "MOD_ASI", tmp_path / "absent.asi")
    monkeypatch.setattr(build_apworld, "MOD_SCM", tmp_path / "absent.scm")
    monkeypatch.setattr(build_apworld, "REPOSITORY_ROOT", tmp_path)
    build_apworld._refuse_unshippable_payload()


def test_both_present_and_fresh_is_allowed(tmp_path: pathlib.Path, monkeypatch) -> None:
    asi = _write(tmp_path / "GtaVcAp.VC.asi", 3000)
    scm = _write(tmp_path / "main.scm", 3000)
    _write(tmp_path / "mod" / "asi" / "src" / "a.cpp", 1000)
    monkeypatch.setattr(build_apworld, "MOD_ASI", asi)
    monkeypatch.setattr(build_apworld, "MOD_SCM", scm)
    monkeypatch.setattr(build_apworld, "REPOSITORY_ROOT", tmp_path)
    build_apworld._refuse_unshippable_payload()


def test_a_stale_asi_refuses(tmp_path: pathlib.Path, monkeypatch) -> None:
    # The gate's own branch, which the other cases never reach: both files are
    # present and the ASI is older than a source.
    asi = _write(tmp_path / "GtaVcAp.VC.asi", 1000)
    scm = _write(tmp_path / "main.scm", 1000)
    _write(tmp_path / "src" / "later.cpp", 2000)
    monkeypatch.setattr(build_apworld, "MOD_ASI", asi)
    monkeypatch.setattr(build_apworld, "MOD_SCM", scm)
    monkeypatch.setattr(build_apworld, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(build_apworld, "ASI_SOURCE_GLOBS", ("src/**/*.cpp",))
    try:
        build_apworld._refuse_unshippable_payload()
    except SystemExit as refusal:
        assert "older than" in str(refusal)
        assert "src/later.cpp" in str(refusal)
    else:
        raise AssertionError("a stale ASI must refuse to package")


def test_the_globs_name_files_that_exist() -> None:
    # Without this the gate can go permanently silent and every other test here
    # still passes: a moved directory or a typo makes every glob match nothing,
    # which reads exactly like a fresh build.
    # The empty tuple is the same silence by another route, and this test would
    # be green for it too with only the loop below.
    assert build_apworld.ASI_SOURCE_GLOBS, "the gate reads no sources at all"
    for glob in build_apworld.ASI_SOURCE_GLOBS:
        matched = list(build_apworld.REPOSITORY_ROOT.glob(glob))
        # Files, which is what the gate consumes; a directory match would satisfy
        # a bare truth test while contributing nothing to it.
        assert any(path.is_file() for path in matched),             f"{glob} matches no file under the repository root"


def _fake_scm(path: pathlib.Path, main_size: int, largest: int = 32447) -> pathlib.Path:
    """A minimal compiled script: three gotos, then the mission segment."""
    import struct
    third = 200
    body = bytearray(b"\x00" * 400)
    # Each goto is 02 00 01 then a dword target.
    def goto(at: int, target: int) -> None:
        body[at:at + 3] = build_apworld.GOTO_PREFIX
        struct.pack_into("<I", body, at + 3, target)
    goto(0, 100)
    goto(100, 150)          # the mission segment
    goto(150, third)
    # The segment records MainSize at +8 and LargestMission at +12.
    struct.pack_into("<I", body, 150 + 8, main_size)
    struct.pack_into("<I", body, 150 + 12, largest)
    path.write_bytes(bytes(body))
    return path


def test_the_main_size_is_read_from_the_header(tmp_path: pathlib.Path) -> None:
    # The gate's whole value rests on reading the right dword: a neighbouring
    # one is a small number that never exceeds the buffer, so a wrong offset
    # leaves the gate green forever instead of failing loudly.
    scm = _fake_scm(tmp_path / "main.scm", 224884)
    assert build_apworld.compiled_main_size(scm) == 224884
    # And it is not reading LargestMission by mistake.
    other = _fake_scm(tmp_path / "other.scm", 210000, largest=32447)
    assert build_apworld.compiled_main_size(other) == 210000


def test_a_file_that_is_not_a_script_reads_as_none(tmp_path: pathlib.Path) -> None:
    garbage = tmp_path / "garbage.scm"
    garbage.write_bytes(b"not a compiled script at all")
    assert build_apworld.compiled_main_size(garbage) is None
    truncated = tmp_path / "short.scm"
    truncated.write_bytes(build_apworld.GOTO_PREFIX + b"\x90\x01\x00\x00")
    assert build_apworld.compiled_main_size(truncated) is None


def test_an_oversized_main_refuses(tmp_path: pathlib.Path, monkeypatch) -> None:
    scm = _fake_scm(tmp_path / "main.scm", build_apworld.MAIN_SECTION_BUFFER + 1)
    monkeypatch.setattr(build_apworld, "MOD_SCM", scm)
    try:
        build_apworld._refuse_oversized_main()
    except SystemExit as refusal:
        assert "over by 1" in str(refusal)
    else:
        raise AssertionError("a MAIN over the buffer must refuse to package")


def test_a_main_that_fits_is_allowed(tmp_path: pathlib.Path, monkeypatch) -> None:
    scm = _fake_scm(tmp_path / "main.scm", build_apworld.MAIN_SECTION_BUFFER)
    monkeypatch.setattr(build_apworld, "MOD_SCM", scm)
    build_apworld._refuse_oversized_main()


def test_an_unreadable_script_refuses(tmp_path: pathlib.Path, monkeypatch) -> None:
    # Refusing is the safe direction: every way to reach it ships a broken game.
    garbage = tmp_path / "main.scm"
    garbage.write_bytes(b"nope")
    monkeypatch.setattr(build_apworld, "MOD_SCM", garbage)
    try:
        build_apworld._refuse_oversized_main()
    except SystemExit as refusal:
        assert "does not read as a compiled script" in str(refusal)
    else:
        raise AssertionError("an unreadable script must refuse to package")


MANIFEST = {
    "game": "Grand Theft Auto Vice City",
    "world_version": "0.1.0",
    "minimum_ap_version": "0.6.7",
}


def _manifest(tmp_path: pathlib.Path, text: str) -> pathlib.Path:
    path = tmp_path / "archipelago.json"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_manifest_names_the_game_to_package(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setattr(build_apworld, "WORLD_MANIFEST", _manifest(tmp_path, json.dumps(MANIFEST)))
    assert build_apworld.manifest_game() == MANIFEST["game"]


def test_a_manifest_missing_a_field_refuses(tmp_path: pathlib.Path, monkeypatch) -> None:
    # Each field is load bearing on its own, so each absence is its own refusal:
    # the packaging component writes a perfectly valid apworld around a missing
    # one and the loss shows up only in a player's install.
    for field in build_apworld.REQUIRED_MANIFEST_FIELDS:
        short = {key: value for key, value in MANIFEST.items() if key != field}
        monkeypatch.setattr(build_apworld, "WORLD_MANIFEST", _manifest(tmp_path, json.dumps(short)))
        try:
            build_apworld.manifest_game()
        except SystemExit as refusal:
            assert field in str(refusal)
        else:
            raise AssertionError(f"a manifest with no {field} must refuse to package")


def test_an_absent_manifest_refuses(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setattr(build_apworld, "WORLD_MANIFEST", tmp_path / "archipelago.json")
    try:
        build_apworld.manifest_game()
    except SystemExit as refusal:
        assert "archipelago.json" in str(refusal)
    else:
        raise AssertionError("a world package with no manifest must refuse to package")


def test_a_manifest_that_is_not_json_refuses(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setattr(build_apworld, "WORLD_MANIFEST", _manifest(tmp_path, "{not json at all"))
    try:
        build_apworld.manifest_game()
    except SystemExit as refusal:
        assert "json" in str(refusal)
    else:
        raise AssertionError("an unreadable manifest must refuse to package")


def test_the_repository_manifest_is_the_one_that_ships() -> None:
    # The build reads the committed file, not the constant above, so this is
    # what keeps the two from drifting into each other.
    manifest = json.loads(build_apworld.WORLD_MANIFEST.read_text(encoding="utf-8"))
    for field in build_apworld.REQUIRED_MANIFEST_FIELDS:
        assert field in manifest, f"the world manifest names no {field}"


def _payload(tmp_path: pathlib.Path, monkeypatch, cleo_names: tuple = ("apwatchers.cs",)):
    """A staging setup on temporary paths: both artifacts, some CLEO, a stage."""
    asi = _write(tmp_path / "GtaVcAp.VC.asi", 1000)
    scm = _write(tmp_path / "main.scm", 1000)
    cleo_dir = tmp_path / "cleo"
    for name in cleo_names:
        _write(cleo_dir / name, 1000)
    staged = tmp_path / "world" / "data" / "mod"
    monkeypatch.setattr(build_apworld, "MOD_ASI", asi)
    monkeypatch.setattr(build_apworld, "MOD_SCM", scm)
    monkeypatch.setattr(build_apworld, "MOD_CLEO_DIR", cleo_dir)
    monkeypatch.setattr(build_apworld, "STAGED_PAYLOAD", staged)
    return staged


def test_staging_writes_the_payload_the_component_packages(tmp_path: pathlib.Path, monkeypatch) -> None:
    staged = _payload(tmp_path, monkeypatch)
    assert build_apworld.stage_mod_payload() == [
        "GtaVcAp.VC.asi", "cleo/apwatchers.cs", "main.scm"]
    assert (staged / "GtaVcAp.VC.asi").is_file()
    assert (staged / "main.scm").is_file()
    assert (staged / "cleo" / "apwatchers.cs").is_file()


def test_clearing_leaves_no_payload_in_the_world_package(tmp_path: pathlib.Path, monkeypatch) -> None:
    # The staged copy lives for one build. Left behind it is a second payload
    # with no freshness gate on it, and the installer prefers it to the packaged
    # one, so a client run from the checkout would deploy whatever is there.
    staged = _payload(tmp_path, monkeypatch)
    build_apworld.stage_mod_payload()
    build_apworld.clear_staged_payload()
    assert not staged.exists()


def test_staging_replaces_what_an_earlier_build_left(tmp_path: pathlib.Path, monkeypatch) -> None:
    # A script that stopped shipping still sits in the stage after an interrupted
    # build, and the component packages whatever it finds there.
    staged = _payload(tmp_path, monkeypatch)
    _write(staged / "cleo" / "apwatchers.cs", 1000)
    stale = _write(staged / "cleo" / "apshops.cs", 1000)
    build_apworld.stage_mod_payload()
    assert not stale.exists()
    assert (staged / "cleo" / "apwatchers.cs").is_file()


def test_no_artifacts_stages_nothing_and_clears_a_leftover(tmp_path: pathlib.Path, monkeypatch) -> None:
    # A checkout with no build in it ships an apworld with no payload, and the
    # one an earlier build staged must not be what goes out in its place.
    staged = _payload(tmp_path, monkeypatch)
    build_apworld.stage_mod_payload()
    monkeypatch.setattr(build_apworld, "MOD_ASI", tmp_path / "absent.asi")
    monkeypatch.setattr(build_apworld, "MOD_SCM", tmp_path / "absent.scm")
    assert build_apworld.stage_mod_payload() == []
    assert not staged.exists()


def test_staging_refuses_a_file_the_uninstaller_would_leave(tmp_path: pathlib.Path, monkeypatch) -> None:
    # The removal manifest is append only, and this is what enforces it: a new
    # CLEO script that nobody listed installs into a game folder that /uninstall
    # then cannot clean.
    staged = _payload(tmp_path, monkeypatch, cleo_names=("apwatchers.cs", "apunlisted.cs"))
    try:
        build_apworld.stage_mod_payload()
    except SystemExit as refusal:
        assert "cleo/apunlisted.cs" in str(refusal)
    else:
        raise AssertionError("a payload the uninstaller cannot clean must refuse to package")
    assert not staged.exists()


def _component(monkeypatch, returncode: int, writes: pathlib.Path | None = None) -> None:
    """Stands in for the packaging component, writing what it is told to."""
    def run(*args, **kwargs) -> subprocess.CompletedProcess:
        if writes is not None:
            _write(writes, 2000)
        return subprocess.CompletedProcess(args, returncode)
    monkeypatch.setattr(build_apworld.subprocess, "run", run)


def _built(root: pathlib.Path) -> pathlib.Path:
    return root / "build" / "apworlds" / f"{build_apworld.WORLD_NAME}.apworld"


def test_the_archive_the_component_wrote_is_what_ships(tmp_path: pathlib.Path, monkeypatch) -> None:
    built = _built(tmp_path)
    _component(monkeypatch, 0, writes=built)
    assert build_apworld.package(tmp_path, "Grand Theft Auto Vice City") == built


def test_a_component_that_packaged_nothing_ships_nothing(tmp_path: pathlib.Path, monkeypatch) -> None:
    # The component logs a world the registry does not hold and exits zero, so
    # the archive from the previous build is still sitting in its output folder.
    # Copying that one out would install a stale apworld as though it were this
    # run's, which is the whole reason the build clears the path first.
    stale = _write(_built(tmp_path), 1000)
    _component(monkeypatch, 0)
    assert build_apworld.package(tmp_path, "Grand Theft Auto Vice City") is None
    assert not stale.exists()


def test_a_component_failure_ships_nothing(tmp_path: pathlib.Path, monkeypatch) -> None:
    stale = _write(_built(tmp_path), 1000)
    _component(monkeypatch, 1)
    assert build_apworld.package(tmp_path, "Grand Theft Auto Vice City") is None
    assert not stale.exists()


def test_the_data_directory_goes_only_when_the_build_owns_it(tmp_path: pathlib.Path, monkeypatch) -> None:
    # data is where an apworld conventionally keeps shipped assets. The build
    # writes data/mod and takes only that back, so a data file this world starts
    # committing later is not deleted by every build that runs after it.
    staged = _payload(tmp_path, monkeypatch)
    build_apworld.stage_mod_payload()
    build_apworld.clear_staged_payload()
    assert not staged.parent.exists()

    build_apworld.stage_mod_payload()
    kept = _write(staged.parent / "shipped.json", 1000)
    build_apworld.clear_staged_payload()
    assert not staged.exists()
    assert kept.is_file()


def test_nothing_is_staged_until_every_gate_has_passed(tmp_path: pathlib.Path, monkeypatch) -> None:
    # The gates read the repository and the stage writes to it, so the order is
    # the property: a refusal has to leave the previous apworld and the previous
    # source tree exactly as they were. Each gate is tested on its own, and
    # nothing else pins them ahead of the staging.
    order: list[str] = []

    def records(name: str, result=None):
        def recorded(*args, **kwargs):
            order.append(name)
            return result
        return recorded

    monkeypatch.setattr(build_apworld, "archipelago_root", records("root", tmp_path))
    monkeypatch.setattr(build_apworld, "link_world", records("link", tmp_path))
    monkeypatch.setattr(build_apworld, "manifest_game", records("manifest", "Grand Theft Auto Vice City"))
    monkeypatch.setattr(build_apworld, "_refuse_unshippable_payload", records("payload"))
    monkeypatch.setattr(build_apworld, "_refuse_oversized_main", records("main"))
    monkeypatch.setattr(build_apworld, "stage_mod_payload", records("stage", []))
    monkeypatch.setattr(build_apworld, "clear_staged_payload", records("clear"))
    monkeypatch.setattr(build_apworld, "package", records("package", None))
    monkeypatch.setattr(sys, "argv", ["build_apworld.py"])

    assert build_apworld.main() == 1
    for gate in ("manifest", "payload", "main"):
        assert order.index(gate) < order.index("stage"), f"{gate} runs after the payload is staged"
    # And the stage is cleared whatever the packaging did, which is why it is
    # the last thing to happen on a run that packaged nothing.
    assert order[-1] == "clear"
