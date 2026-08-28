"""Tests for how the tooling finds Archipelago and links this world into it.

Both halves exist because a checkout moves. The search walks ancestors rather
than checking one sibling, so this repository can sit some folders below the one
Archipelago is cloned into; the link removal clears what an old layout left
behind, since a junction outlives the path it points at and then blocks every
run with a name that already exists.

The search runs to the drive root, so a test asserting that nothing is found is
asserting about the real folders above tmp_path as well as the tree it built.
The marker is what keeps that honest: a candidate has to carry the world API
file, which no folder merely named Archipelago holds by accident. Every checkout
here is built through _checkout so it carries one.

The real checkout is never touched. Each test builds its tree under tmp_path and
points the module's repository root into it.
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
    """An Archipelago checkout, which is the marker file and not the folder name."""
    marker = at / ap_env.CHECKOUT_MARKER
    marker.parent.mkdir(parents=True)
    marker.write_text("", encoding="utf-8")
    return at


def _repository_at(monkeypatch, root: pathlib.Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ap_env, "REPOSITORY_ROOT", root.resolve())


def _world_source_at(monkeypatch, tmp_path: pathlib.Path) -> pathlib.Path:
    source = tmp_path / "repository" / "apworld" / ap_env.WORLD_NAME
    source.mkdir(parents=True)
    monkeypatch.setattr(ap_env, "WORLD_SOURCE", source)
    return source


def _link(target: pathlib.Path, destination: pathlib.Path) -> None:
    """Link the way link_world does, so the tests exercise the real entry kind."""
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(destination)],
                       capture_output=True, check=True)
    else:
        target.symlink_to(destination, target_is_directory=True)


def test_override_wins_over_any_search(tmp_path, monkeypatch) -> None:
    _checkout(tmp_path / "beside" / "Archipelago")
    chosen = _checkout(tmp_path / "chosen")
    _repository_at(monkeypatch, tmp_path / "beside" / "world")
    monkeypatch.setenv("AP_ROOT", str(chosen))
    assert ap_env.archipelago_root() == chosen.resolve()


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


def test_an_empty_override_still_searches(tmp_path, monkeypatch) -> None:
    """An AP_ROOT cleared to nothing is unset, not a refusal to look."""
    root = _checkout(tmp_path / "Archipelago")
    _repository_at(monkeypatch, tmp_path / "world")
    monkeypatch.setenv("AP_ROOT", "")
    assert ap_env.archipelago_root() == root.resolve()


def test_a_folder_named_archipelago_is_not_a_checkout(tmp_path, monkeypatch) -> None:
    """The name is not the test, and a bare worlds folder is not either."""
    (tmp_path / "Archipelago" / "worlds").mkdir(parents=True)
    _repository_at(monkeypatch, tmp_path / "world")
    monkeypatch.delenv("AP_ROOT", raising=False)
    assert ap_env.archipelago_root() is None


def test_a_rejected_override_is_named_in_the_message(tmp_path, monkeypatch) -> None:
    """Telling someone who set AP_ROOT to set AP_ROOT is the one useless answer."""
    folder = tmp_path / "not-a-checkout"
    folder.mkdir()
    monkeypatch.setenv("AP_ROOT", str(folder))
    message = ap_env.missing_checkout_message()
    assert str(folder) in message
    assert "AP_ROOT is set to" in message
    assert ap_env.CHECKOUT_MARKER.as_posix() in message


def test_an_override_pointing_nowhere_says_so(tmp_path, monkeypatch) -> None:
    """A mistyped path is the commonest failure; do not blame a missing file."""
    monkeypatch.setenv("AP_ROOT", str(tmp_path / "never-created"))
    message = ap_env.missing_checkout_message()
    assert "is not a folder" in message
    assert ap_env.CHECKOUT_MARKER.as_posix() not in message


def test_an_empty_override_counts_as_unset(monkeypatch) -> None:
    """A variable cleared to nothing is not a path anyone meant to point at."""
    monkeypatch.setenv("AP_ROOT", "")
    assert "No Archipelago checkout found" in ap_env.missing_checkout_message()


def test_an_empty_search_says_where_a_checkout_may_go(monkeypatch) -> None:
    monkeypatch.delenv("AP_ROOT", raising=False)
    message = ap_env.missing_checkout_message()
    assert "Set AP_ROOT" in message
    assert "ancestors" in message


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


def test_link_world_links_into_an_empty_checkout(tmp_path, monkeypatch) -> None:
    source = _world_source_at(monkeypatch, tmp_path)
    root = _checkout(tmp_path / "Archipelago")
    target = ap_env.link_world(root)
    assert target is not None
    assert target.resolve() == source.resolve()


def test_link_world_replaces_a_link_an_old_layout_left(tmp_path, monkeypatch) -> None:
    """The failure this change exists for: the name is taken by a link to nothing."""
    source = _world_source_at(monkeypatch, tmp_path)
    root = _checkout(tmp_path / "Archipelago")
    moved_away = tmp_path / "old"
    moved_away.mkdir()
    _link(root / "worlds" / ap_env.WORLD_NAME, moved_away)
    moved_away.rmdir()
    target = ap_env.link_world(root)
    assert target is not None
    assert target.resolve() == source.resolve()


def test_link_world_refuses_a_live_link_elsewhere(tmp_path, monkeypatch) -> None:
    """A link to a live path that is not this repository is refused, not deleted."""
    _world_source_at(monkeypatch, tmp_path)
    root = _checkout(tmp_path / "Archipelago")
    other = tmp_path / "another-worlds-copy"
    other.mkdir()
    link = root / "worlds" / ap_env.WORLD_NAME
    _link(link, other)
    assert ap_env.link_world(root) is None
    assert link.resolve() == other.resolve()


def test_link_world_accepts_a_link_already_pointing_here(tmp_path, monkeypatch) -> None:
    source = _world_source_at(monkeypatch, tmp_path)
    root = _checkout(tmp_path / "Archipelago")
    link = root / "worlds" / ap_env.WORLD_NAME
    _link(link, source)
    assert ap_env.link_world(root) == link
