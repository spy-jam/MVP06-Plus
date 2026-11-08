#!/usr/bin/env python3
"""Build ps2_icons: the Xbox game's button art redrawn with the PlayStation 2 release's icons.

usage: python make_ps2_icons.py <Xbox data folder> <PS2 data folder> <output ps2_icons folder>
  e.g. python make_ps2_icons.py assets\\data D:\\DATA ps2_icons
The PS2 folder is the disc's DATA folder (FRONTEND\\*.BIG, IGSHAPES\\IGCRSR.SSH); names are matched in any case.
Needs Python 3, Pillow 11.2 or later and numpy (pip install pillow numpy). Nothing from either disc is stored in this repository.

The two releases share their layouts (.fel): each element has a visibility flag per platform (PC, PS2, Xbox,
GameCube) and the game finds elements by their Xbox path, so where the PS2 shows its own group (the help bar, the
keyboard's, the pitch select labels, the replay panel, the bullpen and overlay prompts, the
draft's Auto Finish box) that group is copied into the Xbox group's place. Select Controller keeps the Xbox's
four rows (the PS2's has two) with the pads in the PS2's proportions. The PS2's control layout puts every
button where the Xbox has the matching one (Cross A, Circle B, Square X, Triangle Y, L1/R1 the triggers, L2/R2
White/Black, Select Back), and the two sheets name their icons the same way, so each Xbox icon takes the PS2
picture of the same name:
  data/frontend/shared.big  helpbuts.xsh: the help icons and controller pictures
  data/frontend/igonly.big  ingameov.xsh: the pitch select diamonds, PICK and STAMINA (the PS2's pitchslc sheet)
                            replay.xsh: the replay controls panel
  data/igshapes/igcrsr.xsh  the base runner and fielder diamonds: Square at third, Triangle at second, Circle first
  data/frontend/frontend.big, ingame.big  the layouts, as above
  data/frontend/load0.big - load7.big  the loading screens with a controller
  data/frontend/minigame.big  the mini game layouts (the same file on every release), every screen as the PS2 draws
      it: the help bar (Triangle Cancel), the pitch slots' colours and the fifth pitch at the top right with R1,
      Select Controller's pads, Press Start, the cutoff prompt
"""
import os, sys, struct
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, '..', 'gc_layout'))
from PIL import Image
from iconlib.big import read_big
from iconlib.refpack import unrefpack
from iconlib import pack
from iconlib.shp import entries, decode_xbox, encode_xbox_into
from iconlib.ps2 import decode_ps2
from make_icons import sheet, records, adopt, unpack, minigame


def find(root, *parts):
    """a path under root, matching each part in any case"""
    p = root
    for part in parts:
        names = {n.lower(): n for n in os.listdir(p)} if os.path.isdir(p) else {}
        if part.lower() not in names: raise SystemExit('no %s in %s' % (part, p))
        p = os.path.join(p, names[part.lower()])
    return p


def ps2_sheet(ps, big, name):
    for n, b in read_big(find(ps, 'frontend', big)):
        if n.lower() == name.lower(): return unpack(b)
    raise SystemExit('%s has no %s' % (big, name))


def paste_into(atlas, rec, pic):
    x, y, w, h = rec
    atlas.paste(Image.new('RGBA', (w, h), (0, 0, 0, 0)), (x, y))
    atlas.alpha_composite(pic.convert('RGBA').resize((w, h), Image.LANCZOS), (x, y))


def pad_boxes(fel, group, w, h):
    """In the groups named group, the controllers (gpad, gpa2) and the CPU outlines (gpdx) drawn w x h, as the PS2
    draws both the same size. The code moves a player's pad onto a side's marker (RIGHTMARKER, LEFTMARKER), where
    that side's outline (RIGHTSIDE, LEFTSIDE) is; the Xbox's tall pad covered the outline from a taller box, so here
    the markers take the pads' size and each outline is centred on its marker, under the pad that lands there."""
    from make_icons import depth
    L = fel.split(b'\n')
    def fields(l): return l.split(b',')
    def name(l): return l.strip().split(b',')[0].split(b':')[-1]
    def box(f): return [int(v) for v in f[3:7]]
    def put(f, cx, cy):
        f[3:7] = [str(int(round(cx - w / 2))).encode(), str(int(round(cy - h / 2))).encode(), str(w).encode(), str(h).encode()]
        return b','.join(f)
    centres = {}; inside = None
    for l in L:
        s = l.strip()
        if inside is not None and s and depth(l) <= inside: inside = None
        if s.startswith((b'GR:', b'GG:')) and name(l) == group: inside = depth(l); continue
        if inside is not None and s.startswith(b'GR:') and name(l) in (b'RIGHTMARKER', b'LEFTMARKER'):
            x, y, bw, bh = box(fields(l)); centres[name(l)[:-6]] = (x + bw / 2, y + bh / 2)
    out = []; inside = None; n = 0
    for l in L:
        s = l.strip()
        if inside is not None and s and depth(l) <= inside: inside = None
        if s.startswith((b'GR:', b'GG:')) and name(l) == group: inside = depth(l); out.append(l); continue
        f = fields(l)
        if inside is not None and s.startswith(b'GR:') and name(l) in (b'RIGHTMARKER', b'LEFTMARKER'):
            l = put(f, *centres[name(l)[:-6]]); n += 1
        elif inside is not None and s.startswith(b'SH:') and len(f) > 13 and f[12] == b'gpdx':
            l = put(f, *centres[name(l)[:-4]]); n += 1
        elif inside is not None and s.startswith(b'SH:') and len(f) > 13 and f[12] in (b'gpad', b'gpa2'):
            x, y, bw, bh = box(f); l = put(f, x + bw / 2, y + bh / 2); n += 1
        out.append(l)
    assert n, group
    return b'\n'.join(out)


def clean_markers(img, recolour=True):
    """the PS2 sheet's controller pictures carry green anchor dots around the pad's silhouette (shoulders, sides,
    grips), which the game draws as green specks around the pads and the CPU outline. A greenish pixel within 2
    pixels of transparency is one (the Triangle button, inside the pad, is not): on the pad it takes the colour of
    the pixels around it, so the light rim stays whole; on the outline (recolour False) it goes"""
    import numpy as np
    for _ in range(3):  # a dot's neighbours can be dots too: again until none is left
        a = np.array(img.convert('RGBA')).astype(float)
        r, g, b, al = (a[..., i] for i in range(4))
        h, w = al.shape
        green = (g > r + 12) & (g > b + 12) & (al > 8)
        pa = np.pad(al, 2, mode='constant')
        low = np.min([pa[dy:dy + h, dx:dx + w] for dy in range(5) for dx in range(5)], axis=0)
        m = green & (low < al.max() * 0.8)
        if not m.any(): break
        out = a.copy()
        for y, x in zip(*np.where(m)):
            y0, y1, x0, x1 = max(0, y - 2), min(h, y + 3), max(0, x - 2), min(w, x + 3)
            nb = a[y0:y1, x0:x1].reshape(-1, 4)
            ok = ~m[y0:y1, x0:x1].reshape(-1) & (nb[:, 3] > 0)
            if recolour and ok.any():
                wt = nb[ok, 3]
                out[y, x, :3] = (nb[ok, :3] * wt[:, None]).sum(0) / wt.sum()
            else:
                out[y, x, 3] = 0
        img = Image.fromarray(out.round().clip(0, 255).astype(np.uint8), 'RGBA')
    return img


def fit_outline(outline, pad, inset=0.025):
    """the CPU outline (gpdx) redrawn over the pad's body, the pad picture without its drop shadow, a little inside
    it. The layouts draw both in the same box (pad_boxes), so a pad landing on a side now covers that side's
    outline; the PS2's outline fills its whole picture, so its curve and ends showed under and beside the pad"""
    import numpy as np
    def bbox(img, frac):
        al = np.array(img.convert('RGBA'))[..., 3]
        ys, xs = np.where(al >= al.max() * frac)
        return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    W, H = outline.size
    pw, ph = pad.size
    px0, py0, px1, py1 = bbox(pad, 0.8)
    tx0, tx1 = (px0 / pw + inset) * W, (px1 / pw - inset) * W
    ty0, ty1 = (py0 / ph + inset) * H, (py1 / ph - inset) * H
    src = outline.convert('RGBA').crop(bbox(outline, 0.3))
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    out.alpha_composite(src.resize((max(1, round(tx1 - tx0)), max(1, round(ty1 - ty0))), Image.LANCZOS),
                        (round(tx0), round(ty0)))
    return out


def dxt1(img):
    """1024x512 RGB -> DXT1 blocks, as the Xbox loading screens hold them (linear, row by row)"""
    import io
    b = io.BytesIO()
    img.convert('RGB').save(b, 'DDS', pixel_format='DXT1')
    d = b.getvalue()
    assert d[:4] == b'DDS ' and d[84:88] == b'DXT1'
    return d[128:128 + img.width * img.height // 2]


def main():
    if len(sys.argv) != 4: raise SystemExit(__doc__)
    xb, ps, out = sys.argv[1:]

    # help icons: same names, same buttons (see above). The 32x32 pictures go as they are; the controller pictures
    # are stretched to the Xbox's (the layouts draw them in their own boxes); bq00, the Xbox's 32x64 Back arrow,
    # takes the PS2's SELECT centred in it.
    ph = ps2_sheet(ps, 'shared.big', 'helpbuts.ssh')
    P = {n: decode_ps2(ph, o) for n, o in entries(ph)[0]}
    # the controller pictures: the green anchor dots out, and the CPU outline where the pad's body is
    for n in ('gpad', 'gpa2'): P[n] = clean_markers(P[n])
    P['gpdx'] = fit_outline(clean_markers(P['gpdx'], recolour=False), P['gpad'])
    xh = sheet(os.path.join(xb, 'frontend', 'shared.big'), 'helpbuts.xsh')
    for n, off in entries(xh)[0]:
        xi = decode_xbox(xh, off)
        g = P[n]
        if g.size == xi.size:
            new = g.copy()
        elif n in ('gpad', 'gpa2', 'gpdx'):
            new = g.resize(xi.size, Image.LANCZOS)
        else:
            new = Image.new('RGBA', xi.size, (0, 0, 0, 0))
            new.alpha_composite(g, ((xi.width - g.width) // 2, (xi.height - g.height) // 2))
        xh = encode_xbox_into(xh, off, new)

    # pitch select: the PS2's diamonds (ps00-ps03, the fifth pitch at the top right with R1), PICK and STAMINA
    xi_raw = sheet(os.path.join(xb, 'frontend', 'igonly.big'), 'ingameov.xsh')
    off = entries(xi_raw)[0][0][1]
    a = decode_xbox(xi_raw, off)
    rec = records(xi_raw, off, '<')
    pp = ps2_sheet(ps, 'igonly.big', 'pitchslc.ssh')
    PP = {n: decode_ps2(pp, o) for n, o in entries(pp)[0]}
    for n in ('ps00', 'ps01', 'ps02', 'ps03', 'pick', 'stam'):
        paste_into(a, rec[n], PP[n])
    xi_new = encode_xbox_into(xi_raw, off, a)

    # replay controls panel (rep1): the PS2's, its buttons drawn in the picture
    xr_raw = sheet(os.path.join(xb, 'frontend', 'igonly.big'), 'replay.xsh')
    roff = entries(xr_raw)[0][0][1]
    r = decode_xbox(xr_raw, roff)
    pr = ps2_sheet(ps, 'igonly.big', 'replay.ssh')
    paste_into(r, records(xr_raw, roff, '<')['rep1'], decode_ps2(pr, dict(entries(pr)[0])['rep1']))
    xr_new = encode_xbox_into(xr_raw, roff, r)

    # base runner and fielder diamonds: the Xbox draws X, Y and B (PXBX, PXBY, PXBB) at third, second and first;
    # the PS2 its Square, Triangle and Circle (PSQR, PTRI, PCIR), the same buttons. Both sheets share one layout.
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
    cr_new = encode_xbox_into(cr_raw, coff, c)

    # layouts: the PS2's groups in the Xbox's places
    feln = {}
    def ig(n):
        if n not in feln: feln[n] = sheet(os.path.join(xb, 'frontend', 'ingame.big'), n)
        return feln[n]
    # Select Controller keeps the Xbox's four rows (the PS2's has two), with its pads in the PS2's proportions
    feln['fes_ingamecontrolmenu.fel'] = pad_boxes(ig('fes_ingamecontrolmenu.fel'), b'XBOXCONTROLLER', 71, 42)
    for n in ('fes_hudleft.fel', 'fes_hudright.fel'):
        feln[n] = adopt(ig(n), b'OTHER', b'XBOX', parent=b'RIGHTSHLDR')
    t = adopt(ig('fes_ingamebullpen.fel'), b'OTHER', b'XBOX')
    feln['fes_ingamebullpen.fel'] = adopt(t, b'NAVGROUPPS2', b'NAVGROUPXBOX')
    feln['fes_navbar.fel'] = adopt(ig('fes_navbar.fel'), b'NAVGROUPPS2', b'NAVGROUPXBOX')
    t = adopt(ig('fes_ingameoverlay.fel'), b'CONSOLE', b'XBOX')
    feln['fes_ingameoverlay.fel'] = adopt(t, b'PS2', b'XBOX')
    feln['fes_ingamereplay.fel'] = adopt(ig('fes_ingamereplay.fel'), b'PS2', b'XBOX')

    fe = {n: b for n, b in read_big(os.path.join(xb, 'frontend', 'frontend.big'))}
    fel_fe = {}
    def fg(n): return fel_fe.get(n) or unpack(fe[n])
    fel_fe['fes_navbar.fel'] = adopt(fg('fes_navbar.fel'), b'NAVGROUPPS2', b'NAVGROUPXBOX')
    fel_fe['fes_tkeyboard.fel'] = adopt(fg('fes_tkeyboard.fel'), b'PS2NAVBAR', b'XBOXNAVBAR')
    fel_fe['fes_controllerselect.fel'] = pad_boxes(fg('fes_controllerselect.fel'), b'XBOX', 80, 50)
    for n in ('fes_fdraftplayer.fel', 'fes_fhirestaff.fel'):
        fel_fe[n] = adopt(fg(n), b'AUTOFINISHPS2', b'AUTOFINISHXBOX')

    pack.MAXTRIES = 1024
    rep = {'shared.big': {'helpbuts.xsh': xh}, 'igonly.big': {'ingameov.xsh': xi_new, 'replay.xsh': xr_new},
           'ingame.big': feln, 'frontend.big': fel_fe}
    # mini games (minigame.big): every screen as the PS2 draws it (see as_platform in make_icons.py): the help bar
    # (Triangle Cancel), the pitch slots' colours and the fifth pitch at the top right, the Press Start boxes, the
    # cutoff prompt. Select Controller keeps its four rows with the pads in the PS2's proportions, as in game.
    def mg_extra(n, t):
        if n == 'fes_igminicontrolmenu.fel': return pad_boxes(t, b'XBOXCONTROLLER', 71, 42), (b'XBOXCONTROLLER',)
        return t, ()
    mg = minigame(xb, 'ps2', mg_extra)
    if mg is not None: rep['minigame.big'] = mg
    os.makedirs(os.path.join(out, 'data', 'frontend'), exist_ok=True)
    for name in rep:
        files = []
        for n, b in read_big(os.path.join(xb, 'frontend', name)):
            if n in rep[name]:
                cmp = pack.refpack(rep[name][n])
                assert unrefpack(cmp) == rep[name][n]
                files.append((n, cmp))
            else:
                files.append((n, b))
        dst = os.path.join(out, 'data', 'frontend', name)
        pack.write_big(dst, files)
        print('wrote', dst)

    # loading screens 0-7, the ones with a controller: the PS2's 512x512 picture, stretched to the Xbox's 1024x512
    # (both fill the screen) and stored as the Xbox's DXT1
    for i in range(8):
        xp = os.path.join(xb, 'frontend', 'load%d.big' % i)
        try:
            pp_ = find(ps, 'frontend', 'load%d.big' % i)
        except SystemExit:
            pp_ = None
        if not (os.path.exists(xp) and pp_):
            print('no load%d.big in both data folders, its loading screen stays' % i)
            continue
        (xn, xbig), = read_big(xp)
        (pn, pbig), = read_big(pp_)
        xu, pu = unpack(xbig), unpack(pbig)
        xo, po = entries(xu)[0][0][1], entries(pu)[0][0][1]
        xw, xh_ = struct.unpack_from('<HH', xu, xo + 4)
        assert xu[xo] == 0x60, hex(xu[xo])
        pic = decode_ps2(pu, po).convert('RGB').resize((xw, xh_), Image.LANCZOS)
        blocks = dxt1(pic)
        new = xu[:xo + 16] + blocks + xu[xo + 16 + len(blocks):]
        cmp = pack.refpack(new)
        assert unrefpack(cmp) == new
        dst = os.path.join(out, 'data', 'frontend', 'load%d.big' % i)
        pack.write_big(dst, [(xn, cmp)])
        print('wrote', dst)

    os.makedirs(os.path.join(out, 'data', 'igshapes'), exist_ok=True)
    dst = os.path.join(out, 'data', 'igshapes', 'igcrsr.xsh')
    open(dst, 'wb').write(cr_new)
    print('wrote', dst)


if __name__ == '__main__':
    main()
