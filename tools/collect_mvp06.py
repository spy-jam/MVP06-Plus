#!/usr/bin/env python3
"""Collect the MVP 06 files the controls mod needs, from your own extracted discs, into one small zip.

usage: python collect_mvp06.py <Xbox game folder> <PS2 disc folder> [output.zip]
  e.g. python collect_mvp06.py "C:\\MVP06\\assets" "D:\\" mvp06-files.zip
The Xbox folder is the one holding default.xbe; the PS2 folder is the disc's root (the one holding SLUS_213.67
and DATA). Either can be left out by passing - instead. Needs only Python 3.

It looks inside every .big archive under the front end folders (and igshapes) of both discs and takes only
the ones that matter for controls:
  - layouts (.fel) where the platforms show different things (help bars, pads, button prompts)
  - picture sheets (.xsh/.ssh) with button or controller pictures in them
  - the first loading screens (load0-load9.big), the ones that showed the controller diagrams on MVP 05
  - the base runner / fielder diamonds (igshapes/igcrsr*)
Everything else stays behind; inventory.txt in the zip lists every archive and what is in it, so a file that
turns out to matter can be asked for by name.
"""
import os, sys, struct, zipfile, io

# ---- EA archives ----------------------------------------------------------------------------------------------

def read_big(data):
    if data[:4] not in (b'BIGF', b'BIG4'): return []
    n, _ = struct.unpack_from('>II', data, 8); o = 16; out = []
    for _ in range(n):
        off, sz = struct.unpack_from('>II', data, o); o += 8
        e = data.index(b'\0', o); name = data[o:e].decode('latin1'); o = e + 1
        out.append((name, data[off:off + sz]))
    return out

def unrefpack(src):
    """EA RefPack (0x10FB / 0x11FB)"""
    if len(src) < 5 or src[1] != 0xFB: return src
    i = 2 + (3 if src[0] & 0x80 == 0 else 4)
    if src[0] & 0x01: i += 3 if src[0] & 0x80 == 0 else 4
    out = bytearray()
    while i < len(src):
        b0 = src[i]
        if b0 < 0x80:
            b1 = src[i + 1]; i += 2
            lit, n, d = b0 & 3, ((b0 >> 2) & 7) + 3, ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1, b2 = src[i + 1], src[i + 2]; i += 3
            lit, n, d = b1 >> 6, (b0 & 0x3F) + 4, ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1, b2, b3 = src[i + 1], src[i + 2], src[i + 3]; i += 4
            lit, n, d = b0 & 3, ((b0 & 0x0C) << 6) + b3 + 5, ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            lit = ((b0 & 0x1F) << 2) + 4; out += src[i + 1:i + 1 + lit]; i += 1 + lit; continue
        else:
            lit = b0 & 3; out += src[i + 1:i + 1 + lit]; break
        out += src[i:i + lit]; i += lit
        for _ in range(n): out.append(out[-d])
    return bytes(out)

def unpack(b):
    return unrefpack(b) if len(b) > 2 and b[1] == 0xFB and b[0] in (0x10, 0x11, 0x90, 0x91) else b

# ---- what counts ----------------------------------------------------------------------------------------------

PICTURES = (b'bu00', b'bq00', b'gpad', b'gpdx', b'ps00', b'pt00', b'rep1')  # help buttons, pads, pitch select, replay

def platform_layout(t):
    """a layout with an element the PS2 and the Xbox (or the GameCube) show differently"""
    if not t.startswith(b'VR:'): return False
    for l in t.split(b'\n'):
        f = l.strip().split(b',')
        if len(f) > 10 and all(x in (b'0', b'1') for x in f[7:11]) and len(set(f[8:11])) > 1:
            return True
    return False

def why(name, data):
    """the reason this archive is wanted, or None"""
    low = name.lower()
    if 'igcrsr' in low: return 'base runner diamonds'
    base = os.path.basename(low)
    if base.startswith('load') and base[4:-4].isdigit() and low.endswith('.big'):
        # the controller diagrams were load0-load7 on MVP 05; the rest are tips, listed in the inventory only
        return 'loading screen' if int(base[4:-4]) < 10 else None
    reasons = set()
    for n, b in read_big(data):
        u = unpack(b); nl = n.lower()
        if nl.endswith('.fel') and platform_layout(u): reasons.add('layouts')
        if nl.endswith(('.xsh', '.ssh', '.gsh')) and any(p in u for p in PICTURES): reasons.add('button pictures')
    return ', '.join(sorted(reasons)) or None

# ---- walking the discs ----------------------------------------------------------------------------------------

def archives(root):
    """every .big under a front end folder, and igshapes' igcrsr files, relative to root"""
    for d, _, files in os.walk(root):
        rel_d = os.path.relpath(d, root).replace('\\', '/').lower()
        for f in files:
            fl = f.lower()
            if ('frontend' in rel_d and fl.endswith('.big')) or ('igshapes' in rel_d and fl.startswith('igcrsr')):
                yield os.path.join(d, f), os.path.relpath(os.path.join(d, f), root).replace('\\', '/')

def collect(root, tag, z, inv):
    if root == '-': return 0
    if not os.path.isdir(root): raise SystemExit('not a folder: %s' % root)
    total = 0; found = 0
    for path, rel in sorted(archives(root), key=lambda x: x[1].lower()):
        found += 1
        data = open(path, 'rb').read()
        reason = why(rel, data)
        inv.append('%-5s %-40s %10d  %s' % (tag, rel, len(data), ('TAKEN: ' + reason) if reason else 'left'))
        for n, b in read_big(data):
            inv.append('        %-36s %9d' % (n, len(b)))
        if reason:
            z.write(path, tag + '/' + rel); total += len(data)
            print('  %-5s %-40s %6d KB  (%s)' % (tag, rel, len(data) // 1024, reason))
    if not found: print('  %s: no frontend folder found under %s' % (tag, root))
    return total

def main():
    if len(sys.argv) not in (3, 4): raise SystemExit(__doc__)
    xb, ps = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) == 4 else 'mvp06-files.zip'
    inv = ['MVP 06 front end archives: tag, path, size, taken or left; then the files inside each', '']
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        print('collecting:')
        total = collect(xb, 'xbox', z, inv) + collect(ps, 'ps2', z, inv)
        z.writestr('inventory.txt', '\n'.join(inv) + '\n')
    print('wrote %s: %d KB of archives before compression (%d KB zipped)' % (out, total // 1024, os.path.getsize(out) // 1024))

if __name__ == '__main__':
    main()
