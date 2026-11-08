"""Desktop shortcuts, only when asked for (Settings tab): "MVP 06 Plus" for the game, "MVP 06 Plus Launcher" for the
Launcher. Made with Windows' own shortcut maker (WScript.Shell, through PowerShell); removed by deleting the .lnk."""
import os
import subprocess
import sys

GAME_NAME = "MVP 06 Plus"
TOOLS_NAME = "MVP 06 Plus Launcher"


def desktop():
    """The desktop folder (OneDrive's, when Windows keeps it there)."""
    import ctypes
    from ctypes import wintypes
    buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0:  # CSIDL_DESKTOPDIRECTORY
        return buf.value
    return os.path.join(os.path.expanduser("~"), "Desktop")


def path(name):
    return os.path.join(desktop(), name + ".lnk")


def exists(name):
    return os.name == "nt" and os.path.isfile(path(name))


def tools_exe():
    """The Launcher's own exe, or None when it's run from source."""
    return sys.executable if getattr(sys, "frozen", False) else None


def create(name, target, icon=None, description=""):
    if os.name != "nt":
        raise OSError("desktop shortcuts are made on Windows")
    env = dict(os.environ, MVP_LNK=path(name), MVP_TARGET=target, MVP_DIR=os.path.dirname(target),
               MVP_ICON=(icon + ",0") if icon and os.path.isfile(icon) else target + ",0", MVP_DESC=description)
    script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:MVP_LNK); "
              "$s.TargetPath = $env:MVP_TARGET; $s.WorkingDirectory = $env:MVP_DIR; "
              "$s.IconLocation = $env:MVP_ICON; $s.Description = $env:MVP_DESC; $s.Save()")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                       capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode or not os.path.isfile(path(name)):
        raise OSError((r.stderr or r.stdout or "the shortcut wasn't made").strip()[-300:])


def remove(name):
    if os.path.isfile(path(name)):
        os.remove(path(name))
