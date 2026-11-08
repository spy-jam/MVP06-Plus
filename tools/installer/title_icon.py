"""The game's icon, made from your own Xbox disc: default.xbe's title image (the $$XTIMAGE section, an XPR0 texture,
128 x 128 DXT1 on the MVP games), as mvp06.ico beside the exe. The game's window loads it from there
(app::AppIcon). On Windows it also goes into MVP06.exe itself, for Explorer, when that can be done.
"""
import io
import os
import struct

ICO = "mvp06.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]


class IconError(Exception):
    pass


def title_image_bytes(xbe):
    base = struct.unpack_from("<I", xbe, 0x104)[0]
    n, sh = struct.unpack_from("<I", xbe, 0x11C)[0], struct.unpack_from("<I", xbe, 0x120)[0] - base
    for i in range(n):
        o = sh + i * 0x38
        _, _, _, raw, size, name = struct.unpack_from("<IIIIII", xbe, o)
        if xbe[name - base:name - base + 10] == b"$$XTIMAGE\0":
            return xbe[raw:raw + size]
    raise IconError("default.xbe has no title image")


def _c565(c):
    return ((c >> 11 & 31) * 255 // 31, (c >> 5 & 63) * 255 // 63, (c & 31) * 255 // 31)


def _dxt_colors(data, o, alpha_block):
    c0, c1 = struct.unpack_from("<HH", data, o)
    a, b = _c565(c0), _c565(c1)
    if c0 > c1 or alpha_block:
        return [a + (255,), b + (255,), tuple((2 * a[k] + b[k]) // 3 for k in range(3)) + (255,),
                tuple((a[k] + 2 * b[k]) // 3 for k in range(3)) + (255,)]
    return [a + (255,), b + (255,), tuple((a[k] + b[k]) // 2 for k in range(3)) + (255,), (0, 0, 0, 0)]


def _decode(fmt, data, w, h):
    from PIL import Image
    im = Image.new("RGBA", (w, h))
    px = im.load()
    if fmt in (0x0C, 0x0E, 0x0F):  # DXT1, DXT2/3, DXT4/5 (blocks, not swizzled)
        step = 8 if fmt == 0x0C else 16
        o = 0
        for by in range(0, h, 4):
            for bx in range(0, w, 4):
                alpha = [255] * 16
                if fmt == 0x0E:
                    bits = int.from_bytes(data[o:o + 8], "little")
                    alpha = [(bits >> (4 * j) & 15) * 17 for j in range(16)]
                elif fmt == 0x0F:
                    a0, a1 = data[o], data[o + 1]
                    bits = int.from_bytes(data[o + 2:o + 8], "little")
                    table = [a0, a1] + ([((6 - k) * a0 + (k + 1) * a1) // 7 for k in range(6)] if a0 > a1 else
                                        [((4 - k) * a0 + (k + 1) * a1) // 5 for k in range(4)] + [0, 255])
                    alpha = [table[bits >> (3 * j) & 7] for j in range(16)]
                c = o + (step - 8)
                cols = _dxt_colors(data, c, fmt != 0x0C)
                idx = struct.unpack_from("<I", data, c + 4)[0]
                for j in range(16):
                    r, g, b_, a = cols[idx >> (2 * j) & 3]
                    px[bx + j % 4, by + j // 4] = (r, g, b_, a if fmt == 0x0C else alpha[j])
                o += step
        return im
    if fmt in (0x06, 0x12):  # A8R8G8B8: swizzled (Morton order), or linear
        for y in range(h):
            for x in range(w):
                if fmt == 0x12:
                    i = y * w + x
                else:
                    i, bit, xx, yy = 0, 0, x, y
                    mx, my = w, h
                    while mx > 1 or my > 1:
                        if mx > 1:
                            i |= (xx & 1) << bit
                            bit += 1
                            xx >>= 1
                            mx >>= 1
                        if my > 1:
                            i |= (yy & 1) << bit
                            bit += 1
                            yy >>= 1
                            my >>= 1
                b_, g, r, a = data[4 * i:4 * i + 4]
                px[x, y] = (r, g, b_, a)
        return im
    raise IconError(f"the title image's format ({fmt:#x}) isn't one this reads")


def title_image(xbe):
    x = title_image_bytes(xbe)
    if x[:4] != b"XPR0":
        raise IconError("the title image isn't an XPR texture")
    header = struct.unpack_from("<I", x, 8)[0]
    data_off, fmtword = struct.unpack_from("<I", x, 16)[0], struct.unpack_from("<I", x, 24)[0]
    fmt, w, h = fmtword >> 8 & 0xFF, 1 << (fmtword >> 20 & 15), 1 << (fmtword >> 24 & 15)
    return _decode(fmt, x[header + data_off:], w, h)


def make_ico(xbe_path, ico_path):
    with open(xbe_path, "rb") as f:
        im = title_image(f.read())
    from PIL import Image
    big = im.resize((256, 256), Image.LANCZOS)
    tmp = ico_path + ".part"
    big.save(tmp, format="ICO", sizes=[(s, s) for s in SIZES])
    os.replace(tmp, ico_path)


def embed(exe, ico_path):
    """The .ico as MVP06.exe's icon (group 1, as the game loads it), with Windows' resource functions."""
    import ctypes
    from ctypes import wintypes
    with open(ico_path, "rb") as f:
        ico = f.read()
    _, typ, count = struct.unpack_from("<HHH", ico, 0)
    if typ != 1 or not count:
        raise IconError("not an icon file")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.BeginUpdateResourceW.restype = wintypes.HANDLE
    k.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    k.UpdateResourceW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wintypes.WORD, ctypes.c_void_p,
                                  wintypes.DWORD]
    k.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    h = k.BeginUpdateResourceW(exe, False)
    if not h:
        raise IconError(f"MVP06.exe can't be changed (error {ctypes.get_last_error()})")
    group = struct.pack("<HHH", 0, 1, count)
    ok = True
    for i in range(count):
        w, hh, colors, _, planes, bits, size, off = struct.unpack_from("<BBBBHHII", ico, 6 + 16 * i)
        img = ico[off:off + size]
        buf = ctypes.create_string_buffer(img, len(img))
        ok &= bool(k.UpdateResourceW(h, 3, i + 1, 0, buf, len(img)))  # RT_ICON
        group += struct.pack("<BBBBHHIH", w, hh, colors, 0, planes, bits, size, i + 1)
    gbuf = ctypes.create_string_buffer(group, len(group))
    ok &= bool(k.UpdateResourceW(h, 14, 1, 0, gbuf, len(group)))  # RT_GROUP_ICON
    if not k.EndUpdateResourceW(h, not ok) or not ok:
        raise IconError(f"MVP06.exe's icon couldn't be set (error {ctypes.get_last_error()})")


def ensure(root, say=None):
    """mvp06.ico from assets/default.xbe if it isn't there yet, and into MVP06.exe on Windows. Quiet unless said."""
    xbe = os.path.join(root, "assets", "default.xbe")
    ico = os.path.join(root, ICO)
    if not os.path.isfile(xbe):
        return False
    try:
        if not os.path.isfile(ico):
            make_ico(xbe, ico)
            exe = os.path.join(root, "MVP06.exe")
            if os.name == "nt" and os.path.isfile(exe):
                try:
                    embed(exe, ico)
                except Exception as e:  # the window still has it, from the .ico
                    if say:
                        say(f"(the icon is beside the game, but not in MVP06.exe: {e})")
            if say:
                say("Made the game's icon from your Xbox disc.")
        return True
    except Exception as e:
        if say:
            say(f"(no icon: {e})")
        return False
