"""Packages the world into gta_vice_city.apworld.

An apworld is a zip whose single top-level entry is the world package
directory. Drop the result in a frozen Archipelago install's custom_worlds
folder to generate and host on that install (or upload it to archipelago.gg).
Test caches and compiled files are excluded. Usage:
    python scripts/build_apworld.py [output_dir]
"""

import pathlib
import sys
import zipfile

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORLD_NAME = "gta_vice_city"
WORLD_SOURCE = REPOSITORY_ROOT / "apworld" / WORLD_NAME

EXCLUDED_DIRECTORIES = {"__pycache__", "test", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def _included(path: pathlib.Path) -> bool:
    if any(part in EXCLUDED_DIRECTORIES for part in path.relative_to(WORLD_SOURCE).parts):
        return False
    return path.suffix not in EXCLUDED_SUFFIXES


def main() -> int:
    if not WORLD_SOURCE.is_dir():
        print(f"No world package at {WORLD_SOURCE}.")
        return 1
    output_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else REPOSITORY_ROOT / "dist"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{WORLD_NAME}.apworld"

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(WORLD_SOURCE.rglob("*")):
            if not path.is_file() or not _included(path):
                continue
            arcname = pathlib.PurePosixPath(WORLD_NAME) / path.relative_to(WORLD_SOURCE).as_posix()
            bundle.write(path, str(arcname))

    print(f"Wrote {archive} ({archive.stat().st_size} bytes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
