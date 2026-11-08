"""Put the release zip together, as Mad Dog's Public Beta packages are laid out, with nothing from the game in it.

usage: python tools/make_release.py <folder with the built files> [version]
  e.g. python tools/make_release.py build\\release "Beta 1"

The folder needs: MVP06.exe, d3dcompiler_ms.dll, msvcp140.dll, vcruntime140.dll, vcruntime140_1.dll (as in
Mad Dog's package), MVP06-Plus-Launcher.exe and gcbridge (from the "release tools" workflow's artifacts).
Writes MVP06-Plus-<version>.zip here, with a SHA256-MANIFEST.json of everything in it.
"""
import hashlib
import json
import os
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILT = ["MVP06.exe", "d3dcompiler_ms.dll", "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll",
         "MVP06-Plus-Launcher.exe", "gcbridge"]
FROM_REPO = ["README.md", "RELEASE-NOTES.md", "START-HERE.txt", "mvp06-settings.toml", "SDK-LICENSE.txt",
             "THIRD_PARTY.txt", "MICROSOFT-RUNTIME-NOTICE.txt", "assets/PUT-GAME-FILES-HERE.txt"]
NEVER = ("gc_icons", "ps2_icons", "shader_cache", "save backups")


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    built = sys.argv[1]
    version = sys.argv[2] if len(sys.argv) == 3 else "Beta 1"
    files = {}
    for n in BUILT:
        p = os.path.join(built, n)
        if not os.path.isfile(p):
            raise SystemExit(f"{n} isn't in {built}")
        files[n] = p
    for n in FROM_REPO:
        p = os.path.join(ROOT, *n.split("/"))
        if os.path.isfile(p):
            files[n] = p
        else:
            print("(no", n + ")")
    assert not any(n.split("/")[0] in NEVER for n in files)
    manifest = {}
    for n, p in sorted(files.items()):
        with open(p, "rb") as f:
            manifest[n] = hashlib.sha256(f.read()).hexdigest()
    out = f"MVP06-Plus-{version.replace(' ', '-')}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n, p in sorted(files.items()):
            zi = zipfile.ZipInfo.from_file(p, n)
            if n == "gcbridge":
                zi.external_attr = 0o100755 << 16  # executable when unzipped on SteamOS
            zi.compress_type = zipfile.ZIP_DEFLATED
            with open(p, "rb") as f:
                z.writestr(zi, f.read())
        z.writestr("SHA256-MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    print("wrote", out, f"({os.path.getsize(out) / 2**20:.1f} MB, {len(files) + 1} files)")


if __name__ == "__main__":
    main()
