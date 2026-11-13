"""The updater on a pretend game folder: python tests/test_updater.py <tools/installer>"""
import hashlib, io, json, os, sys, tempfile, zipfile
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), ".."))
import updater as U


def release_zip(path, files):
    man = {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}
    with zipfile.ZipFile(path, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
        z.writestr(U.MANIFEST, json.dumps(man))


def put(root, name, data):
    p = os.path.join(root, *name.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)


def get(root, name):
    with open(os.path.join(root, *name.split("/")), "rb") as f:
        return f.read()


assert U.newer("Beta 2", "Beta 1") and not U.newer("Beta 1", "Beta 1") and U.newer("1.0", "Beta 9")
assert U.newer("v1.0.1", "1.0") and not U.newer("Beta 3", "1.0") and U.newer("RC 1", "Beta 4")

root = tempfile.mkdtemp()
old = {"MVP06.exe": b"old game", U.LAUNCHER_EXE: b"old launcher", "README.md": b"old readme",
       U.SETTINGS: b"# display\r\ndisplay_mode = \"fullscreen\"  # how\r\nwidth = 0\r\nsave_backups = 30\r\n"}
for n, d in old.items():
    put(root, n, d)
put(root, U.SETTINGS, b"# display\r\ndisplay_mode = \"windowed\"  # how\r\nwidth = 1920\r\nsave_backups = 100\r\nmine = true\r\n")
put(root, "assets/default.xbe", b"game")
put(root, "hdd/E/UDATA/x/save", b"save")

new = {"MVP06.exe": b"new game", U.LAUNCHER_EXE: b"new launcher", "README.md": b"new readme",
       "NEW-FILE.txt": b"added", U.SETTINGS: b"# display\r\ndisplay_mode = \"fullscreen\"  # how\r\nwidth = 0\r\n"
       b"save_backups = 30\r\nnew_option = true  # new\r\n",
       "assets/PUT-GAME-FILES-HERE.txt": b"in every release zip"}
z = os.path.join(root, "rel.zip")
release_zip(z, new)
files = U.verify(z)
assert "assets/PUT-GAME-FILES-HERE.txt" not in files  # checked, then left out: nothing goes into assets
U.apply(root, files, "Beta 1")
assert not os.path.exists(os.path.join(root, "assets", "PUT-GAME-FILES-HERE.txt"))
assert get(root, "MVP06.exe") == b"new game" and get(root, "NEW-FILE.txt") == b"added"
s = get(root, U.SETTINGS).decode()
assert 'display_mode = "windowed"  # how' in s and "width = 1920" in s and "save_backups = 100" in s, s
assert "new_option = true  # new" in s and "mine = true" in s and "\r\n" in s, s
assert get(root, "assets/default.xbe") == b"game" and get(root, "hdd/E/UDATA/x/save") == b"save"
assert U.last_update(root)["from"] == "Beta 1"
assert U.undo(root) == "Beta 1"
assert get(root, "MVP06.exe") == b"old game" and get(root, "README.md") == b"old readme"
assert not os.path.exists(os.path.join(root, "NEW-FILE.txt"))
assert "save_backups = 100" in get(root, U.SETTINGS).decode()  # undo keeps your settings
assert U.last_update(root) is None

# refused: a damaged file, a file into your game files, a zip without the game
release_zip(z, new)
with zipfile.ZipFile(z, "a") as zz:
    zz.writestr("extra.txt", b"x")  # not in the manifest
try:
    U.verify(z); raise SystemExit("file outside the manifest accepted")
except U.UpdateError:
    pass
release_zip(z, dict(new, **{"assets/default.xbe": b"evil"}))
try:
    U.verify(z); raise SystemExit("protected file accepted")
except U.UpdateError as e:
    assert "mustn't" in str(e)
release_zip(z, {"README.md": b"x"})
try:
    U.verify(z); raise SystemExit("zip without the game accepted")
except U.UpdateError:
    pass
man = {n: hashlib.sha256(d).hexdigest() for n, d in new.items()}
man["MVP06.exe"] = "0" * 64
with zipfile.ZipFile(z, "w") as zz:
    for n, d in new.items():
        zz.writestr(n, d)
    zz.writestr(U.MANIFEST, json.dumps(man))
try:
    U.verify(z); raise SystemExit("damaged file accepted")
except U.UpdateError as e:
    assert "damaged" in str(e)

# files Windows has open (the running Launcher, a DLL it loaded) can't be replaced, only renamed: as on Windows
real_replace = os.replace
locked = set()


def windows_replace(src, dst):
    if os.path.normcase(dst) in locked and os.path.exists(dst):
        raise PermissionError(5, "Access is denied", dst)
    real_replace(src, dst)
    if os.path.normcase(src) in locked:  # the open file went with its new name
        locked.discard(os.path.normcase(src))
        locked.add(os.path.normcase(dst))


U.os.replace = windows_replace
U.own_exe = lambda: os.path.join(root, U.LAUNCHER_EXE)
put(root, U.LAUNCHER_EXE, b"old launcher")
put(root, "vcruntime140.dll", b"old dll")
put(root, "msvcp140.dll", b"same dll")
locked |= {os.path.normcase(os.path.join(root, n)) for n in (U.LAUNCHER_EXE, "vcruntime140.dll")}
both = dict(new, **{"vcruntime140.dll": b"new dll", "msvcp140.dll": b"same dll"})
release_zip(z, both)
U.apply(root, U.verify(z), "Beta 1")
assert get(root, U.LAUNCHER_EXE) == b"new launcher" and get(root, U.LAUNCHER_EXE + ".old") == b"old launcher"
assert get(root, "vcruntime140.dll") == b"new dll" and get(root, "vcruntime140.dll.old") == b"old dll"
assert "msvcp140.dll" not in U.last_update(root)["replaced"]  # the same in both: left alone
locked.clear()  # the old Launcher closed
U.tidy(root)
assert not os.path.exists(os.path.join(root, U.LAUNCHER_EXE + ".old"))
assert not os.path.exists(os.path.join(root, "vcruntime140.dll.old"))

# a write failing part way: everything back as it was, the moved files under their own names again
put(root, U.LAUNCHER_EXE, b"old launcher")
put(root, "vcruntime140.dll", b"old dll")
locked |= {os.path.normcase(os.path.join(root, n)) for n in (U.LAUNCHER_EXE, "vcruntime140.dll")}
blocked = os.path.normcase(os.path.join(root, "README.md"))
before = U.os.replace


def failing_replace(src, dst):
    if os.path.normcase(dst) == blocked:
        raise OSError(28, "No space left on device", dst)
    before(src, dst)


U.os.replace = failing_replace
release_zip(z, dict(both, **{"README.md": b"newer readme"}))
try:
    U.apply(root, U.verify(z), "Beta 1"); raise SystemExit("a failed write went through")
except U.UpdateError as e:
    assert "nothing was changed" in str(e)
assert get(root, U.LAUNCHER_EXE) == b"old launcher" and get(root, "vcruntime140.dll") == b"old dll"
assert not os.path.exists(os.path.join(root, "vcruntime140.dll.old"))
U.os.replace = real_replace
locked.clear()

# check(): GitHub's answer read
class R(io.BytesIO):
    headers = {}
    def __enter__(self): return self
    def __exit__(self, *a): pass
U._get = lambda url, timeout=15: R(json.dumps([
    {"name": "MVP06-Plus Beta 4", "tag_name": "beta-4", "draft": True, "assets": []},
    {"name": "MVP06-Plus Beta 3", "tag_name": "beta-3", "prerelease": True, "body": "## New\n- x", "html_url": "h",
     "assets": [{"name": "MVP06-Plus-Beta-3.zip", "browser_download_url": "u", "size": 5}]},
    {"name": "MVP06-Plus Beta 1", "tag_name": "beta-1", "assets": []}]).encode())
i = U.check("Beta 2")
assert i["version"] == "Beta 3" and i["url"] == "u" and i["name"] == "MVP06-Plus-Beta-3.zip", i
assert U.check("Beta 3") is None
print("updater tests passed")
