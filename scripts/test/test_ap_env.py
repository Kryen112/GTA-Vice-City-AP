"""Tests for how the tooling finds Archipelago and links this world into it.

Both halves exist because a checkout moves. The search walks ancestors rather
than checking one sibling, so this repository can sit some folders below the one
Archipelago is cloned into; the link removal clears what the old layout left
behind, since a junction outlives the path it points at and then blocks every
run with a name that already exists.

Nothing here touches the real checkout. Each test builds a tree under tmp_path
and points the module's repository root into it.
"""

import os
import pathlib
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ap_env  # noqa: E402


def _checkout(at: pathlib.Path) -> pathlib.Path:
    """An Archipelago checkout, which is what holding a worlds folder means."""
    (at / "worlds").mkdir(parents=True)
    return at


def _repository_at(monkeypatch, root: pathlib.Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ap_env, "REPOSITORY_ROOT", root.resolve())


def _link(target: pathlib.Path, destination: pathlib.Path) -> None:
    """Link the way link_world does, so the tests exercise the real entry kind."""
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(destination)],
                       capture_output=True, check=True)
    else:
        target.symlink_to(destination, target_is_directory=True)


def test_override_wins_over_any_search(tmp_path, monkeypatch) -> None:
    beside = _checkout(tmp_path / "beside" / "Archipelago")
    chosen = _checkout(tmp_path / "chosen")
    _repository_at(monkeypatch, tmp_path / "beside" / "world")
    monkeypatch.setenv("AP_ROOT", str(chosen))
    assert ap_env.archipelago_root() == chosen.resolve()
    assert beside.exists()


def test_override_that_is_not_a_checkout_finds_nothing(tmp_path, monkeypatch) -> None:
    """A typo in the override fails here rather than running against a neighbour."""
    _checkout(tmp_path / "Archipelago")
    _repository_at(monkeypatch, tmp_path / "world")
    monkeypatch.setenv("AP_ROOT", str(tmp_path / "Archipelagoo"))
    assert ap_env.archipelago_root() is None


def test_sibling_checkout_is_found(tmp_path, monkeypatch) -> None:
    root = _checkout(tmp_path / "Archipelago")
    _repository_at(monkeypatch, tmp_path / "world")
    monkeypatch.delenv("AP_ROOT", raising=False)
    assert ap_env.archipelago_root() == root.resolve()


def test_checkout_above_a_nested_repository_is_found(tmp_path, monkeypatch) -> None:
    """The layout this search exists for: the repository moved a folder down."""
    root = _checkout(tmp_path / "Archipelago")
    _repository_at(monkeypatch, tmp_path / "game" / "game")
    monkeypatch.delenv("AP_ROOT", raising=False)
    assert ap_env.archipelago_root() == root.resolve()


def test_the_nearest_checkout_wins(tmp_path, monkeypatch) -> None:
    _checkout(tmp_path / "Archipelago")
    nearer = _checkout(tmp_path / "game" / "Archipelago")
    _repository_at(monkeypatch, tmp_path / "game" / "world")
    monkeypatch.delenv("AP_ROOT", raising=False)
    assert ap_env.archipelago_root() == nearer.resolve()


def test_a_folder_named_archipelago_is_not_a_checkout(tmp_path, monkeypatch) -> None:
    (tmp_path / "Archipelago").mkdir()
    _repository_at(monkeypatch, tmp_path / "world")
    monkeypatch.delenv("AP_ROOT", raising=False)
    assert ap_env.archipelago_root() is None


def test_a_dangling_link_is_removed(tmp_path) -> None:
    destination = tmp_path / "gone"
    destination.mkdir()
    target = tmp_path / "link"
    _link(target, destination)
    destination.rmdir()
    assert ap_env._remove_dangling_link(target) is True
    assert not os.path.lexists(target)


def test_a_live_link_is_left_alone(tmp_path) -> None:
    """A link to a path that still exists is the caller's to refuse, not ours."""
    destination = tmp_path / "here"
    destination.mkdir()
    target = tmp_path / "link"
    _link(target, destination)
    assert ap_env._remove_dangling_link(target) is False
    assert os.path.lexists(target)


def test_an_absent_target_removes_nothing(tmp_path) -> None:
    assert ap_env._remove_dangling_link(tmp_path / "nothing") is False


def test_a_real_directory_is_left_alone(tmp_path) -> None:
    """Never mistake a directory for a link and delete what is inside it."""
    target = tmp_path / "worlds"
    target.mkdir()
    (target / "kept.py").write_text("", encoding="utf-8")
    assert ap_env._remove_dangling_link(target) is False
    assert (target / "kept.py").is_file()
