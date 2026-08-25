"""Tests for the packaging script's freshness gate.

The gate stands between a stale compiled ASI and a player's game folder, since
the client installs the packaged payload over that folder on every run. It is
pure and parameterized on the root and the globs so it can be driven from a
temporary directory instead of the repository.
"""

import os
import pathlib
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
