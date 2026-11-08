"""PS2 SHPS (.ssh) pictures, decode only.

Image types used by MVP Baseball 2005 (PS2):
  0x01  4-bit indexed            0x02  8-bit indexed            0x05  32-bit RGBA
  0x0E  "GST 4x2 / 2-bit": an 8-bit indexed picture stored as a base index per 4x2 pixel block plus a 2-bit
        detail per pixel (index = base + detail), both in the GS's swizzled order when the header has 0x2000.
Palettes are attachment 0x21 (32-bit RGBA, alpha 0..0x80); with 0x2000 in their header they are in the GS's CSM1 order.
"""
import struct
from PIL import Image


def _blocks(u, off):
    res = []; o = off
    while True:
        t = u[o]; nxt = int.from_bytes(u[o + 1:o + 4], 'little')
        res.append((o, t, nxt))
        if nxt == 0 or o + nxt >= len(u) or len(res) > 8: break
        o += nxt
    return res


def _palette(u, off):
    for o, t, n in _blocks(u, off)[1:]:
        if t == 0x21:
            cnt = struct.unpack_from('<H', u, o + 4)[0] * struct.unpack_from('<H', u, o + 6)[0]
            raw = u[o + 16:o + 16 + 4 * cnt]
            pal = [tuple(raw[4 * i:4 * i + 4]) for i in range(cnt)]
            if struct.unpack_from('<H', u, o + 12)[0] & 0x2000 and cnt > 16:
                # CSM1: within each 32 entries, 8-15 and 16-23 trade places
                pal += [(0, 0, 0, 0)] * (256 - cnt)
                pal = [pal[(i & ~0x18) | ((i & 8) << 1) | ((i & 16) >> 1)] for i in range(256)]
            return [(r, g, b, min(255, a * 2)) for r, g, b, a in pal]
    return None


def _swz(x, y):
    """the GS 8-bit block swizzle: (x, y) inside a 16-wide, 4-high group -> position in that group's stream"""
    x1 = ((x & ~0x0F) >> 1) + ((x & 0x07) ^ ((y & 0x02) << 1) ^ (y & 0x04))
    y1 = ((y & ~0x03) >> 1) + (y & 0x01)
    z1 = ((x & 0x08) >> 2) + ((y & 0x02) >> 1)
    return x1, y1, z1


def _gst422(data, w, h, swizzled):
    bw, bh = 4, 2
    base_n = (w // bw) * (h // bh)
    base = data[:base_n]
    doff = (base_n + 15) & ~15
    det = data[doff:doff + w * h // 4]
    if swizzled:
        bwid = w // bw
        nb = bytearray(base_n)
        for y in range(h // bh):
            for x in range(bwid):
                xx, yy = x * bw, y * bh
                x1, y1, z1 = _swz(xx, yy)
                o = 32 * ((y1 // bh) * bwid // 2 + x1 // bw) + 8 * z1
                nb[y * bwid + x] = base[o >> 3]
        base = bytes(nb)
        nd = bytearray(len(det)); k = 0
        for y in range(h):
            for x in range(0, w, 4):
                v = 0
                for xf in (3, 2, 1, 0):
                    x1, y1, z1 = _swz(x + xf, y)
                    x2, y2, z2 = _swz(x1, y1)
                    o = 32 * (y2 * w // 4 + x2) + 8 * z2 + 2 * z1
                    v = (v << 2) | ((det[o >> 3] >> (o & 7)) & 3)
                nd[k] = v; k += 1
        det = bytes(nd)
    out = bytearray(w * h); k = 0; o = 0
    for y in range(h):
        bo = (w // bw) * (y // bh)
        for x in range(0, w, 4):
            d = det[k]; k += 1; b = base[bo]; bo += 1
            for i in range(4):
                out[o] = (b + ((d >> (2 * i)) & 3)) & 0xFF; o += 1
    return bytes(out)


def decode_ps2(u, off):
    t = u[off]
    w, h = struct.unpack_from('<HH', u, off + 4)
    flags = struct.unpack_from('<H', u, off + 12)[0]
    swizzled = bool(flags & 0x2000)
    data = u[off + 16:]
    img = Image.new('RGBA', (w, h))
    if t == 0x05:
        img.frombytes(bytes(data[:w * h * 4]))
        r, g, b, a = img.split()
        return Image.merge('RGBA', (r, g, b, a.point(lambda v: min(255, v * 2))))
    pal = _palette(u, off)
    if t == 0x02:
        idx = bytes(data[:w * h])
        if swizzled: raise ValueError('swizzled 8-bit picture')
    elif t == 0x01:
        raw = data[:w * h // 2]
        idx = bytes(v for b in raw for v in (b & 15, b >> 4))
    elif t == 0x0E:
        idx = _gst422(bytes(data), w, h, swizzled)
    else:
        raise ValueError('ps2 type %x' % t)
    img.putdata([pal[i] if i < len(pal) else (0, 0, 0, 0) for i in idx])
    return img
