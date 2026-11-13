"""mvp06-settings.toml beside the exe: read, and single values changed in place (comments and the rest of the
file kept as they are). The game reads it when it starts and never writes it."""
import os
import re

FILE = "mvp06-settings.toml"

# what the Settings tab offers, with the shipped file's values as the defaults
DISPLAY_MODES = ["windowed", "borderless", "fullscreen"]
DEFAULTS = {"display_mode": "fullscreen", "width": 0, "height": 0, "render_percent": 100, "fps_cap": 60,
            "vsync": True, "low_latency": False, "anisotropic_filtering": 16, "xbox_720p": True}


def _parse(v):
    v = v.split("#", 1)[0].strip() if not v.strip().startswith('"') else v.strip()
    if v.startswith('"'):
        return v[1:v.index('"', 1)]
    if v in ("true", "false"):
        return v == "true"
    try:
        return int(v)
    except ValueError:
        return v


def _fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return '"' + str(v).replace('"', "") + '"'


def read(root):
    out = {}
    try:
        with open(os.path.join(root, FILE), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*([A-Za-z0-9_]+)\s*=\s*(.*)$", line)
                if m:
                    out[m.group(1)] = _parse(m.group(2))
    except OSError:
        pass
    return out


def write(root, changes):
    """Each key's line given its new value (its comment after the value kept), or added at the end."""
    p = os.path.join(root, FILE)
    try:
        with open(p, encoding="utf-8", newline="") as f:
            text = f.read()
    except OSError:
        text = ""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    left = dict(changes)
    for i, line in enumerate(lines):
        m = re.match(r"(\s*)([A-Za-z0-9_]+)(\s*=\s*)(.*)$", line)
        if m and m.group(2) in left:
            rest = m.group(4).strip()
            if rest.startswith('"') and '"' in rest[1:]:
                rest = rest[rest.index('"', 1) + 1:]  # a quoted value may hold a #: its comment is after it
            comment = "  #" + rest.split("#", 1)[1] if "#" in rest else ""
            lines[i] = m.group(1) + m.group(2) + m.group(3) + _fmt(left.pop(m.group(2))) + comment
    for k, v in left.items():
        lines.append(f"{k} = {_fmt(v)}")
    tmp = p + ".part"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(nl.join(lines) + nl)
    os.replace(tmp, p)
