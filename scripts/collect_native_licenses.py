"""Refresh notices from the dependencies installed by build_native_client.ps1."""

from pathlib import Path


def collect(root: Path) -> str:
    deps = root / ".build/apcpp-deps"
    versions = {}
    for block in (deps / "vcpkg/status").read_text().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if fields.get("Architecture") == "x86-windows-static" and "Version" in fields:
            versions[fields["Package"]] = fields["Version"]
    sections = [
        ("APCpp 172f683d4306b4fa209949419993198f87d881ed, with local changes",
         "N00byKing and contributors; modifications by randomcodegen, 2026-09-08.\n"
         "LGPL-2.1-only; changes documented in mod/asi/third_party/apcpp/README.md.\n\n"
         + (root / "mod/asi/third_party/apcpp/LICENSE").read_text()),
        ("nlohmann/json 3.11.3", (root / "LICENSE").read_text().replace(
            "Copyright (c) 2026 Kryen112\nCopyright (c) 2026 randomcodegen",
            "Copyright (c) 2013-2023 Niels Lohmann <https://nlohmann.me>")),
        ("plugin-sdk", (root.parent / "plugin-sdk/LICENSE").read_text()),
    ]
    for name in ("ixwebsocket", "jsoncpp", "mbedtls", "zlib"):
        text = (deps / f"x86-windows-static/share/{name}/copyright").read_text(encoding="utf-8")
        if name == "mbedtls":
            text = "This build selects the Apache-2.0 license option.\n\n" + text
        sections.append((f"{name} {versions[name]} (vcpkg x86-windows-static)", text))
    return ("THIRD PARTY LICENSES AND NOTICES\n\n"
            "Collected from the vendored sources and installed native build dependencies.\n"
            "Each component retains its terms. See NOTICE for distribution requirements.\n\n"
            + "\n".join(f"{'=' * 72}\n{name}\n{'=' * 72}\n\n{text}\n" for name, text in sections))


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    (root / "THIRD_PARTY_LICENSES").write_text(collect(root), encoding="utf-8", newline="\n")
