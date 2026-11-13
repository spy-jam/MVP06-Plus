"""MVP 06 NCAA Baseball dynasty saves into your Xbox dynasty saves: from the PS2 (a .psu, the .sav from one, or a
PCSX2 memory card) or from another Xbox.

  is_ps2(data) / read_ps2(data)      a PS2 dynasty, checked: {name, payload}
  read_xbox(data)                    an Xbox dynasty, checked: its payload
  ps2_to_xbox(src, xbox_dynasty)     the PS2 dynasty as an Xbox data.dat, built on one of your own Xbox dynasties
  xbox_to_xbox(data, xbox_dynasty)   another Xbox's dynasty in yours: the same format, signed again

The PS2 <-> Xbox conversion is spy_jam's MVP 06 converter (mvp06/lib/m06.py, its notes in mvp06/NOTES.md). It was
worked out on fresh dynasties; a dynasty already into its season can hold data in the one place whose layout
differs and isn't known yet, and is refused rather than guessed.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(getattr(sys, "_MEIPASS", HERE), "mvp06", "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import m06  # noqa: E402
import m06files as F  # noqa: E402

PS2_HEAD = 0xC8
PS2_SAV_SIZE = PS2_HEAD + m06.PS2_PAYLOAD_LEN
XB_SIZE = 0x108 + m06.XB_PAYLOAD_LEN  # an Xbox dynasty's data.dat


class DynastyError(Exception):
    pass


def _check(ok, why):
    if not ok:
        raise DynastyError(why)


def _u32(b, p):
    return struct.unpack_from("<I", b, p)[0]


def _sav_from(data):
    """The PS2 dynasty .sav in data (itself, or the one in a .psu), and the .psu's icons if any."""
    if len(data) == PS2_SAV_SIZE:
        return data, None
    try:
        ents = [e for e in F.psu_parse(data) if e["data_off"] is not None]
    except (struct.error, ValueError):
        ents = []
    savs = [e for e in ents if e["size"] == PS2_SAV_SIZE]
    _check(savs, "not an MVP 06 PS2 dynasty (.psu, or a .sav from one)")
    e = savs[0]
    return data[e["data_off"]:e["data_off"] + e["size"]], (F.psu_file(data, "title.ico"), F.psu_file(data, "icon.sys"))


def is_ps2(data):
    try:
        _sav_from(bytes(data))
        return True
    except DynastyError:
        return False


def read_ps2(data):
    data = bytes(data)
    sav, icons = _sav_from(data)
    hl, pl = struct.unpack_from("<II", sav, 0x10)
    _check(hl == PS2_HEAD and pl == m06.PS2_PAYLOAD_LEN, "not an MVP 06 PS2 dynasty this reads")
    _check(_u32(sav, 0) == F.ea_crc(sav[0x10:hl]) and _u32(sav, 4) == F.ea_crc(sav[hl:hl + pl]),
           "the PS2 save's checksums don't match: it's damaged or edited")
    if icons and all(icons):
        _check(_u32(sav, 8) == F.ea_crc(icons[0]) and _u32(sav, 12) == F.ea_crc(icons[1]),
               "the .psu's save icon doesn't match its save")
    payload = sav[hl:hl + pl]
    try:
        m06.markers(payload)
    except m06.Unsupported as e:
        raise DynastyError(f"not an MVP 06 dynasty this reads ({e})")
    name = sav[0x28:0x48].decode("utf-16-le", "replace").split("\0")[0]
    return dict(name=name, payload=payload)


def read_xbox(data):
    data = bytes(data)
    _check(len(data) == XB_SIZE, "not an MVP 06 Xbox dynasty save (data.dat)")
    _check(F.xb_check(data), "the Xbox save's signatures don't match: it's damaged or edited")
    payload = F.xb_payload(data)
    _check(len(payload) == m06.XB_PAYLOAD_LEN, "not an MVP 06 Xbox dynasty this reads")
    try:
        m06.markers(payload)
    except m06.Unsupported as e:
        raise DynastyError(f"not an MVP 06 dynasty this reads ({e})")
    return payload


def ps2_to_xbox(src, xbox_dynasty):
    """src: read_ps2's result (or PS2 bytes). The Xbox data.dat, built on xbox_dynasty (keeping its name)."""
    if not isinstance(src, dict):
        src = read_ps2(src)
    mine = read_xbox(xbox_dynasty)
    try:
        payload = m06.p2x(src["payload"], mine)
    except m06.Unsupported as e:
        raise DynastyError(f"this dynasty can't be converted yet ({e})")
    out = F.xb_build(bytes(xbox_dynasty), payload)
    _check(F.xb_check(out), "the converted save failed its signature check")
    return out


def xbox_to_xbox(data, xbox_dynasty):
    """Another Xbox's MVP 06 dynasty in one of yours: its dynasty unchanged, under your save's name, signed again."""
    payload = read_xbox(data)
    read_xbox(xbox_dynasty)
    out = F.xb_build(bytes(xbox_dynasty), payload)
    _check(F.xb_check(out), "the save failed its signature check")
    return out
