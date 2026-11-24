"""Standalone setup installs offline, preserves runtimes and rejects corrupt archives."""

import hashlib
import importlib
import io
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def standalone(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    package = tmp_path / "gta_vc_setup"
    package.mkdir()
    (package / "__init__.py").touch()
    for name in ("setup.py", "installer.py"):
        shutil.copyfile(root / "scripts/gta_vc_setup" / name, package / name)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.syspath_prepend(str(root / "scripts"))
    dependencies = importlib.import_module("setup_dependencies")
    setup = importlib.import_module("gta_vc_setup.setup")
    monkeypatch.setattr(dependencies, "__file__", str(tmp_path / "setup_dependencies.py"))
    (tmp_path / "licenses").mkdir()
    (tmp_path / "licenses/loader.txt").write_text("license")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("dinput8.dll", b"downloaded loader")
        output.writestr("VC.CLEO.asi", b"cleo")
        output.writestr("CLEO_Readme/Readme.txt", b"credits")
    runtimes = tmp_path / "runtimes"
    runtimes.mkdir()
    for name in ("asi-loader.zip", "cleo.zip"):
        (runtimes / name).write_bytes(archive.getvalue())
    digest = hashlib.sha256(archive.getvalue()).hexdigest()
    monkeypatch.setattr(dependencies, "LOADER_SHA256", digest)
    monkeypatch.setattr(dependencies, "CLEO_SHA256", digest)
    yield dependencies, setup, archive.getvalue()
    for name in list(sys.modules):
        if name == "setup_dependencies" or name.startswith("gta_vc_setup"):
            del sys.modules[name]


def test_install_keeps_existing_files_and_reuses_cleo(standalone, tmp_path):
    dependencies, _, _ = standalone
    game = tmp_path / "game"
    game.mkdir()
    (game / "dinput8.dll").write_bytes(b"existing loader")
    with mock.patch.object(dependencies.urllib.request, "urlopen",
                           side_effect=OSError("Network unavailable")) as request:
        dependencies.install(game)
        assert (game / "dinput8.dll").read_bytes() == b"existing loader"
        assert (game / "VC.CLEO.asi").read_bytes() == b"cleo"
        assert (game / "GtaVcAp-Licenses/CLEO-2.1.1.txt").read_bytes() == b"credits"
        dependencies.install(game)
        request.assert_not_called()
    (game / "VC.CLEO.asi").rename(game / "CLEO.asi")
    (game / "dinput8.dll").unlink()
    with mock.patch.object(dependencies.urllib.request, "urlopen",
                           side_effect=OSError("Network unavailable")) as request:
        dependencies.install(game)
        dependencies.install(game)
        request.assert_not_called()
        assert not (game / "VC.CLEO.asi").exists()
        assert (game / "dinput8.dll").read_bytes() == b"downloaded loader"


@pytest.mark.parametrize("corrupt", [False, True])
def test_fresh_install_uses_verified_bundled_runtime_archives_offline(standalone, tmp_path, corrupt):
    dependencies, _, _ = standalone
    game = tmp_path / "Instalación de Vice City"
    game.mkdir()
    if corrupt:
        (tmp_path / "runtimes/cleo.zip").write_bytes(b"corrupt archive")
    with mock.patch.object(dependencies.urllib.request, "urlopen",
                           side_effect=OSError("Network unavailable")) as request:
        if corrupt:
            with pytest.raises(dependencies.InstallRefused, match="integrity"):
                dependencies.install(game)
            assert not list(game.iterdir())
        else:
            dependencies.install(game)
            assert (game / "dinput8.dll").read_bytes() == b"downloaded loader"
            assert (game / "VC.CLEO.asi").read_bytes() == b"cleo"
        request.assert_not_called()


def test_missing_bundled_runtime_does_not_install_partial_files(standalone, tmp_path):
    dependencies, _, _ = standalone
    game = tmp_path / "game"
    game.mkdir()
    (tmp_path / "runtimes/cleo.zip").unlink()
    with pytest.raises(dependencies.InstallRefused, match="missing a bundled game runtime"):
        dependencies.install(game)
    assert not list(game.iterdir())


def test_build_download_rejects_corrupt_runtime_archive(standalone):
    dependencies, _, _ = standalone
    with mock.patch.object(dependencies.urllib.request, "urlopen") as request:
        request.return_value.__enter__.return_value.read.return_value = b"corrupt archive"
        with pytest.raises(dependencies.InstallRefused, match="integrity"):
            dependencies.download(dependencies.LOADER_URL, dependencies.LOADER_SHA256)


def test_shared_setup_validates_game_before_dependencies(standalone, tmp_path):
    _, setup, _ = standalone
    game = tmp_path / "game"
    game.mkdir()
    (game / "gta-vc.exe").touch()
    before = mock.Mock()
    with (mock.patch.object(setup.installer, "game_process_running", return_value=False),
          mock.patch.object(setup.installer, "require_supported_game_build"),
          mock.patch.object(setup.installer, "materialize_payload",
                            side_effect=setup.installer.StockScriptRefused("Wrong script")),
          mock.patch.object(setup.installer, "deploy") as deploy):
        messages = mock.Mock()
        setup.launch(str(game), open_directory=mock.Mock(), messagebox=messages,
                     before_install=before)
        before.assert_not_called()
        deploy.assert_not_called()
        messages.assert_called_once_with(setup.TITLE, "Wrong script", error=True)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process check")
@pytest.mark.parametrize("output, running", [(b"No tasks match: \xff", False),
                                            (b"GTA-VC.EXE \xff", True)])
def test_process_check_handles_localized_output(standalone, output, running):
    _, setup, _ = standalone
    run = subprocess.run

    def tasklist(arguments, **kwargs):
        if kwargs.get("text"):
            kwargs["encoding"] = "utf-8"
        return run([sys.executable, "-c",
                    f"import sys; sys.stdout.buffer.write({output!r})"], **kwargs)

    with mock.patch.object(setup.installer.subprocess, "run", side_effect=tasklist):
        assert setup.installer.game_process_running() is running


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Shell shortcut")
def test_connection_shortcut_and_optional_failure(standalone, tmp_path, monkeypatch):
    _, setup, _ = standalone
    game = tmp_path / "Vice City's game"
    game.mkdir()
    (game / "gta-vc.exe").touch()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user's data"))
    monkeypatch.setattr(setup.installer, "game_process_running", lambda: False)
    monkeypatch.setattr(setup.installer, "require_supported_game_build", lambda _: None)
    monkeypatch.setattr(setup.installer, "deploy", lambda _: [])
    setup.install(game)
    shortcut = game / "Archipelago Connection Settings.lnk"
    settings = tmp_path / "user's data/GtaVcAp/connection.ini"
    assert shortcut.is_file() and settings.is_file()
    monkeypatch.setenv("GTAVC_TEST_SHORTCUT", str(shortcut))
    result = subprocess.run([
        "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
        "(New-Object -ComObject WScript.Shell).CreateShortcut($env:GTAVC_TEST_SHORTCUT).TargetPath",
    ], check=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    assert Path(result.stdout.strip()) == settings
    saved = settings.read_bytes()
    subprocess.run([
        "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
        "$ErrorActionPreference = 'Stop'; "
        "$file = [System.IO.File]::GetAccessControl($env:GTAVC_TEST_SETTINGS); "
        "$file.SetAccessRuleProtection($true, $true); "
        "[System.IO.File]::SetAccessControl($env:GTAVC_TEST_SETTINGS, $file); "
        "$link = (New-Object -ComObject WScript.Shell).CreateShortcut($env:GTAVC_TEST_SHORTCUT); "
        "$link.TargetPath = 'C:\\missing-connection.ini'; $link.Save()",
    ], env={**setup.os.environ, "GTAVC_TEST_SETTINGS": str(settings)},
        check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    setup.install(game)
    result = subprocess.run([
        "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
        "$ErrorActionPreference = 'Stop'; "
        "[System.IO.File]::GetAccessControl($env:GTAVC_TEST_SETTINGS).AreAccessRulesProtected; "
        "(New-Object -ComObject WScript.Shell).CreateShortcut($env:GTAVC_TEST_SHORTCUT).TargetPath",
    ], env={**setup.os.environ, "GTAVC_TEST_SETTINGS": str(settings)},
        check=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    assert not result.stderr, result.stderr
    protected, target = result.stdout.strip().splitlines()
    assert protected == "False" and Path(target) == settings
    assert settings.read_bytes() == saved
    shortcut.unlink()
    setup.install(game)
    assert shortcut.is_file() and settings.read_bytes() == saved
    run = subprocess.run
    def fail_shortcut(command, **kwargs):
        if command[0] == "powershell.exe":
            raise OSError("No shortcut support")
        return run(command, **kwargs)
    with mock.patch.object(setup.subprocess, "run", side_effect=fail_shortcut):
        log = setup.install(game)
    assert any("Could not create the shortcut" in line for line in log)
    assert settings.read_bytes() == saved


def test_update_dialog_returns_with_a_hidden_root(standalone):
    import tkinter as tk
    _, setup, _ = standalone
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    root.withdraw()
    create_window = tk.Tk
    timed_out = []

    def timeout():
        timed_out.append(True)
        root.quit()

    def window():
        dialog = create_window()
        dialog.withdraw()
        def click_install():
            dialog.winfo_children()[0].winfo_children()[1].invoke()

        dialog.after(10, click_install)
        dialog.after(1000, timeout)
        return dialog

    try:
        with mock.patch.object(tk, "Tk", side_effect=window):
            assert setup.choose_action() == "install"
            assert not timed_out
    finally:
        root.destroy()
