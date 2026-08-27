"""Tests for the numbering snapshot writer's refusals.

The writer is the only thing that may change a frozen id table, so the ways it
declines to are the whole of it. Each of these is a way the freeze could be
taken off by accident and reported as success: a deleted snapshot rewritten from
whatever the tables now hold, a released flag that is a string and so is true, a
released snapshot missing a table and therefore checking nothing.

The world's own tables are never imported here. These drive the pure comparison
and the file-level guards with tables made up on the spot, which is what lets
the released path be exercised while the real snapshot is not released yet.
"""

import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import freeze_numbering  # noqa: E402

TABLES = {
    "item_id_base": 10,
    "location_id_base": 20,
    "items": {"Sprint": 10, "Jump": 11},
    "locations": {"An Old Friend": 20, "The Party": 21},
    "scm_globals": {"base:UNLOCK_BASE": 9010, "unlock:Rosenberg": 9010,
                    "completion:An Old Friend": 9036},
}


def _snapshot(released: bool = True, **changes) -> dict:
    snapshot = {"released": released, **{key: (dict(value) if isinstance(value, dict)
                                               else value)
                                         for key, value in TABLES.items()}}
    snapshot.update(changes)
    return snapshot


def test_matching_tables_have_moved_nothing() -> None:
    assert freeze_numbering.moved_entries(_snapshot(), TABLES) == []


def test_a_tail_append_has_moved_nothing() -> None:
    # The one change a released freeze allows. The writer does not police where
    # the new name landed; the test suite's freeze_violations does.
    grown = {**TABLES, "locations": {**TABLES["locations"], "A New Check": 22}}
    assert freeze_numbering.moved_entries(_snapshot(), grown) == []


def test_a_moved_id_is_reported() -> None:
    shifted = {**TABLES, "locations": {"An Old Friend": 20, "The Party": 22}}
    moved = freeze_numbering.moved_entries(_snapshot(), shifted)
    assert moved == ["locations: 'The Party' was 21, now 22"]


def test_a_missing_name_is_reported() -> None:
    shrunk = {**TABLES, "items": {"Sprint": 10}}
    assert freeze_numbering.moved_entries(_snapshot(), shrunk) == ["items: 'Jump' is gone, id 11"]


def test_a_moved_base_is_reported() -> None:
    rebased = {**TABLES, "item_id_base": 99}
    assert freeze_numbering.moved_entries(_snapshot(), rebased) == ["item_id_base was 10, now 99"]


def test_a_released_snapshot_missing_a_table_is_reported() -> None:
    # Not silence. Reading an absent table as nothing to check is how a released
    # freeze stops freezing while every run still says it wrote the snapshot.
    without = _snapshot()
    del without["items"]
    assert freeze_numbering.moved_entries(without, TABLES) == [
        "items: the released snapshot has no items at all"]


def _run(tmp_path: pathlib.Path, monkeypatch, argv: list[str],
         snapshot: dict | str | None) -> tuple[int, str, pathlib.Path]:
    """Runs the writer against a snapshot path of our own, with the world's
    tables stubbed, and hands back its exit code and what it printed."""
    path = tmp_path / "frozen_numbering.json"
    if snapshot is not None:
        path.write_text(snapshot if isinstance(snapshot, str)
                        else json.dumps(snapshot), encoding="utf-8")
    printed: list[str] = []
    monkeypatch.setattr(freeze_numbering, "SNAPSHOT", path)
    monkeypatch.setattr(freeze_numbering, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(freeze_numbering, "archipelago_root", lambda: tmp_path)
    monkeypatch.setattr(freeze_numbering, "link_world", lambda root: tmp_path)
    monkeypatch.setattr(freeze_numbering, "current_tables", lambda: dict(TABLES))
    monkeypatch.setattr(freeze_numbering, "print",
                        lambda *args: printed.append(" ".join(map(str, args))),
                        raising=False)
    monkeypatch.setattr(sys, "argv", ["freeze_numbering.py", *argv])
    return freeze_numbering.main(), "\n".join(printed), path


def test_a_deleted_snapshot_is_not_quietly_rewritten(tmp_path, monkeypatch) -> None:
    # The reset button this must not have: with the file gone, writing a fresh
    # one takes the freeze off whatever the tables now say and exits happy.
    code, printed, path = _run(tmp_path, monkeypatch, [], None)
    assert code == 1
    assert "deleted rather than never written" in printed
    assert not path.exists()


def test_the_first_run_writes_one(tmp_path, monkeypatch) -> None:
    code, printed, path = _run(tmp_path, monkeypatch, ["--first-run"], None)
    assert code == 0
    assert json.loads(path.read_text(encoding="utf-8"))["released"] is False
    assert "not yet released" in printed


def test_the_first_run_will_not_overwrite(tmp_path, monkeypatch) -> None:
    code, printed, _ = _run(tmp_path, monkeypatch, ["--first-run"], _snapshot(released=False))
    assert code == 1
    assert "already exists" in printed


def test_a_released_flag_that_is_not_a_flag_is_refused(tmp_path, monkeypatch) -> None:
    # 'false' is a true string, which would put the writer in the released phase
    # while reading as unreleased to anyone glancing at the file.
    code, printed, _ = _run(tmp_path, monkeypatch, [], _snapshot(released="false"))
    assert code == 1
    assert "neither true nor false" in printed


def test_a_released_id_that_moved_is_refused(tmp_path, monkeypatch) -> None:
    stale = _snapshot()
    stale["locations"]["The Party"] = 999
    code, printed, path = _run(tmp_path, monkeypatch, [], stale)
    assert code == 1
    assert "a released id never moves" in printed
    # And the file it refused to write is still the one it read.
    assert json.loads(path.read_text(encoding="utf-8"))["locations"]["The Party"] == 999


def test_a_released_snapshot_that_only_grew_is_rewritten(tmp_path, monkeypatch) -> None:
    smaller = _snapshot()
    del smaller["locations"]["The Party"]
    code, _, path = _run(tmp_path, monkeypatch, [], smaller)
    assert code == 0
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["released"] is True
    assert written["locations"] == TABLES["locations"]


def test_rewriting_keeps_the_phase(tmp_path, monkeypatch) -> None:
    # The flag is a hand edit made once. A rewrite must not hand it back.
    for released in (False, True):
        code, _, path = _run(tmp_path, monkeypatch, [], _snapshot(released=released))
        assert code == 0
        assert json.loads(path.read_text(encoding="utf-8"))["released"] is released
