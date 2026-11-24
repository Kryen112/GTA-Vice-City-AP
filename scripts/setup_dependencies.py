"""Install shared game runtimes without replacing existing installations."""

import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path

from gta_vc_setup.installer import InstallRefused

LOADER_URL = (
    "https://github.com/ThirteenAG/Ultimate-ASI-Loader/releases/download/v9.7.4/Ultimate-ASI-Loader-NoPDB.zip"
)
LOADER_SHA256 = "14b3a1ad018899571ac9aa01482977f3c6d49e6cba99f552d01c5acacd1315e1"
LOADER_LICENSE_URL = "https://raw.githubusercontent.com/ThirteenAG/Ultimate-ASI-Loader/v9.7.4/license"
CLEO_URL = "https://github.com/cleolibrary/III.VC.CLEO/releases/download/2.1.1/CLEO.VC_v2.1.1.zip"
CLEO_SHA256 = "3a7de13dbf0c83ec7e83011eec9157c7d5b43b828a26f12991ea0da367b3c3ab"


def download(url: str, sha256: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(16 * 1024 * 1024 + 1)
    except OSError as error:
        raise InstallRefused("Could not download the required game runtime. "
                             "Check your internet connection and run setup again.") from error
    if hashlib.sha256(data).hexdigest() != sha256:
        raise InstallRefused("The game runtime download failed its integrity check. "
                             "Run setup again.")
    return data


def runtime_archive(name: str, sha256: str) -> zipfile.ZipFile:
    try:
        data = (Path(__file__).parent / "runtimes" / name).read_bytes()
    except OSError as error:
        raise InstallRefused("The installer is missing a bundled game runtime. Download setup again.") from error
    if hashlib.sha256(data).hexdigest() != sha256:
        raise InstallRefused("A bundled game runtime failed its integrity check. Download setup again.")
    return zipfile.ZipFile(io.BytesIO(data))


def install(install_dir: Path) -> None:
    bundled = Path(__file__).parent
    files = []
    if not (install_dir / "dinput8.dll").exists():
        with runtime_archive("asi-loader.zip", LOADER_SHA256) as archive:
            files.append(("dinput8.dll", archive.read("dinput8.dll")))
    if not any((install_dir / folder / name).exists()
               for folder in ("", "scripts") for name in ("VC.CLEO.asi", "CLEO.asi")):
        with runtime_archive("cleo.zip", CLEO_SHA256) as archive:
            files.extend((name, archive.read(source)) for name, source in (
                ("VC.CLEO.asi", "VC.CLEO.asi"),
                ("GtaVcAp-Licenses/CLEO-2.1.1.txt", "CLEO_Readme/Readme.txt")))
    files.extend((f"GtaVcAp-Licenses/{source.name}", source.read_bytes())
                 for source in (bundled / "licenses").iterdir())
    for name, data in files:
        destination = install_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("xb") as output:
                output.write(data)
        except FileExistsError:
            pass
