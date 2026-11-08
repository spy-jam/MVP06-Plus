#!/usr/bin/env python3
"""Build ps2_icons for MVP 06 NCAA: the Xbox game's button art redrawn with the PS2 release's (SLUS_213.67).

usage: python make_ps2_icons06.py <Xbox data folder> <PS2 disc DATA folder> <output ps2_icons folder>
  e.g. python make_ps2_icons06.py "C:\\MVP06\\assets\\data" "D:\\DATA" ps2_icons
Needs Python 3, Pillow 11.2 or later and numpy (pip install pillow numpy). Nothing from either disc is stored here.

As for MVP 2005 (make_ps2_icons.py, whose helpers this uses), with MVP 06's files:
  data/frontend/shared.big   helpbuts.xsh: the help icons and controller pictures by name (gpco, the co-op pad, too);
                             the PS2 sheet's green anchor dots cleared and the CPU outline fitted under the pad
  data/frontend/igonly.big   ingameov.xsh: pitch select (ps00-ps03, PICK, STAMINA) and the PS2's button pictures
                             bu10-bu21 from its pitchslc sheet; replay.xsh: the replay panel (rep1)
  data/frontend/coopov.big   the co-op games' copy of igonly's two sheets, the same way
  data/igshapes/igcrsr.xsh   the base runner and fielder diamonds: Square, Triangle, Circle
  data/frontend/frontend.big, ingame.big, minigame.big, cooplay.big, cbplay.big, apt.big: the layouts (.fel), the
                             same files on both releases, every screen as the PS2 draws it (as_platform in
                             make_icons.py), strict: a PS2 group goes in an Xbox group's place only when it holds all
                             of the Xbox group's groups (the game finds them by name)
MVP 06 has no load*.big loading screens with controllers; igcrsr1/igcrsr9 are pitch meter pieces, left as they are.
"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
sys.path.insert(0, os.path.join(here, '..', 'gc_layout'))
from PIL import Image
from iconlib.big import read_big
from iconlib.refpack import unrefpack
from iconlib import pack
from iconlib.shp import entries, decode_xbox, encode_xbox_into
from iconlib.ps2 import decode_ps2
import make_icons
from make_icons import sheet, records, unpack, layouts
from make_ps2_icons import clean_markers, fit_outline, paste_into, ps2_sheet, find

LAYOUT_ARCHIVES = ('frontend.big', 'ingame.big', 'minigame.big', 'cooplay.big', 'cbplay.big', 'apt.big')


def help_icons(xb, ps):
    ph = ps2_sheet(ps, 'shared.big', 'helpbuts.ssh')
    P = {n: decode_ps2(ph, o) for n, o in entries(ph)[0]}
    for n in ('gpad', 'gpa2', 'gpco'):
        if n in P: P[n] = clean_markers(P[n])
    P['gpdx'] = fit_outline(clean_markers(P['gpdx'], recolour=False), P['gpad'])
    xh = sheet(os.path.join(xb, 'frontend', 'shared.big'), 'helpbuts.xsh')
    for n, off in entries(xh)[0]:
        if n not in P:
            print('  helpbuts: no PS2 picture for %s, the Xbox one stays' % n)
            continue
        xi = decode_xbox(xh, off)
        g = P[n]
        if g.size == xi.size:
            new = g.copy()
        elif n in ('gpad', 'gpa2', 'gpdx', 'gpco'):
            new = g.resize(xi.size, Image.LANCZOS)
        else:
            new = Image.new('RGBA', xi.size, (0, 0, 0, 0))
            new.alpha_composite(g, ((xi.width - g.width) // 2, (xi.height - g.height) // 2))
        xh = encode_xbox_into(xh, off, new)
    return xh


def overlay_sheets(xb, ps, archive):
    """pitch select and the replay panel in one of the overlay archives (igonly.big, coopov.big)"""
    xi_raw = sheet(os.path.join(xb, 'frontend', archive), 'ingameov.xsh')
    off = entries(xi_raw)[0][0][1]
    a = decode_xbox(xi_raw, off)
    rec = records(xi_raw, off, '<')
    pp = ps2_sheet(ps, archive, 'pitchslc.ssh')
    PP = {n: decode_ps2(pp, o) for n, o in entries(pp)[0]}
    want = ['ps00', 'ps01', 'ps02', 'ps03', 'pick', 'stam'] + ['bu%02d' % k for k in range(10, 22)]
    done = [n for n in want if n in rec and n in PP]
    for n in done: paste_into(a, rec[n], PP[n])
    print('  %s ingameov: %s' % (archive, ' '.join(done)))
    xi_new = encode_xbox_into(xi_raw, off, a)
    xr_raw = sheet(os.path.join(xb, 'frontend', archive), 'replay.xsh')
    roff = entries(xr_raw)[0][0][1]
    r = decode_xbox(xr_raw, roff)
    pr = ps2_sheet(ps, archive, 'replay.ssh')
    paste_into(r, records(xr_raw, roff, '<')['rep1'], decode_ps2(pr, dict(entries(pr)[0])['rep1']))
    xr_new = encode_xbox_into(xr_raw, roff, r)
    return {'ingameov.xsh': xi_new, 'replay.xsh': xr_new}


def diamonds(xb, ps):
    cr_raw = open(os.path.join(xb, 'igshapes', 'igcrsr.xsh'), 'rb').read()
    pc = open(find(ps, 'igshapes', 'igcrsr.ssh'), 'rb').read()
    coff = entries(cr_raw)[0][0][1]
    c = decode_xbox(cr_raw, coff)
    crec = records(cr_raw, coff, '<')
    pcoff = entries(pc)[0][0][1]
    g = decode_ps2(pc, pcoff)
    prec = records(pc, pcoff, '<')
    for xn, pn in (('PXBX', 'PSQR'), ('PXBY', 'PTRI'), ('PXBB', 'PCIR')):
        x, y, w, h = prec[pn]
        paste_into(c, crec[xn], g.crop((x, y, x + w, y + h)))
    return encode_xbox_into(cr_raw, coff, c)


def main():
    if len(sys.argv) != 4: raise SystemExit(__doc__)
    xb, ps, out = sys.argv[1:]
    rep = {'shared.big': {'helpbuts.xsh': help_icons(xb, ps)}}
    for archive in ('igonly.big', 'coopov.big'):
        rep[archive] = overlay_sheets(xb, ps, archive)
    print('layouts:')
    make_icons.KNOWN_PICTURES = make_icons.picture_names(xb)
    for archive in LAYOUT_ARCHIVES:
        r = layouts(os.path.join(xb, 'frontend', archive), 'ps2', strict=True)
        if r is None: print('  no %s in the Xbox data folder' % archive)
        elif r: rep[archive] = {**rep.get(archive, {}), **r}
    pack.MAXTRIES = 1024
    os.makedirs(os.path.join(out, 'data', 'frontend'), exist_ok=True)
    for name, files_new in rep.items():
        files = []
        for n, b in read_big(os.path.join(xb, 'frontend', name)):
            if n in files_new:
                c = pack.refpack(files_new[n])
                assert unrefpack(c) == files_new[n]
                files.append((n, c))
            else:
                files.append((n, b))
        dst = os.path.join(out, 'data', 'frontend', name)
        pack.write_big(dst, files)
        print('wrote', dst, '(%d files changed)' % len(files_new))
    os.makedirs(os.path.join(out, 'data', 'igshapes'), exist_ok=True)
    dst = os.path.join(out, 'data', 'igshapes', 'igcrsr.xsh')
    open(dst, 'wb').write(diamonds(xb, ps))
    print('wrote', dst)


if __name__ == '__main__':
    main()
