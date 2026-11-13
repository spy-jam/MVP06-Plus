"""MVP 06 NCAA Baseball saves (the game's own, in hdd beside MVP06.exe): listed for the Launcher's Import a save.

  hdd/E/UDATA/4541008d/<12-hex folder>/   data.dat, SaveMeta.xbx (UTF-16LE with BOM: "Name=<name> (<type>)"),
                                          saveimage.xbx
"""
import datetime
import os
import re
import shutil
import subprocess

TITLE = "4541008d"


class SaveError(Exception):
    pass


def udata(root):
    return os.path.join(root, "hdd", "E", "UDATA", TITLE)


def game_running():
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq MVP06.exe", "/NH"], capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "mvp06.exe" in r.stdout.lower()
    except OSError:
        return False


def savemeta(folder):
    """(name, type) from the save's SaveMeta.xbx: 'Name=Matched (Dynasty)' -> ('Matched', 'Dynasty')."""
    try:
        with open(os.path.join(folder, "SaveMeta.xbx"), "rb") as f:
            b = f.read()
        t = b.decode("utf-16-le" if b[:2] == b"\xff\xfe" else "latin-1").lstrip("﻿")
        for line in t.splitlines():
            if line.startswith("Name="):
                v = line[5:].strip()
                m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", v)
                return (m.group(1), m.group(2)) if m else (v, "")
    except OSError:
        pass
    return "", ""


def list_saves(root):
    """[{folder, id, name, type, size, when}] newest first."""
    out = []
    base = udata(root)
    if not os.path.isdir(base):
        return out
    for d in os.listdir(base):
        folder = os.path.join(base, d)
        dat = os.path.join(folder, "data.dat")
        if not os.path.isfile(dat):
            continue
        name, typ = savemeta(folder)
        out.append(dict(folder=folder, id=d, name=name or d, type=typ or "?", size=os.path.getsize(dat),
                        when=datetime.datetime.fromtimestamp(os.path.getmtime(dat))))
    return sorted(out, key=lambda s: s["when"], reverse=True)


def backup_folder(root, folder, why):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H.%M.%S")
    dest = os.path.join(root, "save backups", f"{stamp} before {why}", os.path.basename(folder))
    shutil.copytree(folder, dest)
    return dest
