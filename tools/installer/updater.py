"""Updates from the MVP06-Plus releases on GitHub, from the Launcher.

  check()              the latest release, if it's newer than this one: version, notes, its zip
  download()           the zip into .update/ in the game folder
  verify()             every file in it against its SHA256-MANIFEST.json, and nothing outside the program files
  apply()              the program files replaced, the old ones kept in .update/previous to undo; your game files,
                       saves, backups, button art, shader cache and logs are never touched; your settings are kept,
                       with any new options added
  undo()               the program files from before the last update back

Only api.github.com and GitHub's download host are contacted, and only to check or to download.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile

# For testing an update before it's public (Test-Updater.cmd sets these; players never do): another repository,
# a private one read with a GitHub token
REPO = os.environ.get("MVP06_UPDATE_REPO") or "spy-jam/MVP06-Plus"
TOKEN = os.environ.get("MVP06_UPDATE_TOKEN") or ""
RELEASES = f"https://api.github.com/repos/{REPO}/releases?per_page=20"  # betas are pre-releases, which /latest skips
PAGE = f"https://github.com/{REPO}/releases/latest"
AGENT = "MVP06-Plus-Launcher"
GAME_EXE = "MVP06.exe"
LAUNCHER_EXE = "MVP06-Plus-Launcher.exe"
SETTINGS = "mvp06-settings.toml"
MANIFEST = "SHA256-MANIFEST.json"
WORK = ".update"  # in the game folder: the download, and the files the last update replaced
# yours, never written by an update (a release zip holding any of these is refused)
PROTECTED = ("assets", "hdd", "save backups", "gc_icons", "ps2_icons", "shader_cache", "logs", WORK)
# in every release zip, but nothing an update needs: checked against the manifest like the rest, then left out
SKIP = ("assets/PUT-GAME-FILES-HERE.txt",)


class UpdateError(Exception):
    pass


def version_key(v):
    """'Beta 2', 'beta-2', 'v1.0', '1.0.1' -> comparable: betas before release candidates before releases."""
    s = v.strip().lower().lstrip("v")
    nums = tuple(int(n) for n in re.findall(r"\d+", s)) or (0,)
    stage = 0 if "beta" in s else 1 if "rc" in s else 2
    return (stage,) + nums


def newer(latest, current):
    return version_key(latest) > version_key(current)


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """A private release's download goes from GitHub to its file host, which refuses GitHub's token."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).hostname != urllib.parse.urlparse(req.full_url).hostname:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new


def _get(url, timeout=15, accept="application/vnd.github+json"):
    headers = {"User-Agent": AGENT, "Accept": accept}
    if TOKEN and urllib.parse.urlparse(url).hostname == "api.github.com":
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.build_opener(_DropAuthOnRedirect).open(req, timeout=timeout)


def check(current):
    """The newest published release, if it's newer than current, else None: {version, tag, notes, url, size, page}."""
    try:
        with _get(RELEASES) as r:
            rels = json.load(r)
    except Exception as e:  # offline, GitHub down, rate limited
        raise UpdateError(f"couldn't reach GitHub ({e})")
    best = None
    for rel in rels if isinstance(rels, list) else []:
        if rel.get("draft"):
            continue
        version = re.sub(r"^MVP06-Plus\s*", "", rel.get("name") or "").strip() or rel.get("tag_name", "")
        if version and (best is None or newer(version, best[0])):
            best = (version, rel)
    if not best or not newer(best[0], current):
        return None
    version, rel = best
    zips = [a for a in rel.get("assets", []) if a.get("name", "").startswith("MVP06-Plus-") and a["name"].endswith(".zip")]
    if not zips:
        raise UpdateError(f"{version} has no MVP06-Plus zip to download")
    a = zips[0]
    # a private repository's files come through the API, with the token
    return {"version": version, "tag": rel.get("tag_name", ""), "notes": rel.get("body") or "",
            "url": a["url"] if TOKEN else a["browser_download_url"], "size": a.get("size", 0), "name": a["name"],
            "page": rel.get("html_url") or PAGE}


def download(root, info, progress=None):
    """The release zip into .update/, its size checked; progress(done, total)."""
    os.makedirs(os.path.join(root, WORK), exist_ok=True)
    dest = os.path.join(root, WORK, info["name"])
    part = dest + ".part"
    try:
        with _get(info["url"], timeout=60, accept="application/octet-stream") as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            done = 0
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
                done += len(b)
                if progress:
                    progress(done, total)
    except Exception as e:
        raise UpdateError(f"the download stopped ({e})")
    if info.get("size") and os.path.getsize(part) != info["size"]:
        raise UpdateError("the download is incomplete")
    os.replace(part, dest)
    return dest


def _safe(name):
    parts = name.replace("\\", "/").split("/")
    low = "/".join(parts).lower()
    return name and not name.startswith("/") and ":" not in name and ".." not in parts and \
        not any(low == p.lower() or low.startswith(p.lower() + "/") for p in PROTECTED)


def verify(zip_path):
    """{name: bytes} of the zip's files, each matching the manifest, all program files."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            manifest = json.loads(z.read(MANIFEST))
            names = [n for n in z.namelist() if not n.endswith("/") and n != MANIFEST]
            if sorted(names) != sorted(manifest):
                raise UpdateError("the zip's files don't match its manifest")
            out = {}
            for n in names:
                skip = n in SKIP
                if not skip and not _safe(n):
                    raise UpdateError(f"the zip has a file it mustn't: {n}")
                data = z.read(n)
                if hashlib.sha256(data).hexdigest() != manifest[n]:
                    raise UpdateError(f"{n} in the download is damaged")
                if not skip:
                    out[n] = data
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise UpdateError(f"the download isn't a release zip ({e})")
    if GAME_EXE not in out or LAUNCHER_EXE not in out:
        raise UpdateError("the zip has no MVP06.exe or Launcher")
    return out


def game_running():
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}", "/NH"], capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=10)
        return GAME_EXE.lower() in r.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def own_exe():
    """This Launcher's .exe when it runs as one, else None."""
    return os.path.abspath(sys.executable) if getattr(sys, "frozen", False) else None


def merged_settings(new_text, old_values):
    """The new release's settings file with your values in it, and any of yours it doesn't have added at the end."""
    import settings as ST
    import tempfile
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, ST.FILE)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        ST.write(d, old_values)
        with open(p, encoding="utf-8", newline="") as f:
            return f.read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _put(dest, data, moved):
    """data written as dest. A file Windows has open (the running Launcher, a DLL it loaded) can't be replaced, but
    it can be renamed: it goes to dest.old (removed at the next start) and the new one takes its name."""
    with open(dest + ".new", "wb") as f:
        f.write(data)
    try:
        os.replace(dest + ".new", dest)
    except PermissionError:
        old = dest + ".old"
        if os.path.exists(old):
            os.remove(old)
        os.replace(dest, old)
        moved.append(dest)
        os.replace(dest + ".new", dest)


def _same(dest, data):
    try:
        return os.path.getsize(dest) == len(data) and open(dest, "rb").read() == data
    except OSError:
        return False


def apply(root, files, version_from):
    """The program files written; the ones replaced kept in .update/previous (one update back) to undo. A file
    that's the same in both versions is left alone."""
    import settings as ST
    if game_running():
        raise UpdateError("MVP06 is running: quit the game first")
    prev = os.path.join(root, WORK, "previous")
    shutil.rmtree(prev, ignore_errors=True)
    os.makedirs(prev)
    written, added, moved = [], [], []
    try:
        for name, data in sorted(files.items()):
            dest = os.path.join(root, *name.split("/"))
            if name == SETTINGS and os.path.isfile(dest):
                data = merged_settings(data.decode("utf-8"), ST.read(root)).encode("utf-8")
            if _same(dest, data):
                continue
            if os.path.isfile(dest):
                keep = os.path.join(prev, *name.split("/"))
                os.makedirs(os.path.dirname(keep), exist_ok=True)
                shutil.copy2(dest, keep)
                written.append(name)
            else:
                added.append(name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            _put(dest, data, moved)
    except OSError as e:
        _restore(root, prev, written, added, moved)
        raise UpdateError(f"couldn't write the new files ({e}); nothing was changed")
    with open(os.path.join(prev, "update.json"), "w") as f:
        json.dump({"from": version_from, "replaced": written, "added": added}, f, indent=2)


def _restore(root, prev, written, added, moved):
    """A failed update undone: each file as it was (one that was moved aside gets its name back)."""
    moved = {os.path.normcase(m) for m in moved}
    for name in written:
        dest = os.path.join(root, *name.split("/"))
        try:
            if os.path.normcase(dest) in moved and os.path.exists(dest + ".old"):
                if os.path.exists(dest):
                    os.remove(dest)
                os.replace(dest + ".old", dest)
            else:
                shutil.copy2(os.path.join(prev, *name.split("/")), dest)
        except OSError:
            pass
    for name in added:
        try:
            os.remove(os.path.join(root, *name.split("/")))
        except OSError:
            pass


def last_update(root):
    """{from, replaced, added} of the last update, if it can be undone."""
    try:
        with open(os.path.join(root, WORK, "previous", "update.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def undo(root):
    """The program files from before the last update back (your settings as they are now)."""
    info = last_update(root)
    if not info:
        raise UpdateError("there's no update to undo")
    if game_running():
        raise UpdateError("MVP06 is running: quit the game first")
    prev = os.path.join(root, WORK, "previous")
    files = {}
    for name in info["replaced"]:
        if name == SETTINGS:
            continue  # the settings stay yours
        with open(os.path.join(prev, *name.split("/")), "rb") as f:
            files[name] = f.read()
    try:
        for name, data in files.items():
            _put(os.path.join(root, *name.split("/")), data, [])
        for name in info["added"]:
            if name != SETTINGS:
                try:
                    os.remove(os.path.join(root, *name.split("/")))
                except OSError:
                    pass
    except OSError as e:
        raise UpdateError(f"couldn't put the old files back ({e})")
    shutil.rmtree(prev, ignore_errors=True)
    return info["from"]


def tidy(root):
    """At start: the renamed old Launcher and a finished download removed."""
    for d in (root, os.path.dirname(own_exe() or root)):  # files moved aside by an update, now closed
        for n in os.listdir(d) if os.path.isdir(d) else ():
            if n.endswith(".old"):
                try:
                    os.remove(os.path.join(d, n))
                except OSError:
                    pass  # still in use; next time
    w = os.path.join(root, WORK)
    for n in os.listdir(w) if os.path.isdir(w) else ():
        if n.endswith(".zip") or n.endswith(".part"):
            try:
                os.remove(os.path.join(w, n))
            except OSError:
                pass


def restart(pretend=None):
    """The (new) Launcher started again; the caller then closes. pretend: after an undo in Test-Updater.cmd's test
    (its files are the same build before and after), the version it went back to, so the test shows it."""
    me = own_exe()
    args = [me] if me else [sys.executable, os.path.abspath(sys.argv[0])]
    env = dict(os.environ)
    env.pop("MVP06_TEST_VERSION", None)  # a test: the new Launcher is the version it says it is
    # the Launcher exe unpacks itself to a temporary folder; started with this one's PyInstaller settings, the new
    # one would take itself for a helper of this one and use its folder, which is deleted when this one closes
    # ("Failed to start embedded python interpreter"). It starts as a program of its own
    for k in list(env):
        if k.startswith("_PYI_") or k in ("_MEIPASS2", "_PYI_SPLASH_IPC"):
            env.pop(k)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if pretend and env.get("MVP06_UPDATE_REPO"):
        env["MVP06_TEST_VERSION"] = pretend
    subprocess.Popen(args, close_fds=True, env=env)
