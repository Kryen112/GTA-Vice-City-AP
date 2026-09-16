"""Build dist/GTA-Vice-City-AP-Setup.exe on Windows using PyInstaller."""

import importlib.metadata
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import build_apworld as payload


def stage_setup(folder: Path) -> Path:
    package = folder / "gta_vc_setup"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    for name in ("setup.py", "installer.py"):
        shutil.copyfile(Path(__file__).parent / "gta_vc_setup" / name, package / name)
    original = payload.STAGED_PAYLOAD
    try:
        payload.STAGED_PAYLOAD = package / "data" / "mod"
        staged = payload.stage_mod_payload()
        missing = set(payload._installer_module().SHIPPED_PAYLOAD_PATHS) - set(staged)
        if missing or "main.scm" not in staged:
            raise SystemExit(f"Incomplete setup payload: {', '.join(sorted(missing)) or 'main.scm'}")
    finally:
        payload.STAGED_PAYLOAD = original
    return package


def main():
    if sys.platform != "win32":
        raise SystemExit("Build the Windows setup on Windows.")
    importlib.metadata.version("pyinstaller")
    payload._refuse_unshippable_payload()
    payload._refuse_oversized_main()
    payload._refuse_unpatchable_payload()
    root = payload.REPOSITORY_ROOT
    work = root / ".build" / "standalone-setup"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as temporary:
        folder = Path(temporary)
        package = stage_setup(folder)
        sys.path.insert(0, str(folder))
        import setup_dependencies
        licences = folder / "licenses"
        licences.mkdir()
        for name in payload.LICENCE_FILES:
            shutil.copyfile(root / name, licences / name)
        shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", licences / "Python.txt")
        shutil.copyfile(Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms",
                        licences / "Tcl-Tk.txt")
        for dependency in ("bsdiff4", "pyinstaller"):
            distribution = importlib.metadata.distribution(dependency)
            for file in distribution.files:
                if "license" in file.name.lower() or "copying" in file.name.lower():
                    shutil.copyfile(distribution.locate_file(file),
                                    licences / f"{dependency}-{file.name}")
        with urllib.request.urlopen(setup_dependencies.LOADER_LICENSE_URL, timeout=30) as response:
            (licences / "Ultimate-ASI-Loader.txt").write_bytes(response.read())
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--onefile", "--windowed", "--uac-admin", "--noupx",
            "--name", "GTA-Vice-City-AP-Setup", "--exclude-module", "Utils",
            "--paths", str(folder), "--distpath", str(root / "dist"),
            "--workpath", str(work / "pyinstaller"), "--specpath", str(folder),
            "--add-data", f"{package / 'data'}:gta_vc_setup/data",
            "--add-data", f"{licences}:licenses",
            str(root / "scripts" / "standalone_setup.py"),
        ], check=True)
    print(root / "dist" / "GTA-Vice-City-AP-Setup.exe")


if __name__ == "__main__":
    main()
