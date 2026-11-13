"""An older MVP06-Plus (Beta 1 has no updater), or Mad Dog's MVP06, brought into this new folder: its installed game,
saves and the rest that's the player's, copied (the old folder keeps working) or moved (no extra space, and quick on
the same drive; the old folder no longer works). The program files are this folder's own, and the settings are this
release's file with the old one's values in it.
"""
import os
import shutil

import discs
import settings as ST

# what's the player's: the game installed from the disc, saves, backups, button art, the shader cache, the icon from
# the disc, the Launcher's own choices
CARRY = ("assets", "hdd", "save backups", "gc_icons", "ps2_icons", "shader_cache", "mvp06.ico",
         "mvp06-plus-launcher.json")


class CarryError(Exception):
    pass


def check(old, root):
    """The old folder's checked: an MVP 06 install that isn't this folder. Its size in bytes."""
    if not old or os.path.normcase(os.path.realpath(old)) == os.path.normcase(os.path.realpath(root)):
        raise CarryError("pick the folder of your older MVP06-Plus, not this one")
    xbe = os.path.join(old, "assets", "default.xbe")
    if not os.path.isfile(xbe):
        raise CarryError("that folder has no installed game (no assets\\default.xbe): pick the folder with "
                         "MVP06.exe in it")
    try:
        with open(xbe, "rb") as f:
            tid, name = discs.xbe_title(f.read())
    except (OSError, discs.DiscError) as e:
        raise CarryError(f"the game in that folder can't be read ({e})")
    if tid != discs.XBOX_TITLE:
        raise CarryError(f"that folder holds {name or 'another game'}, not MVP 06 NCAA Baseball")
    if os.path.isfile(os.path.join(root, "assets", "default.xbe")):
        raise CarryError("this folder has a game installed already")
    total = 0
    for name in CARRY:
        p = os.path.join(old, *name.split("/"))
        if os.path.isfile(p):
            total += os.path.getsize(p)
        for d, _, fs in os.walk(p):
            total += sum(os.path.getsize(os.path.join(d, f)) for f in fs)
    return total


def _files(old):
    for name in CARRY:
        p = os.path.join(old, *name.split("/"))
        if os.path.isfile(p):
            yield name
        elif os.path.isdir(p):
            for d, _, fs in os.walk(p):
                for f in fs:
                    yield os.path.relpath(os.path.join(d, f), old).replace(os.sep, "/")


def bring_over(old, root, move=False, say=print, progress=None):
    """The old folder's game, saves and the rest into root (copied, or moved), then its settings. Returns the count
    of files brought over."""
    check(old, root)
    files = list(_files(old))
    if not move:
        need = check(old, root)
        if shutil.disk_usage(root).free < need + 200 * 2**20:
            raise CarryError(f"copying needs about {need / 2**30:.1f} GB free on this drive: free some space, or "
                             "choose Move")
    say(f"{'Moving' if move else 'Copying'} {len(files)} files from {old}...")
    for i, rel in enumerate(files):
        src = os.path.join(old, *rel.split("/"))
        dst = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if move:
            shutil.move(src, dst)
        else:
            shutil.copy2(src, dst)
        if progress and (i % 50 == 0 or i == len(files) - 1):
            progress((i + 1) / len(files))
    if move:  # the folders it left empty
        for name in CARRY:
            p = os.path.join(old, *name.split("/"))
            for d, _, _ in sorted(os.walk(p), key=lambda x: -len(x[0])):
                try:
                    os.rmdir(d)
                except OSError:
                    pass
    # the settings: this release's file (its new options, its notes) with the old one's values
    mine = ST.read(old)
    if mine:
        ST.write(root, mine)
        say(f"Settings brought over ({len(mine)}).")
    say(f"{'Moved' if move else 'Copied'} {len(files)} files.")
    return len(files)
