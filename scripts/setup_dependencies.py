"""Install shared game runtimes without replacing existing installations."""

import hashlib
import io
import json
import re
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from gta_vc_setup.installer import InstallRefused

LOADER_URL = "https://github.com/ThirteenAG/Ultimate-ASI-Loader/releases/download/Win32-latest/dinput8-Win32.zip"
LOADER_RELEASE_URL = "https://api.github.com/repos/ThirteenAG/Ultimate-ASI-Loader/releases/tags/Win32-latest"
LOADER_LICENSE_URL = "https://raw.githubusercontent.com/ThirteenAG/Ultimate-ASI-Loader/Win32-latest/license"
CLEO_URL = "https://github.com/cleolibrary/III.VC.CLEO/releases/download/2.1.1/CLEO.VC_v2.1.1.zip"
CLEO_SHA256 = "3a7de13dbf0c83ec7e83011eec9157c7d5b43b828a26f12991ea0da367b3c3ab"


def download(url: str, sha256: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(16 * 1024 * 1024 + 1)
    except (OSError, urllib.error.URLError) as error:
        raise InstallRefused("Could not download the required game runtime. "
                             "Check your internet connection and run setup again.") from error
    if hashlib.sha256(data).hexdigest() != sha256:
        raise InstallRefused("The game runtime download failed its integrity check. "
                             "Run setup again.")
    return data


def download_loader() -> bytes:
    """Verify the rolling Win32 archive against GitHub's current asset digest."""
    request = urllib.request.Request(LOADER_RELEASE_URL, headers={"User-Agent": "GtaVcAp-Setup"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.loads(response.read(1024 * 1024))
        asset = next(asset for asset in release["assets"] if asset["browser_download_url"] == LOADER_URL)
        digest = asset["digest"]
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("Missing SHA-256")
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        raise InstallRefused("Could not verify the ASI Loader release. Check your internet connection "
                             "and run setup again.") from error
    return download(LOADER_URL, digest.removeprefix("sha256:"))


def install(install_dir: Path) -> None:
    bundled = Path(__file__).parent
    files = []
    if not (install_dir / "dinput8.dll").exists():
        with zipfile.ZipFile(io.BytesIO(download_loader())) as archive:
            files.append(("dinput8.dll", archive.read("dinput8.dll")))
    if not any((install_dir / folder / name).exists()
               for folder in ("", "scripts") for name in ("VC.CLEO.asi", "CLEO.asi")):
        with zipfile.ZipFile(io.BytesIO(download(CLEO_URL, CLEO_SHA256))) as archive:
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
