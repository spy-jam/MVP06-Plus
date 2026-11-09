"""MVP06-Plus Launcher. Install: puts your own discs' game files where the game looks for them, in the folder the installer is in.

  Xbox disc (required)        every file, into assets/ (as Mad Dog's original asks for by hand)
  GameCube art (optional)     there was no GameCube MVP 06: made from MVP 2005's GameCube art, the gc_icons of an
                              MVP05-Plus install (tools/gc_layout/make_gc_icons06.py), or a 06 gc_icons set copied
  PS2 disc (optional)         only the 4 files the button art needs, read into a temporary folder, made into
                              ps2_icons/ (tools/ps2_layout/make_ps2_icons06.py), then deleted

Nothing is written anywhere else: no registry, no shortcuts, no Program Files. Deleting the folder removes it all.

Save backups: the game's own backups of your saves (save backups/), listed and restored.

  MVP06-Plus-Launcher.exe                       the window
  MVP06-Plus-Launcher.exe --xbox X [--gamecube G] [--ps2 P] [--dir D]   installing without it
"""
import argparse
import datetime
import json
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("gc_layout", "ps2_layout"):  # the art builders (bundled beside this when frozen)
    for base in (os.path.join(HERE, "..", sub), os.path.join(getattr(sys, "_MEIPASS", HERE), sub)):
        if os.path.isdir(base) and base not in sys.path:
            sys.path.insert(0, base)

import discs  # noqa: E402

VERSION = "Beta 1"
GAME = "MVP06-Plus"


def game_dir():
    """The folder with MVP06.exe: the installer's own (frozen), else the repository's root."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(HERE, "..", ".."))


class Log:
    """Messages, and one progress bar across the whole install: the steps (plan) each get a share of the bar by how
    long they usually take; status shows "Step 2 of 3: ..." with the time so far."""
    def __init__(self, say=print, progress=None, status=None):
        self.say, self.progress, self.status = say, progress, status
        self.steps, self.at, self.label, self.started = [], -1, "", 0.0
        self._timer = None

    def plan(self, steps):
        """steps: [(label, seconds it usually takes)]"""
        self.steps, self.at = list(steps), -1

    def step(self, label=None):
        """On to the next step of the plan."""
        import time
        if self.at >= 0:
            self.part(1.0)
        self.at = min(self.at + 1, len(self.steps) - 1)
        self.label = label or (self.steps[self.at][0] if self.steps else "")
        self.started = time.monotonic()
        self.part(0.0)
        self.show_status()

    def show_status(self):
        if self.status and self.steps:
            import time
            t = int(time.monotonic() - self.started)
            self.status(f"Step {self.at + 1} of {len(self.steps)}: {self.label}  ({t // 60}:{t % 60:02d})")

    def part(self, f):
        """This far (0 to 1) through the current step."""
        if not self.progress:
            return
        if not self.steps or self.at < 0:
            return self.progress(f)
        total = sum(s for _, s in self.steps)
        before = sum(s for _, s in self.steps[:self.at])
        self.progress((before + min(max(f, 0.0), 1.0) * self.steps[self.at][1]) / total)

    def timed(self, seconds):
        """For work that can't say how far it is: the bar moves on by the time it usually takes, slowing as it nears the
        end of the step's share so it never sits full while there's still work."""
        log = self

        class Timer:
            def __enter__(self):
                import threading, time, math
                self.stop = threading.Event()

                def tick():
                    t0 = time.monotonic()
                    while not self.stop.wait(0.25):
                        t = time.monotonic() - t0
                        f = 0.9 * t / seconds if t < seconds else 0.9 + 0.08 * (1 - math.exp(-(t - seconds) / seconds))
                        log.part(f)
                        log.show_status()
                threading.Thread(target=tick, daemon=True).start()
                return self

            def __exit__(self, *a):
                self.stop.set()
        return Timer()

    def finish(self, text):
        if self.progress:
            self.progress(1.0)
        if self.status:
            self.status(text)


def need_space(folder, nbytes):
    free = shutil.disk_usage(folder).free
    if free < nbytes + (64 << 20):
        raise discs.DiscError(f"not enough room: {nbytes / 2**30:.1f} GB needed, {free / 2**30:.1f} GB free")


def install_xbox(src, root, log):
    assets = os.path.join(root, "assets")
    with discs.open_xbox(src) as d:
        files = d.files()
        todo = {}
        for p, (_, n) in files.items():
            dest = os.path.join(assets, *p.split("/"))
            if not (os.path.isfile(dest) and os.path.getsize(dest) == n):
                todo[p] = (dest, n)
        total = sum(n for _, n in todo.values())
        log.say(f"Xbox disc: {discs.GAME_NAME}, {len(files)} files"
                + (f", copying {len(todo)} ({total / 2**20:.0f} MB)" if todo else ", already in assets"))
        if todo:
            need_space(root, total)
        done = [0]

        def step(n):
            done[0] += n
            log.part(done[0] / total)

        for p, (dest, _) in sorted(todo.items()):
            d.copy(p, dest, step)
        with open(os.path.join(assets, MANIFEST), "w") as f:  # what a complete install has: checked at each start
            json.dump({"title": discs.GAME_NAME + " (Xbox)", "files": {p: n for p, (_, n) in files.items()}}, f)
    log.say("Xbox files are in assets.")


MANIFEST = "mvp06-plus-install.json"
# about how long each step takes (seconds), for its share of the progress bar; the art steps can't report progress, so
# the bar moves by these. Measured on a modest PC; a faster one just finishes early
SECONDS = {"xbox": 40, "ps2": 50, "gc2005": 45, "gc06": 55}
LAUNCHER_FILE = "mvp06-plus-launcher.json"  # the Launcher's own: where DolphinTool / chdman are, once chosen


def load_tools(root):
    try:
        with open(os.path.join(root, LAUNCHER_FILE)) as f:
            discs.TOOL_PATHS.update(json.load(f).get("tools", {}))
    except (OSError, ValueError):
        pass


def remember_tool(root, tool, path):
    discs.TOOL_PATHS[tool] = path
    p = os.path.join(root, LAUNCHER_FILE)
    try:
        with open(p) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault("tools", {})[tool] = path
    with open(p, "w") as f:
        json.dump(data, f, indent=2)


def check_install(root):
    """What's installed, for the window: {exe, xbox, xbox_ok, gamecube, ps2} (texts; xbox_ok True when playable)."""
    assets = os.path.join(root, "assets")
    r = {"exe": os.path.isfile(os.path.join(root, "MVP06.exe"))}
    xbe = os.path.join(assets, "default.xbe")
    if not os.path.isfile(xbe):
        r["xbox"], r["xbox_ok"] = "not installed", False
    else:
        try:
            with open(xbe, "rb") as f:
                tid, name = discs.xbe_title(f.read())
            if tid != discs.XBOX_TITLE:
                raise discs.DiscError(f"assets holds {name or 'another game'}, not {discs.GAME_NAME}")
            m = os.path.join(assets, MANIFEST)
            if os.path.isfile(m):
                with open(m) as f:
                    want = json.load(f)["files"]
                gone, bad = [], []
                for p, n in want.items():
                    f = os.path.join(assets, *p.split("/"))
                    if not os.path.isfile(f):
                        gone.append(p)
                    elif os.path.getsize(f) != n:
                        bad.append(p)
                if bad or gone:
                    r["xbox"], r["xbox_ok"] = f"incomplete: {len(bad) + len(gone)} of {len(want)} files missing or " \
                                              f"changed (install it again)", False
                else:
                    r["xbox"], r["xbox_ok"] = f"installed ({len(want)} files, all there)", True
            elif os.path.isfile(os.path.join(assets, "data", "frontend", "shared.big")):
                r["xbox"], r["xbox_ok"] = "installed (put there by hand)", True
            else:
                r["xbox"], r["xbox_ok"] = "incomplete: default.xbe is there but the game's data isn't", False
        except Exception as e:
            r["xbox"], r["xbox_ok"] = f"can't be used: {e}", False
    for kind, name in (("gamecube", "gc_icons"), ("ps2", "ps2_icons")):
        d = os.path.join(root, name)
        if not os.path.isfile(os.path.join(d, "data", "frontend", "shared.big")):
            r[kind] = "not installed (optional)"
        else:
            have = {os.path.relpath(os.path.join(a, f), d).replace(os.sep, "/").lower()
                    for a, _, fs in os.walk(d) for f in fs}
            missing = [f for f in ICON_FILES[kind] if f not in have]
            r[kind] = "installed" + (" (an older set, missing " + ", ".join(os.path.basename(m) for m in missing) + ")"
                                     if missing else "")
    return r


def run_builder(builder, args, out_name):
    """An art builder's main() with these arguments, its printing kept out of the window."""
    argv, sys.argv = sys.argv, [builder.__file__] + args
    words = io.StringIO()
    try:
        with contextlib.redirect_stdout(words):
            builder.main()
    except SystemExit as e:
        raise discs.DiscError(f"making {out_name} stopped: {e}")
    finally:
        sys.argv = argv


def xbox_data_for_art(root):
    xbox_data = os.path.join(root, "assets", "data")
    if not os.path.isfile(os.path.join(xbox_data, "frontend", "shared.big")):
        raise discs.DiscError("the Xbox files aren't in assets yet: the art is made from them too")
    return xbox_data


def build_art(kind, src, root, log):
    """ps2_icons from the PS2 disc; only the art's files are read, into a temporary folder that's deleted."""
    xbox_data = xbox_data_for_art(root)
    tmp = tempfile.mkdtemp(prefix="mvp-installer-")
    try:
        with discs.open_ps2(src) as d:
            log.say(f"PS2 disc: reading the {len(discs.PS2_ART_FILES)} files the button art needs")
            discs.extract(d, discs.PS2_ART_FILES, tmp, upper=True)
        built = os.path.join(tmp, "ps2_icons")
        import make_ps2_icons06 as builder
        with log.timed(SECONDS["ps2"]):
            run_builder(builder, [xbox_data, os.path.join(tmp, "DATA"), built], "ps2_icons")
        put_icons(built, os.path.join(root, "ps2_icons"))
        log.say(f"ps2_icons made ({count_files(os.path.join(root, 'ps2_icons'))} files).")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_gc_from_discs(gc_src, xbox05_src, root, log):
    """gc_icons for 06 from the MVP 2005 GameCube and Xbox discs: 2005's GameCube art made first, as MVP05-Plus makes
    it (make_icons05.py), from only the files it needs on each disc, then made into 06's. All in a temporary folder."""
    if not xbox05_src:
        raise discs.DiscError("the 2005 GameCube disc's art is made together with the MVP Baseball 2005 Xbox disc: "
                              "choose that too (or your MVP05-Plus folder instead of both)")
    xbox_data_for_art(root)
    tmp = tempfile.mkdtemp(prefix="mvp-installer-")
    try:
        with discs.open_gamecube(gc_src) as d:
            log.say(f"MVP 2005 GameCube disc: reading the {len(discs.GC05_ART_FILES)} files the art needs")
            discs.extract(d, discs.GC05_ART_FILES, os.path.join(tmp, "gc"))
        with discs.open_xbox(xbox05_src, discs.XBOX05_TITLE, discs.XBOX05_NAME) as d:
            log.say(f"MVP 2005 Xbox disc: reading the {len(discs.XBOX05_ART_FILES)} files the art needs")
            discs.extract(d, discs.XBOX05_ART_FILES, os.path.join(tmp, "xb"))
        set2005 = os.path.join(tmp, "gc_icons_2005")
        import make_icons05 as builder
        with log.timed(SECONDS["gc2005"]):
            run_builder(builder, [os.path.join(tmp, "xb", "data"), os.path.join(tmp, "gc", "data"), set2005],
                        "2005's gc_icons")
        log.step("making GameCube button art for 06")
        build_gc_from_2005(set2005, root, log)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_gc_from_2005(set2005, root, log):
    """gc_icons for 06 from MVP 2005's GameCube art (an MVP05-Plus gc_icons): an estimate, as GameCube 06 never was."""
    xbox_data = xbox_data_for_art(root)
    tmp = tempfile.mkdtemp(prefix="mvp-installer-")
    try:
        log.say("Making GameCube art for 06 from MVP 2005's GameCube art (this takes a minute)")
        built = os.path.join(tmp, "gc_icons")
        import make_gc_icons06 as builder
        with log.timed(SECONDS["gc06"]):
            run_builder(builder, [xbox_data, set2005, built], "gc_icons")
        put_icons(built, os.path.join(root, "gc_icons"))
        log.say(f"gc_icons made ({count_files(os.path.join(root, 'gc_icons'))} files).")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def count_files(d):
    return sum(len(f) for _, _, f in os.walk(d))


def put_icons(src, dest):
    """src's set in place of dest's, the old one kept until the new one is all there."""
    old = dest + ".old"
    shutil.rmtree(old, ignore_errors=True)
    if os.path.exists(dest):
        os.replace(dest, old)
    try:
        shutil.copytree(src, dest)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        if os.path.exists(old):
            os.replace(old, dest)
        raise
    shutil.rmtree(old, ignore_errors=True)


# what a made 06 set has (make_gc_icons06.py / make_ps2_icons06.py); a set missing some still works, with Xbox art
# for whatever's missing
_SET06 = ["data/frontend/" + n for n in ("shared.big", "frontend.big", "ingame.big", "igonly.big", "minigame.big",
                                         "cooplay.big", "coopov.big", "cbplay.big")] + ["data/igshapes/igcrsr.xsh"]
ICON_FILES = {"gamecube": _SET06, "ps2": _SET06 + ["data/frontend/apt.big"]}


def is_2005_set(folder):
    """MVP 2005's art (its loading screens are in it), not a 06 set."""
    return os.path.isfile(os.path.join(folder, "data", "frontend", "load3.big"))


def is_icons_source(src):
    """A folder or a .zip: an icons set someone already made, not a disc."""
    return os.path.isdir(src) or src.lower().endswith(".zip")


def find_set(folder, name):
    """The set in folder: folder itself (it has data/frontend), or a name folder in it or one level further down."""
    def has(d):
        return os.path.isfile(os.path.join(d, "data", "frontend", "shared.big"))
    if has(folder) and os.path.basename(folder.rstrip("/\\")).lower() != ("ps2_icons" if name == "gc_icons" else
                                                                               "gc_icons"):
        return folder
    for d in [os.path.join(folder, name)] + [os.path.join(folder, s, name) for s in sorted(os.listdir(folder))
                                             if os.path.isdir(os.path.join(folder, s))]:
        if has(d):
            return d
    return None


def import_icons(kind, src, root, log):
    """gc_icons or ps2_icons someone already made (a folder, or a .zip with it), copied beside the game."""
    name = "gc_icons" if kind == "gamecube" else "ps2_icons"
    tmp = None
    try:
        if not os.path.isdir(src):
            import zipfile
            tmp = tempfile.mkdtemp(prefix="mvp-installer-")
            try:
                with zipfile.ZipFile(src) as z:
                    for m in z.infolist():
                        target = os.path.realpath(os.path.join(tmp, m.filename))
                        if not target.startswith(os.path.realpath(tmp) + os.sep):
                            raise discs.DiscError(f"{os.path.basename(src)} has a file outside its own folders")
                    z.extractall(tmp)
            except zipfile.BadZipFile:
                raise discs.DiscError(f"{os.path.basename(src)} isn't a zip that can be read")
            folder = tmp
        else:
            folder = src
        found = find_set(folder, name)
        if not found:
            raise discs.DiscError(f"no {name} in {os.path.basename(src) or src} (it should hold data/frontend/shared.big)")
        dest = os.path.join(root, name)
        if is_2005_set(found):
            if kind == "gamecube":
                return build_gc_from_2005(found, root, log)
            raise discs.DiscError("that's MVP 2005's ps2_icons: 06 needs its own, made from the MVP 06 PS2 disc")
        if os.path.realpath(found) == os.path.realpath(dest):
            log.say(f"{name} is already in place.")
            return
        have = {os.path.relpath(os.path.join(d, f), found).replace(os.sep, "/").lower()
                for d, _, fs in os.walk(found) for f in fs}
        missing = [f for f in ICON_FILES[kind] if f not in have]
        put_icons(found, dest)
        log.say(f"{name} copied ({count_files(dest)} files).")
        if missing:
            log.say(f"  It's a set without {', '.join(os.path.basename(m) for m in missing)}: the game shows "
                    f"Xbox art there.")
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def run(root, xbox=None, gamecube=None, ps2=None, log=None, xbox05=None):
    """ps2: the MVP 06 PS2 disc image (the art is made from it), or a ps2_icons folder or .zip.
    gamecube (experimental): the MVP 2005 GameCube disc, with xbox05 the MVP 2005 Xbox disc; or an MVP05-Plus folder
    or its gc_icons (2005's GameCube art); either made into 06's. Or a 06 gc_icons folder or .zip, copied."""
    load_tools(root)
    log = log or Log()
    if not (xbox or gamecube or ps2):
        raise discs.DiscError("choose your Xbox disc, and any PS2 disc or GameCube art")
    if gamecube and xbox05 and is_icons_source(gamecube):
        log.say("(the 2005 Xbox disc isn't needed with an MVP05-Plus folder or a gc_icons set: left out)")
    steps = []
    if xbox:
        steps.append(("copying the Xbox game", SECONDS["xbox"]))
    if ps2:
        steps.append(("copying the PS2 button art", 2) if is_icons_source(ps2) else
                     ("making the PS2 button art", SECONDS["ps2"]))
    if gamecube:
        if not is_icons_source(gamecube):
            steps.append(("making MVP 2005's GameCube button art", SECONDS["gc2005"]))
            steps.append(("making GameCube button art for 06", SECONDS["gc06"]))
        else:
            steps.append(("GameCube button art", SECONDS["gc06"]))  # copied, or made from a 2005 set (the long one)
    log.plan(steps)
    if xbox:
        log.step()
        install_xbox(xbox, root, log)
    if ps2:
        log.step()
        (import_icons if is_icons_source(ps2) else build_art)("ps2", ps2, root, log)
    if gamecube:
        log.step()
        if is_icons_source(gamecube):
            import_icons("gamecube", gamecube, root, log)
        else:
            build_gc_from_discs(gamecube, xbox05, root, log)
    if not os.path.isfile(os.path.join(root, "assets", "default.xbe")):
        log.say("The Xbox files aren't in assets yet: choose your Xbox disc too, the game needs it.")
        log.finish("Done (the Xbox game still needs installing)")
    else:
        log.say("Done. Run MVP06.exe.")
        log.finish("Done")


# ---------------------------------------------------------------- the window

def gui(root):
    import tkinter as tk
    from tkinter import filedialog, ttk

    w = tk.Tk()
    w.title(f"{GAME} Launcher ({VERSION}) by spy_jam")
    import title_icon
    title_icon.ensure(root)  # the game's icon from the Xbox disc, once it's installed

    def set_icon():
        ico = os.path.join(root, title_icon.ICO)
        if os.name == "nt" and os.path.isfile(ico):
            try:
                w.iconbitmap(default=ico)
            except tk.TclError:
                pass
    set_icon()
    w.resizable(False, False)
    tabs = ttk.Notebook(w)
    tabs.grid(padx=8, pady=8)
    tab = ttk.Frame(tabs, padding=12)
    tabs.add(tab, text="Install")
    saves_tab(tabs, root, tk, ttk)
    settings_tab(tabs, root, tk, ttk)

    # --- what's installed, with Launch: shown when the game is ready to play
    ready = ttk.Frame(tab)
    ttk.Label(ready, text=f"{GAME} is installed", font=("Segoe UI", 12, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(ready, text=root, foreground="#555").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
    lines = {}
    for i, (k, label) in enumerate((("xbox", "Xbox game"), ("gamecube", "GameCube button art"),
                                    ("ps2", "PS2 button art"))):
        mark = None
        text = ttk.Label(ready)
        text.grid(row=2 + i, column=0, columnspan=2, sticky="w", pady=1)
        lines[k] = (mark, text, label)
    rb = ttk.Frame(ready)
    rb.grid(row=6, column=0, columnspan=2, sticky="we", pady=(16, 0))
    launch = ttk.Button(rb, text="Launch MVP 06")
    launch.pack(side="left", ipadx=18, ipady=6)
    change = ttk.Button(rb, text="Add or change button art, or reinstall…")
    change.pack(side="left", padx=10)
    launch_note = ttk.Label(ready, text="", foreground="#a33", wraplength=520, justify="left")
    launch_note.grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))
    # what Windows sees right now (controllers.py): the adapter and its driver, and the other controllers
    ttk.Label(ready, text="Controllers", font=("Segoe UI", 10, "bold")).grid(row=8, column=0, columnspan=2,
                                                                            sticky="w", pady=(14, 2))
    pad_adapter = ttk.Label(ready, text="Looking…", wraplength=520, justify="left")
    pad_adapter.grid(row=9, column=0, columnspan=2, sticky="w")
    pad_others = ttk.Label(ready, text="", wraplength=520, justify="left")
    pad_others.grid(row=10, column=0, columnspan=2, sticky="w")
    ttk.Label(ready, foreground="#777", wraplength=520, justify="left", text=(
        "Button art follows the controller connected when the game starts.")).grid(
        row=11, column=0, columnspan=2, sticky="w", pady=(4, 0))
    colours = {"ok": "#1a7f37", "warn": "#b35900", "none": "#777"}

    def watch_pads():
        import controllers

        def look():
            try:
                st = controllers.status()
            except Exception as e:
                st = e
            w.after(0, lambda: show_pads(st))

        def show_pads(st):
            if st is None:
                pad_adapter.configure(text="Controller status is shown on Windows.", foreground="#777")
            elif isinstance(st, Exception):
                pad_adapter.configure(text=f"Couldn't read the controllers: {st}", foreground="#777")
            else:
                (level, text), line = controllers.summary(st)
                pad_adapter.configure(text=text, foreground=colours[level])
                pad_others.configure(text=line, foreground="#1a7f37" if st["pads"] or st["xinput"] else "#777")
            if st is not None:
                w.after(3000, lambda: threading.Thread(target=look, daemon=True).start())
        threading.Thread(target=look, daemon=True).start()

    # --- the discs
    frm = ttk.Frame(tab)
    ttk.Label(frm, text=f"{GAME} installs into this folder:", font=("Segoe UI", 10, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(frm, text=root, foreground="#555").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))
    kinds = [
        ("xbox", "Xbox disc (required)", [("Xbox image", "*.iso *.xiso"), ("All files", "*.*")], True),
        ("ps2", "MVP 06 PS2 disc, or a ps2_icons folder or .zip (optional, button art)",
         [("PS2 image or icons zip", "*.iso *.chd *.zip"), ("All files", "*.*")], "ps2_icons"),
        ("gamecube", "MVP 2005 GameCube disc, or your MVP05-Plus folder, or a 06 gc_icons folder or .zip",
         [("GameCube image or gc_icons zip", "*.iso *.gcm *.rvz *.gcz *.ciso *.wia *.zip"), ("All files", "*.*")],
         "gc_icons"),
        ("xbox05", "MVP 2005 Xbox disc (only needed with the GameCube disc above)",
         [("Xbox image", "*.iso *.xiso"), ("All files", "*.*")], True),
    ]
    folder_titles = {"xbox": "The folder with default.xbe", "ps2": "The ps2_icons folder",
                     "gamecube": "Your MVP05-Plus folder, or a gc_icons folder",
                     "xbox05": "The MVP Baseball 2005 folder with default.xbe"}
    vars_ = {}
    labels = {}
    gc_rows = ttk.Frame(frm)  # shown when the experimental GameCube box is ticked
    for i, (k, label, types, folder_ok) in enumerate(kinds):
        v = tk.StringVar()
        vars_[k] = v
        parent, r = (frm, 2 + 2 * i) if k in ("xbox", "ps2") else (gc_rows, 2 * (i - 2))
        labels[k] = ttk.Label(parent, text=label)
        labels[k].grid(row=r, column=0, columnspan=3, sticky="w")
        ttk.Entry(parent, textvariable=v, width=60).grid(row=r + 1, column=0, sticky="we", pady=(0, 6))

        def pick(v=v, types=types):
            p = filedialog.askopenfilename(filetypes=types)
            if p:
                v.set(os.path.normpath(p))

        ttk.Button(parent, text="Image…", command=pick).grid(row=r + 1, column=1, padx=(6, 0), pady=(0, 6))

        def pickdir(v=v, k=k):
            p = filedialog.askdirectory(title=folder_titles[k])
            if p:
                v.set(os.path.normpath(p))
        ttk.Button(parent, text="Folder…", command=pickdir).grid(row=r + 1, column=2, padx=(6, 0), pady=(0, 6))

    gc_on = tk.BooleanVar(value=False)

    def gc_toggle():
        if gc_on.get():
            gc_rows.grid(row=7, column=0, columnspan=3, sticky="we")
        else:
            gc_rows.grid_remove()
            vars_["gamecube"].set("")
            vars_["xbox05"].set("")
    ttk.Checkbutton(frm, text="Experimental GameCube button art support", variable=gc_on,
                    command=gc_toggle).grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 2))
    ttk.Label(gc_rows, foreground="#666", wraplength=560, justify="left", text=(
        "MVP 06 never came out on GameCube, so its GameCube buttons come from MVP 2005. Choose both 2005 discs, "
        "or just an MVP05-Plus folder that already has GameCube art.")).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 4))

    status_text = tk.StringVar(value="")
    ttk.Label(frm, textvariable=status_text, foreground="#444").grid(row=8, column=0, columnspan=3, sticky="w",
                                                                     pady=(8, 0))
    bar = ttk.Progressbar(frm, length=440, mode="determinate", maximum=1.0)
    bar.grid(row=9, column=0, columnspan=3, sticky="we", pady=(2, 4))
    out = tk.Text(frm, width=72, height=8, state="disabled", wrap="word", relief="flat", background="#f4f4f4")
    out.grid(row=10, column=0, columnspan=3, pady=4)
    fb = ttk.Frame(frm)
    fb.grid(row=11, column=0, columnspan=3, sticky="we", pady=(6, 0))
    go = ttk.Button(fb, text="Install")
    go.pack(side="right")
    back = ttk.Button(fb, text="← Back")

    def say(t):
        def f():
            out.configure(state="normal")
            out.insert("end", t + "\n")
            out.see("end")
            out.configure(state="disabled")
        w.after(0, f)

    def show(state=None):
        """The installed view when the game's ready to play, else the discs."""
        r = state or check_install(root)
        ok = r["xbox_ok"] and r["exe"]
        tabs.tab(tab, text="Play" if ok else "Install")  # Install until the game's installed, then Play
        if ok:
            for k, (mark, text, label) in lines.items():
                good = r[k].startswith("installed")
                text.configure(text=f"{label}: {r[k]}", foreground="#1a7f37" if good else "#777")
            frm.grid_remove()
            ready.grid(row=0, column=0, sticky="nw")
            back.pack(side="left")
            labels["xbox"].configure(text="Xbox disc (installed: leave empty, or choose one to install again)")
        else:
            ready.grid_remove()
            frm.grid(row=0, column=0, sticky="nw")
            if not r["exe"]:
                say("Note: MVP06.exe isn't in this folder. Put MVP06-Plus Launcher in the game's folder.")
            elif r["xbox"] != "not installed":
                say(f"Xbox game: {r['xbox']}")
        return ok

    def progress(x):
        w.after(0, lambda: bar.configure(value=x))

    def status(t):
        w.after(0, lambda: status_text.set(t))

    def work():
        try:
            run(root, **{k: (v.get().strip() or None) for k, v in vars_.items()}, log=Log(say, progress, status))
            w.after(0, lambda: bar.configure(value=1.0))
            import title_icon
            if title_icon.ensure(root, say):
                w.after(0, set_icon)
            r = check_install(root)
            if r["xbox_ok"] and r["exe"]:
                w.after(1200, lambda: (show(r), [v.set("") for v in vars_.values()]))
        except discs.ToolMissing as e:
            w.after(0, lambda: ask_tool(e))
        except discs.DiscError as e:
            say(f"Stopped: {e}")
        except Exception:
            say("Something went wrong:\n" + traceback.format_exc(limit=-6))
        finally:
            w.after(0, lambda: go.configure(state="normal"))

    def ask_tool(e):
        """Where DolphinTool / chdman is, asked once and remembered; then the install goes on."""
        say(str(e))
        p = filedialog.askopenfilename(title=f"Where is {e.exe}?", filetypes=[(e.exe, e.exe), ("Programs", "*.exe")])
        if p:
            remember_tool(root, e.tool, os.path.normpath(p))
            say(f"Using {os.path.normpath(p)}")
            start()

    def start():
        go.configure(state="disabled")
        bar.configure(value=0)
        threading.Thread(target=work, daemon=True).start()

    def do_launch():
        exe = os.path.join(root, "MVP06.exe")
        try:
            subprocess.Popen([exe], cwd=root, close_fds=True)
        except OSError as e:
            launch_note.configure(text=f"MVP06.exe wouldn't start: {e}")
            return
        w.after(800, w.destroy)

    def do_change():
        ready.grid_remove()
        frm.grid(row=0, column=0, sticky="nw")

    go.configure(command=start)
    launch.configure(command=do_launch)
    change.configure(command=do_change)
    back.configure(command=lambda: show())
    show()
    watch_pads()
    w.mainloop()


def when_text(t):
    """11-07-2026 3:39 PM"""
    return f"{t.month:02d}-{t.day:02d}-{t.year} {t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def right_click_menu(tree, items_for):
    """A right-click menu on a list's rows: the row under the pointer is picked (kept with the others when it's
    already one of several picked), then items_for(row) gives the menu's [(label, command)]."""
    import tkinter as tk

    def popup(e):
        iid = tree.identify_row(e.y)
        if not iid:
            return
        if iid not in tree.selection():
            tree.selection_set(iid)
        tree.focus(iid)
        m = tk.Menu(tree, tearoff=0)
        for label, cmd in items_for(iid):
            m.add_command(label=label, command=cmd)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()
    tree.bind("<Button-3>", popup)


def open_in_explorer(path):
    os.makedirs(path, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)


def saves_tab(tabs, root, tk, ttk):
    """Saves: Current saves and Backups, each its own tab inside."""
    outer = ttk.Frame(tabs, padding=8)
    tabs.add(outer, text="Saves")
    inner = ttk.Notebook(outer)
    inner.grid(sticky="nwe")
    refresh_current = current_saves_tab(inner, root, tk, ttk)
    refresh_backups = backups_tab(inner, root, tk, ttk, refresh_current)

    def on_tab(_):  # each list as it is now when it's looked at
        if inner.index("current") == 0:
            refresh_current()
        else:
            refresh_backups()
    inner.bind("<<NotebookTabChanged>>", on_tab)


def current_saves_tab(nb, root, tk, ttk):
    import backups as B

    frm = ttk.Frame(nb, padding=10)
    nb.add(frm, text="Current saves")
    ttk.Label(frm, wraplength=520, justify="left", text=(
        "The saves the game uses now, in hdd beside MVP06.exe.")).grid(row=0, column=0, sticky="w", pady=(0, 8))
    tree = ttk.Treeview(frm, columns=("when", "size"), show="tree headings", height=12, selectmode="browse")
    tree.heading("#0", text="Save")
    tree.heading("when", text="Last saved")
    tree.heading("size", text="Size")
    tree.column("#0", width=280, anchor="w")
    tree.column("when", width=150, anchor="w")
    tree.column("size", width=80, anchor="e")
    tree.grid(row=1, column=0, sticky="we")
    note = ttk.Label(frm, text="", foreground="#666")
    note.grid(row=3, column=0, sticky="w", pady=(6, 0))

    def refresh():
        tree.delete(*tree.get_children())
        saves = []
        for i, p in B.save_folders(os.path.join(root, "hdd")).items():
            files = [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs]
            when = max((os.path.getmtime(f) for f in files), default=os.path.getmtime(p))
            saves.append((B.save_name(p), when, sum(os.path.getsize(f) for f in files), p))
        folders.clear()
        for name, when, size, p in sorted(saves, key=lambda x: x[1], reverse=True):
            folders[tree.insert("", "end", text=name, values=(
                when_text(datetime.datetime.fromtimestamp(when)),
                f"{size / 2**20:.1f} MB" if size >= 2**20 else f"{max(1, size // 1024)} KB"))] = p
        note.configure(text="" if saves else "No saves yet: they appear here once you save in the game.")

    folders = {}
    right_click_menu(tree, lambda iid: [("Open folder", lambda: open_in_explorer(folders[iid]))])

    bar = ttk.Frame(frm)
    bar.grid(row=2, column=0, sticky="we", pady=(8, 0))
    ttk.Button(bar, text="Open saves folder",
               command=lambda: open_in_explorer(os.path.join(root, "hdd", B.TITLE_UDATA))).pack(side="right")
    ttk.Button(bar, text="Refresh", command=refresh).pack(side="right", padx=6)
    refresh()
    return refresh


def desktop_resolution():
    """The main screen's resolution in real pixels (not scaled by Windows' display scaling), or None."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        dc = u.GetDC(None)
        try:
            w, h = g.GetDeviceCaps(dc, 118), g.GetDeviceCaps(dc, 117)  # DESKTOPHORZRES, DESKTOPVERTRES
        finally:
            u.ReleaseDC(None, dc)
        return (w, h) if w > 0 and h > 0 else None
    except Exception:
        return None


def settings_tab(tabs, root, tk, ttk):
    """Display options in mvp06-settings.toml: the game reads them when it starts."""
    import settings as ST

    frm = ttk.Frame(tabs, padding=12)
    tabs.add(frm, text="Settings")
    ttk.Label(frm, text="Display", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(frm, foreground="#666", wraplength=520, justify="left", text=(
        "Saved in mvp06-settings.toml beside the game. Changes take effect the next time the game starts.")).grid(
        row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))
    mode = tk.StringVar()
    aspect = tk.StringVar()
    res = tk.StringVar()
    scale = tk.StringVar()
    fps = tk.StringVar()
    aniso = tk.StringVar()
    vsync = tk.BooleanVar()
    x720 = tk.BooleanVar()
    desk = desktop_resolution()
    # The game plays widescreen when the resolution is 3:2 or wider (app::Widescreen), else 4:3, with black bars at
    # the sides of a wider screen. So the aspect ratio is picked here and the resolutions follow it.
    WIDE, NARROW = "Widescreen (16:9)", "Standard (4:3)"
    current = f"Current desktop resolution ({desk[0]} x {desk[1]})" if desk else "Current desktop resolution"
    fit43 = f"Fit to your screen ({desk[1] * 4 // 3} x {desk[1]})" if desk else None
    lists = {WIDE: [current, "1280 x 720", "1600 x 900", "1920 x 1080", "2560 x 1440", "3840 x 2160"],
             NARROW: ([fit43] if fit43 else []) + ["640 x 480", "800 x 600", "1024 x 768", "1280 x 960", "1440 x 1080",
                                                   "1600 x 1200", "1920 x 1440", "2880 x 2160"]}
    fps_names = {"30": 30, "60 (default)": 60, "Unlimited": 0}
    aniso_names = {"Off (as on Xbox)": 0, "2x": 2, "4x": 4, "8x": 8, "16x": 16}
    res_box = ttk.Combobox(frm, textvariable=res, values=lists[WIDE], width=34)
    rows = [
        ("Display mode", ttk.Combobox(frm, textvariable=mode, values=["Windowed", "Borderless", "Fullscreen"],
                                      state="readonly", width=34)),
        ("Aspect ratio", ttk.Combobox(frm, textvariable=aspect, values=[WIDE, NARROW], state="readonly", width=34)),
        ("Resolution", res_box),
        ("Render scale (%)", ttk.Spinbox(frm, textvariable=scale, from_=25, to=200, increment=25, width=34)),
        ("Frame rate cap", ttk.Combobox(frm, textvariable=fps, values=list(fps_names), state="readonly", width=34)),
        ("Texture filtering", ttk.Combobox(frm, textvariable=aniso, values=list(aniso_names), state="readonly",
                                           width=34)),
    ]
    for i, (label, widget) in enumerate(rows):
        ttk.Label(frm, text=label).grid(row=2 + i, column=0, sticky="w", pady=3)
        widget.grid(row=2 + i, column=1, sticky="w", padx=(12, 0), pady=3)
    ttk.Label(frm, text="(or type one, like 1366 x 768)", foreground="#666").grid(
        row=4, column=2, sticky="w", padx=8)
    ttk.Checkbutton(frm, text="VSync", variable=vsync).grid(row=8, column=0, columnspan=2, sticky="w", pady=(6, 0))
    x720_box = ttk.Checkbutton(frm, text="Xbox 720p mode (as on an Xbox console with 720p enabled in the dashboard)",
                               variable=x720)
    x720_box.grid(row=9, column=0, columnspan=3, sticky="w")
    note = ttk.Label(frm, text="", wraplength=520, justify="left")
    note.grid(row=11, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def name_of(d, v):
        return next((k for k, x in d.items() if x == v), str(v))

    def parse_res(text):
        """(w, h), (0, 0) for the desktop's own, or None."""
        if text.startswith("Current desktop"):
            return 0, 0
        if text.startswith("Fit to your screen"):
            text = text[text.index("(") + 1:text.index(")")]
        try:
            w, h = (int(x) for x in text.lower().replace("×", "x").split("x"))
        except ValueError:
            return None
        return (w, h) if 320 <= w <= 16384 and 240 <= h <= 16384 else None

    def is_wide(w, h):
        if not (w and h):
            w, h = desk or (16, 9)
        return w * 2 >= h * 3

    wide_720 = [True]  # 720p mode as it was in 16:9, for switching back

    def shape_changed(_=None):
        narrow = aspect.get() == NARROW
        res_box.configure(values=lists[aspect.get()])
        r = parse_res(res.get())
        if r is None or is_wide(*r) == narrow:  # the resolution isn't the new aspect ratio: the first that is
            res.set(lists[aspect.get()][0])
        # 720p mode is widescreen only: off (and greyed) in 4:3, back as it was in 16:9
        if narrow:
            if str(x720_box.cget("state")) != "disabled":
                wide_720[0] = x720.get()
            x720.set(False)
        else:
            x720.set(wide_720[0])
        x720_box.configure(state="disabled" if narrow else "normal")
        if narrow and mode.get() == "Fullscreen":
            mode.set("Borderless")
            note.configure(text="4:3 plays with black bars at the sides. Display mode is now Borderless: fullscreen "
                                "would switch your screen to a 4:3 mode, which many screens stretch.",
                           foreground="#8a5a00")
        elif not narrow:
            note.configure(text="")

    rows[1][1].bind("<<ComboboxSelected>>", shape_changed)

    def load():
        s = dict(ST.DEFAULTS)
        s.update(ST.read(root))
        mode.set(str(s["display_mode"]).capitalize())
        w, h = int(s.get("width") or 0), int(s.get("height") or 0)
        aspect.set(WIDE if is_wide(w, h) else NARROW)
        res_box.configure(values=lists[aspect.get()])
        if not (w and h):
            res.set(current)
        elif fit43 and desk and (w, h) == (desk[1] * 4 // 3, desk[1]):
            res.set(fit43)
        else:
            res.set(f"{w} x {h}")
        x720_box.configure(state="normal" if aspect.get() == WIDE else "disabled")
        scale.set(str(s["render_percent"]))
        fps.set(name_of(fps_names, s["fps_cap"]))
        aniso.set(name_of(aniso_names, s["anisotropic_filtering"]))
        vsync.set(bool(s["vsync"]))
        wide_720[0] = bool(s["xbox_720p"]) if aspect.get() == WIDE else True
        x720.set(wide_720[0] if aspect.get() == WIDE else False)

    def save():
        r = parse_res(res.get())
        try:
            sc = int(scale.get())
            assert r is not None and 10 <= sc <= 400
        except (ValueError, AssertionError):
            note.configure(text="The resolution is width x height (like 1920 x 1080), and the render scale a "
                                "percentage (100 is the resolution itself).", foreground="#a33")
            return
        w, h = r
        if is_wide(w, h) != (aspect.get() == WIDE):
            note.configure(text=f"{w} x {h} is {'widescreen' if is_wide(w, h) else '4:3'}: pick that aspect ratio, or "
                                f"another resolution.", foreground="#a33")
            return
        fp = fps_names.get(fps.get(), 60) if fps.get() in fps_names else int(fps.get())
        an = aniso_names.get(aniso.get(), 0) if aniso.get() in aniso_names else int(aniso.get().rstrip("x"))
        ST.write(root, {"display_mode": mode.get().lower(), "width": w, "height": h, "render_percent": sc,
                        "fps_cap": fp, "vsync": vsync.get(), "anisotropic_filtering": an,
                        "xbox_720p": x720.get()})
        note.configure(text="Saved. Restart the game if it's running.", foreground="#1a7f37")

    def defaults():
        ST.write(root, dict(ST.DEFAULTS))
        load()
        note.configure(text="Back to the defaults (fullscreen at your desktop's resolution). Restart the game if it's running.",
                       foreground="#1a7f37")

    # desktop shortcuts, only when asked for
    import shortcuts as SC
    ttk.Label(frm, text="Desktop shortcuts", font=("Segoe UI", 10, "bold")).grid(
        row=12, column=0, columnspan=3, sticky="w", pady=(18, 4))
    sc_rows = [(SC.GAME_NAME, lambda: os.path.join(root, "MVP06.exe"), "the game"),
               (SC.TOOLS_NAME, SC.tools_exe, "this Launcher")]
    sc_buttons = {}

    def sc_refresh():
        for name, target, _ in sc_rows:
            b, lbl = sc_buttons[name]
            if os.name != "nt" or not target() or not os.path.isfile(target()):
                b.configure(text="Create", state="disabled")
                lbl.configure(text=f"\"{name}\": " + ("Windows only" if os.name != "nt" else
                                                       "only from the Launcher's .exe" if not target() else
                                                       "MVP06.exe isn't here"), foreground="#777")
            elif SC.exists(name):
                b.configure(text="Remove", state="normal")
                lbl.configure(text=f"\"{name}\" is on your desktop", foreground="#1a7f37")
            else:
                b.configure(text="Create", state="normal")
                lbl.configure(text=f"\"{name}\": not on your desktop", foreground="#555")

    def sc_toggle(name, target, what):
        try:
            if SC.exists(name):
                SC.remove(name)
            else:
                import title_icon
                SC.create(name, target(), os.path.join(root, title_icon.ICO),
                          f"Opens {what}")
        except OSError as e:
            note.configure(text=f"Couldn't change the shortcut: {e}", foreground="#a33")
        sc_refresh()

    for i, (name, target, what) in enumerate(sc_rows):
        b = ttk.Button(frm, width=9, command=lambda n=name, t=target, w_=what: sc_toggle(n, t, w_))
        b.grid(row=13 + i, column=0, sticky="w", pady=2)
        lbl = ttk.Label(frm)
        lbl.grid(row=13 + i, column=1, columnspan=2, sticky="w", padx=(12, 0))
        sc_buttons[name] = (b, lbl)
    sc_refresh()

    bar = ttk.Frame(frm)
    bar.grid(row=10, column=0, columnspan=3, sticky="we", pady=(14, 0))
    ttk.Button(bar, text="Save", command=save).pack(side="right")
    ttk.Button(bar, text="Defaults", command=defaults).pack(side="right", padx=6)
    ttk.Button(bar, text="Open the settings file", command=lambda: os.startfile(os.path.join(root, ST.FILE))
               if os.name == "nt" else None).pack(side="left")
    load()


def backups_tab(nb, root, tk, ttk, refresh_current):
    from tkinter import messagebox
    import backups as B
    import settings as ST

    frm = ttk.Frame(nb, padding=10)
    nb.add(frm, text="Backups")
    ttk.Label(frm, wraplength=520, justify="left", text=(
        "A backup is made each time the game starts. Open a date and pick the save to restore. Click the date to "
        "restore every save from that date.")).grid(
        row=1, column=0, sticky="w", pady=(0, 8))
    tree = ttk.Treeview(frm, columns=("state",), show="tree headings", height=10, selectmode="extended")
    tree.heading("#0", text="Backed up / save")
    tree.heading("state", text="Compared to current saves")
    tree.column("#0", width=330, anchor="w")
    tree.column("state", width=190, anchor="w")
    tree.grid(row=2, column=0, sticky="we")
    out = tk.Text(frm, width=72, height=4, state="disabled", wrap="word", relief="flat", background="#f4f4f4")
    out.grid(row=4, column=0, pady=(8, 0))
    rows = {}

    def say(t):
        out.configure(state="normal")
        out.insert("end", t + "\n")
        out.see("end")
        out.configure(state="disabled")

    def refresh():
        tree.delete(*tree.get_children())
        rows.clear()
        for b in B.list_backups(root):
            when = when_text(b["when"]) + (" (before restore)" if "before restore" in b["name"] else "")
            n = len(b["items"])
            parent = tree.insert("", "end", text=when, values=(f"{n} save{'s' if n != 1 else ''}",))
            rows[parent] = ("backup", b, None)
            for s in b["items"]:
                iid = tree.insert(parent, "end", text=s["name"], values=(s["state"],))
                rows[iid] = ("save", b, s)
        if not rows:
            say("No backups yet: the game makes one when it starts, once you have saves.")

    def do_restore():
        sel = [rows[i] for i in tree.selection()]
        if not sel:
            messagebox.showinfo("Save backups", "Pick a date, or saves under one, first.")
            return
        backups_picked = {id(b): b for _, b, _ in sel}
        if len(backups_picked) > 1:
            messagebox.showinfo("Save backups", "Pick saves from one date at a time.")
            return
        b = sel[0][1]
        whole = any(kind == "backup" for kind, _, _ in sel)
        picked = b["items"] if whole else [s for kind, _, s in sel if kind == "save"]
        when = when_text(b["when"])
        names = "\n".join("   •  " + s["name"] for s in picked) or "   (no saves)"
        if whole:
            what = (f"Restore all saves from {when}?\n\n{names}\n\nThis replaces all your current saves. They're "
                    f"backed up to the save backups folder first.")
        else:
            what = (f"Restore from {when}?\n\n{names}\n\nYour current saves are backed up to the save backups "
                    f"folder first.")
        if not messagebox.askyesno("Restore saves?", what):
            return
        try:
            B.restore(root, b["path"], say=say, ids=None if whole else [s["id"] for s in picked])
        except B.BackupError as e:
            say(f"Stopped: {e}")
        except Exception as e:
            say(f"Something went wrong: {e}")
        refresh()
        refresh_current()

    keep = tk.StringVar(value=str(ST.read(root).get("save_backups", 30)))
    choices = ["0", "15", "30", "50", "100", "250", "1000"]
    if keep.get() not in choices:  # a number set by hand in the settings file stays in the list
        choices = sorted(choices + [keep.get()], key=lambda x: int(x) if x.isdigit() else 0)

    def save_keep(*_):
        n = int(keep.get())
        if ST.read(root).get("save_backups") != n:
            ST.write(root, {"save_backups": n})

    bar = ttk.Frame(frm)
    bar.grid(row=3, column=0, sticky="we", pady=(8, 0))
    ttk.Button(bar, text="Restore…", command=do_restore).pack(side="left")

    def backup_menu(iid):
        kind, b, sv = rows[iid]
        return [("Restore…", do_restore), ("Open folder", lambda: open_in_explorer(sv["path"] if sv else b["path"]))]
    right_click_menu(tree, backup_menu)
    ttk.Label(bar, text="Keep").pack(side="left", padx=(16, 4))
    kb = ttk.Combobox(bar, textvariable=keep, values=choices, state="readonly", width=6)
    kb.pack(side="left")
    kb.bind("<<ComboboxSelected>>", save_keep)
    ttk.Label(bar, text="backups").pack(side="left", padx=(4, 0))
    ttk.Button(bar, text="Open backups folder",
               command=lambda: open_in_explorer(os.path.join(root, "save backups"))).pack(side="right")
    ttk.Button(bar, text="Refresh", command=refresh).pack(side="right", padx=6)
    refresh()
    return refresh


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--xbox")
    a.add_argument("--gamecube")
    a.add_argument("--ps2")
    a.add_argument("--xbox05", help="the MVP Baseball 2005 Xbox disc, with --gamecube the 2005 GameCube disc")
    a.add_argument("--dir", default=game_dir())
    o = a.parse_args()
    if not (o.xbox or o.gamecube or o.ps2 or o.xbox05):
        return gui(o.dir)
    try:
        run(o.dir, o.xbox, o.gamecube, o.ps2, xbox05=o.xbox05)
    except discs.DiscError as e:
        raise SystemExit(f"stopped: {e}")


if __name__ == "__main__":
    main()
