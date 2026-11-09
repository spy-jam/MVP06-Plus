#!/usr/bin/env python3
"""Build gc_icons: the Xbox game's button art redrawn with the GameCube release's icons.

usage: python make_icons.py <Xbox data folder> <GameCube data folder> <output gc_icons folder>
  e.g. python make_icons.py assets\\data C:\\path\\to\\gc\\root\\data gc_icons
Needs Python 3 and Pillow (pip install pillow). Nothing from either disc is stored in this repository.

What it changes (the game looks these up by name, the same names on both releases):
  data/frontend/shared.big  helpbuts.xsh: the help icons. Each Xbox button's icon becomes the GameCube button that
      does the same job in the menus (B stays B for Back, X becomes Y for Random, Y becomes X for User Profile);
      L, R, START and the White/Black slots take the GameCube L, R, START and C stick pictures. The controller
      pictures (gpad, gpa2, gpdx) become the GameCube pad.
  data/frontend/igonly.big  ingameov.xsh: the pitch select diamonds, PICK and STAMINA become the GameCube's own
      pictures (its pitchslc sheet), the fifth pitch at the top right with R.
      replay.xsh: the replay controls panel becomes the GameCube's, with its buttons.
  data/igshapes/igcrsr.xsh  the base runner and fielder diamonds: B at third, Y at second, X at first, drawn with
      the GameCube's pictures.
  data/frontend/frontend.big  the menu layouts, as ingame.big: the help bar and keyboard spacing, team select's
      pads and arrows, the draft's Auto Finish box.
  data/frontend/load0.big - load7.big  the loading screens with a controller: the GameCube's (when the data folders
      have them).
  data/frontend/ingame.big  the in-game layouts. Both releases ship the same files, with a visibility flag per
      platform on each element: the Xbox groups take the GameCube groups' places where they differ on screen
      (Select Controller, the fifth pitch's label, the help bar), the cutoff prompt shows R, argue and charge the mound show B.
  data/frontend/minigame.big  the mini game layouts (the same file on every release), every screen as the GameCube
      draws it: the help bar, the pitch slots' colours and the fifth pitch at the top right, the fielding HUD's
      pitch arrows, Select Controller's pads, Press Start, the cutoff prompt, Rumble for Vibration.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
from iconlib.big import read_big
from iconlib.refpack import unrefpack
from iconlib import pack
from iconlib.shp import entries, decode_xbox, decode_gc, encode_xbox_into
from iconlib.atlas_patch import fit, replace_disc

def unpack(b): return unrefpack(b) if b[:2] == b'\x10\xfb' else b

def sheet(path, name):
    for n, b in read_big(path):
        if n == name: return unpack(b)
    raise SystemExit('%s has no %s' % (path, name))

def records(u, off, E):
    """a sheet's named records: name -> (x, y, w, h) inside its one picture"""
    import struct
    from iconlib.shp import blocks
    recs = names = None
    for bo, t, n in blocks(u, off, E)[1:]:
        d = u[bo:bo + n if n else len(u)]
        if t == 0x7c: recs = [struct.unpack_from(E + '4I', d, 8 + 16 * i) for i in range((len(d) - 8) // 16)]
        if t == 0x6f: names = d[8:].split(b'\0')[0].decode('latin1').split(',')[1:]
    return dict(zip(names, recs))

def depth(l): return len(l) - len(l.lstrip(b' '))

def adopt(fel, src, dst, parent=None, swap=None):
    """every group named dst (under a group named parent, if given) takes the content and place of its sibling
    group named src; dst keeps its name and its platform flags, so the game still finds it by its Xbox path.
    swap: pairs of icon names exchanged in the copy (the two releases' sheets hold some buttons in other slots)"""
    L = fel.split(b'\n'); out = []; i = 0; done = 0
    def end(i):
        d = depth(L[i]); j = i + 1
        while j < len(L) and L[j].strip() and depth(L[j]) > d: j += 1
        return j
    def name(l): return l.strip().split(b',')[0].split(b':')[-1]
    def sibling(i, nm):  # the group named nm beside line i
        d = depth(L[i]); k = i - 1
        while k >= 0 and depth(L[k]) >= d:
            if depth(L[k]) == d and name(L[k]) == nm: return k
            k -= 1
        k = i + 1
        while k < len(L) and L[k].strip() and depth(L[k]) >= d:
            if depth(L[k]) == d and name(L[k]) == nm: return k
            k += 1
        return None
    def parent_name(i):
        d = depth(L[i]); k = i - 1
        while k >= 0 and depth(L[k]) >= d: k -= 1
        return name(L[k]) if k >= 0 else None
    while i < len(L):
        l = L[i]
        if l.strip().startswith((b'GR:', b'GG:')) and name(l) == dst and (parent is None or parent_name(i) == parent):
            s = sibling(i, src)
            if s is not None:
                head = l.rstrip(b'\r').split(b','); sh = L[s].rstrip(b'\r').split(b',')
                sh[0] = head[0]; sh[7:11] = head[7:11]  # name, then the PC/PS2/Xbox/GameCube flags
                cr = b'\r' if l.endswith(b'\r') else b''
                out.append(b','.join(sh) + cr)
                body = L[s + 1:end(s)]
                for x, y in swap or ():
                    body = [l.replace(x, b'\0').replace(y, x).replace(b'\0', y) for l in body]
                out.extend(body)
                i = end(i); done += 1
                continue
        out.append(l); i += 1
    assert done, (src, dst)
    return b'\n'.join(out)

FLAG = {'ps2': 8, 'xbox': 9, 'gc': 10}  # a .fel line split at ',': fields 7-10 are the PC/PS2/Xbox/GameCube flags
LEAVES = (b'RT:', b'TB:', b'TX:', b'TL:')  # coloured boxes and text: an Xbox one is shown exactly when p's is

KNOWN_PICTURES = None  # picture names the Xbox data has (picture_names): an icon twin is taken only when its picture is one


# the Xbox files picture_names reads: the front end archives the art is made from and the in-game sheets. Only these, as
# the art was made and checked with; the whole data folder is about 2 GB, too much to read (MemoryError on Windows)
PICTURE_SOURCES = {'frontend/' + n for n in ('apt.big', 'cbplay.big', 'cooplay.big', 'coopov.big', 'frontend.big',
                                             'igonly.big', 'ingame.big', 'minigame.big', 'shared.big')} | \
                  {'igshapes/' + n for n in ('igcrsr.xsh', 'igcrsr1.xsh', 'igcrsr9.xsh')}


def picture_names(xb):
    """every picture name in the Xbox data folder's sheets (.xsh, loose or in a .big): sheet entries and atlas records"""
    import struct
    from iconlib.shp import entries
    names = set()
    def add(raw):
        try:
            es, E = entries(raw)
        except (struct.error, UnicodeDecodeError):
            return
        for n, o in es:
            names.add(n.encode('latin1'))
            try: names.update(k.encode('latin1') for k in records(raw, o, E))
            except Exception: pass
    for dp, _, fs in os.walk(xb):
        for fn in fs:
            path = os.path.join(dp, fn)
            rel = os.path.relpath(path, xb).replace(os.sep, '/').lower()
            if rel not in PICTURE_SOURCES:
                continue
            if fn.lower().endswith('.big'):
                for n, b in read_big(path):
                    if n.lower().endswith('.xsh'): add(unpack(b))
            elif fn.lower().endswith('.xsh'):
                add(open(path, 'rb').read())
    return names


def as_platform(fel, p, skip=(), swap=(), strict=False):
    """the whole layout drawn as platform p ('ps2' or 'gc') draws it, for the mini games (minigame.big), whose
    layouts are the same file on every release:
      - a group the Xbox draws and p doesn't, beside exactly one group p draws and the Xbox doesn't, takes that
        group's place and content (adopt); it keeps its name and flags, and inside it the Xbox draws what p draws
      - a box or text the Xbox and p draw differently (the pitch slots' button colours) is drawn as p draws it
    skip: group names left alone (handled by the caller); swap: icon names exchanged in everything p draws (the
    GameCube sheet holds B and X the other way round from the menus' Xbox slots, as in the nav bars above);
    strict: adopt only a group whose groups inside (GR, GG, SG, BU: what the game finds by name) include all of the
    Xbox group's (MVP 06: its GameCube groups are partly 2005's, older than the screens); 'leaves': its texts, boxes
    and icons too (MVP 06's GameCube groups: the code fills the Xbox's by name, and 2005's nav bars name theirs otherwise)
    returns the new layout and a list of what changed"""
    P, X = FLAG[p], FLAG['xbox']
    L = fel.split(b'\n'); n = len(L)
    def f(i): return L[i].rstrip(b'\r').split(b',')
    def name(i): return L[i].strip().split(b',')[0].split(b':')[-1]
    def flags(i):
        v = f(i)
        return (v[P], v[X]) if len(v) > 10 and all(x in (b'0', b'1') for x in v[7:11]) else None
    def end(i):
        d = depth(L[i]); j = i + 1
        while j < n and L[j].strip() and depth(L[j]) > d: j += 1
        return j
    def siblings(i):
        d = depth(L[i]); k = i - 1
        while k >= 0 and depth(L[k]) >= d: k -= 1
        j = k + 1; out = []
        while j < n and L[j].strip() and depth(L[j]) >= d:
            if depth(L[j]) == d: out.append(j)
            j += 1
        return out
    def is_group(i): return L[i].strip().startswith((b'GR:', b'GG:'))
    def show_as_p(line):  # the Xbox flag takes p's; icons swapped
        cr = b'\r' if line.endswith(b'\r') else b''
        v = line.rstrip(b'\r').split(b',')
        if len(v) > 10 and all(x in (b'0', b'1') for x in v[7:11]): v[X] = v[P]
        line = b','.join(v)
        for a, b in swap: line = line.replace(a, b'\0').replace(b, a).replace(b'\0', b)
        return line + cr
    def icon_twin(i):
        """the sibling icon (SH) p draws and the Xbox doesn't, within 4 pixels of icon i (pause Show Info, the ballpark
        editor's Reset, the HUD's L1/R1, the controller pages' buttons: the PS2 icon is a separate leaf there)"""
        v = f(i)
        try: x, y = int(v[3]), int(v[4])
        except ValueError: return None
        best = None
        for s in siblings(i):
            if s == i or not L[s].strip().startswith(b'SH:') or flags(s) != (b'1', b'0'): continue
            w = f(s)
            try: d = max(abs(int(w[3]) - x), abs(int(w[4]) - y))
            except ValueError: continue
            if d <= 4 and (best is None or d < best[0]): best = (d, s)
        return best[1] if best else None
    out = []; log = []; i = 0
    while i < n:
        fl = flags(i) if is_group(i) else None
        strict_left = False
        if fl == (b'0', b'1') and name(i) not in skip:
            src = [s for s in siblings(i) if is_group(s) and flags(s) == (b'1', b'0')]
            if len(src) > 1:  # several: the one named for p in the Xbox one's name (XBOXCONTROLLER -> PS2CONTROLLER)
                tag = {'ps2': b'PS2', 'gc': b'GC'}[p]
                named = [s for s in src if name(s) == name(i).replace(b'XBOX', tag)]
                if len(named) == 1: src = named
            if len(src) == 1 and strict:
                kinds = (b'GR:', b'GG:', b'SG:', b'BU:') + ((b'TX:', b'TL:', b'TB:', b'SH:', b'RT:') if strict == 'leaves' else ())
                def groups(k):
                    return {name(m) for m in range(k + 1, end(k)) if L[m].strip().startswith(kinds)}
                missing = groups(i) - groups(src[0])
                if missing:
                    log.append('L%d %s: the %s group lacks %s, left' % (i + 1, name(i).decode(), p,
                               ', '.join(sorted(x.decode() for x in missing))))
                    src = []; strict_left = True
            if len(src) == 1:
                s = src[0]
                head = f(i); sh = f(s)
                sh[0] = head[0]; sh[7:11] = head[7:11]
                cr = b'\r' if L[i].endswith(b'\r') else b''
                out.append(b','.join(sh) + cr)
                out.extend(show_as_p(l) for l in L[s + 1:end(s)])
                log.append('L%d %s takes %s' % (i + 1, name(i).decode(), name(s).decode()))
                i = end(i); continue
            if not src and not strict_left: log.append('L%d %s: no %s group beside it, left' % (i + 1, name(i).decode(), p))
            elif src: log.append('L%d %s: %d %s groups beside it, left' % (i + 1, name(i).decode(), len(src), p))
        l = L[i]
        fl = flags(i)
        if strict and fl == (b'0', b'1') and l.strip().startswith(b'SH:'):
            twin = icon_twin(i)
            if twin is not None and KNOWN_PICTURES is not None and f(twin)[12] not in KNOWN_PICTURES:
                log.append('L%d %s: %s has no picture in the Xbox data, left' % (i + 1, name(i).decode(), f(twin)[12].decode('latin1')))
                twin = None
            if twin is not None:  # an icon only the Xbox draws, with p's own icon at the same spot: p's in its place
                head = f(i); tw = f(twin)
                tw[0] = head[0]; tw[7:11] = head[7:11]
                cr = b'\r' if L[i].endswith(b'\r') else b''
                line = b','.join(tw)
                for a, b in swap: line = line.replace(a, b'\0').replace(b, a).replace(b'\0', b)
                out.append(line + cr)
                log.append('L%d %s draws %s' % (i + 1, name(i).decode(), tw[12].decode('latin1')))
                i += 1; continue
        if fl and fl[0] != fl[1] and l.strip().startswith(LEAVES):
            log.append('L%d %s shown as on %s' % (i + 1, name(i).decode(), p)); l = show_as_p(l)
        elif fl and fl[0] == b'1' and swap:  # icon names swapped in what p draws; the flags left as they are, so a
            cr = b'\r' if l.endswith(b'\r') else b''  # group only p draws (2005's NAVGROUPGC) stays hidden on the Xbox
            l = l.rstrip(b'\r')
            for a, b in swap: l = l.replace(a, b'\0').replace(b, a).replace(b'\0', b)
            l += cr
        out.append(l); i += 1
    return b'\n'.join(out), log

def layouts(path, p, extra=None, strict=False):
    """every layout in one archive drawn as platform p draws it (as_platform): {name: new layout} for those that
    change, or None when the archive isn't there"""
    if not os.path.exists(path):
        return None
    swap = [(b'bu01', b'bu03'), (b'bp01', b'bp03')] if p == 'gc' else ()
    res = {}
    for n, b in read_big(path):
        if not n.endswith('.fel'): continue
        t = unpack(b)
        t2, skip = extra(n, t) if extra else (t, ())
        t2, log = as_platform(t2, p, skip=skip, swap=swap, strict=strict)
        if t2 != t:
            res[n] = t2
        for x in log: print('  %s %s: %s' % (os.path.basename(path), n, x))
    return res

def minigame(xb, p, extra=None):
    """minigame.big's layouts drawn as platform p draws them: {name: new layout} for the files that change.
    extra(name, layout) runs first for the few screens that need more (Select Controller's pads)"""
    path = os.path.join(xb, 'frontend', 'minigame.big')
    if not os.path.exists(path):
        print('no minigame.big in the Xbox data folder, the mini games stay as on the Xbox')
        return None
    swap = [(b'bu01', b'bu03'), (b'bp01', b'bp03')] if p == 'gc' else ()
    res = {}
    for n, b in read_big(path):
        if not n.endswith('.fel'): continue
        t = unpack(b)
        t2, skip = extra(n, t) if extra else (t, ())
        t2, log = as_platform(t2, p, skip=skip, swap=swap)
        if t2 != t:
            res[n] = t2
            for x in log: print('  minigame %s: %s' % (n, x))
    return res

def main():
    if len(sys.argv) != 4: raise SystemExit(__doc__)
    xb, gc, out = sys.argv[1:]
    gh = sheet(os.path.join(gc, 'frontend', 'shared.big'), 'helpbuts.gsh')
    G = {n: decode_gc(gh, o) for n, o in entries(gh)[0]}

    # help icons. The menus name these slots by Xbox button (bu01 is "the B button"), so each gets the GameCube
    # button that does the same job there: Back is B on both, Random X -> Y, User Profile Y -> X (the menu actions
    # 2, 3 and 4 of the two releases' control tables). Same-size pictures are copied as they are; the controller
    # pictures go where the CPU outline sits on screen.
    xh = sheet(os.path.join(xb, 'frontend', 'shared.big'), 'helpbuts.xsh')
    src = {'bu01': 'bu03', 'bu02': 'bu02', 'bu03': 'bu01', 'gpa2': 'gpad'}
    for n, off in entries(xh)[0]:
        xi = decode_xbox(xh, off)
        g = G[src.get(n, n)]
        if n in ('gpdx', 'gpad', 'gpa2'):
            # the CPU outline and the pad: the layout patches below draw them in the GameCube's own boxes (64x49 on
            # team select and in game), where the whole picture fills the box, so each is stretched as it is
            new = g.resize(xi.size, Image.LANCZOS)
        elif g.size == xi.size:
            new = g.copy()
        else:  # bq00 is 32x64 on Xbox: the GameCube START, centred where the Xbox arrow was
            bb = list(xi.getbbox() or (0, 0, xi.width, xi.height))
            cy = (bb[1] + bb[3]) // 2
            new = Image.new('RGBA', xi.size, (0, 0, 0, 0))
            new.alpha_composite(g, ((xi.width - g.width) // 2, max(0, min(xi.height - g.height, cy - g.height // 2))))
        for c in ((0, 0), (new.width - 1, 0), (0, new.height - 1), (new.width - 1, new.height - 1)):
            if new.getpixel(c) == (65, 197, 65, 255):  # stray opaque marker pixels in the GameCube C pictures
                new.putpixel(c, (0, 0, 0, 0))
        xh = encode_xbox_into(xh, off, new)

    # in-game sheet: the pitch select diamonds, PICK and STAMINA become the GameCube's own pictures (its pitchslc
    # sheet). Both releases draw them from the same layout boxes (155x129, 44x41, 64x40), so each GameCube picture
    # is stretched to its Xbox record as the GameCube stretches it to the box. The GameCube diamond with five pitches
    # has the fifth box at the top right with R under it, where the layout patch below moves that pitch's label.
    xi_raw = sheet(os.path.join(xb, 'frontend', 'igonly.big'), 'ingameov.xsh')
    off = entries(xi_raw)[0][0][1]
    a = decode_xbox(xi_raw, off)
    rec = records(xi_raw, off, '<')
    ps = sheet(os.path.join(gc, 'frontend', 'igonly.big'), 'pitchslc.gsh')
    P = {n: decode_gc(ps, o) for n, o in entries(ps)[0]}
    for n in ('ps00', 'ps01', 'ps02', 'ps03', 'pick', 'stam'):
        x, y, w, h = rec[n]
        a.paste(Image.new('RGBA', (w, h), (0, 0, 0, 0)), (x, y))
        a.alpha_composite(P[n].resize((w, h), Image.LANCZOS), (x, y))
    xi_new = encode_xbox_into(xi_raw, off, a)

    # replay controls panel (igonly.big replay.xsh, record rep1): the button pictures are part of the panel's art, so
    # it becomes the GameCube's panel (B, L, A, R, X under the transport arrows, Y Hide, START Exit, Z Game Camera,
    # the control pad, control stick and C stick on the left). The layout draws it in a 512x127 box on both; the
    # GameCube's picture is 512x64, the Xbox record 512x128.
    xr_raw = sheet(os.path.join(xb, 'frontend', 'igonly.big'), 'replay.xsh')
    roff = entries(xr_raw)[0][0][1]
    r = decode_xbox(xr_raw, roff)
    rrec = records(xr_raw, roff, '<')
    gr = sheet(os.path.join(gc, 'frontend', 'igonly.big'), 'replay.gsh')
    grep = decode_gc(gr, dict(entries(gr)[0])['rep1'])
    x, y, w, h = rrec['rep1']
    r.paste(Image.new('RGBA', (w, h), (0, 0, 0, 0)), (x, y))
    r.alpha_composite(grep.resize((w, h), Image.LANCZOS), (x, y))
    xr_new = encode_xbox_into(xr_raw, roff, r)

    # base runner and fielder diamonds (data/igshapes/igcrsr.xsh, a loose file): the Xbox draws its round X, Y and
    # B (records PXBX, PXBY, PXBB) at third, second and first base. The
    # GameCube draws its own pictures (pgcb, pgcy, pgcx) there: B at third, Y at second, X at first.
    cr_raw = open(os.path.join(xb, 'igshapes', 'igcrsr.xsh'), 'rb').read()
    gcr = open(os.path.join(gc, 'igshapes', 'igcrsr.gsh'), 'rb').read()
    coff = entries(cr_raw)[0][0][1]
    c = decode_xbox(cr_raw, coff)
    crec = records(cr_raw, coff, '<')
    g = decode_gc(gcr, entries(gcr)[0][0][1])
    grec = records(gcr, entries(gcr)[0][0][1], '>')
    def gpic(n):
        x, y, w, h = grec[n]
        return g.crop((x, y, x + w, y + h))
    # (pwht, pred, pblu and ptxx, the white, red and blue circles and the yellow X beside them, are the pitch result
    # markers, not buttons: they stay)
    for xbn, gcn in (('PXBX', 'pgcb'), ('PXBY', 'pgcy'), ('PXBB', 'pgcx')):
        x, y, w, h = crec[xbn]
        pic = gpic(gcn).resize((w, h), Image.LANCZOS)
        c.paste(Image.new('RGBA', (w, h), (0, 0, 0, 0)), (x, y))
        c.alpha_composite(pic, (x, y))
    cr_new = encode_xbox_into(cr_raw, coff, c)

    # in-game layouts (ingame.big). Each element has a visibility flag per platform (PC, PS2, Xbox, GameCube); the
    # game code finds elements by their Xbox path, so GameCube-only groups are copied into the Xbox ones' places.
    feln = {}
    def fel_get(n):
        if n not in feln: feln[n] = sheet(os.path.join(xb, 'frontend', 'ingame.big'), n)
        return feln[n]

    # Select Controller: the GameCube group draws the pad and the CPU outline in 64x49 boxes (the Xbox one in 75x70
    # and 72x55); its pads draw gpa2, the GameCube pad as gpad also is
    n = 'fes_ingamecontrolmenu.fel'
    feln[n] = adopt(fel_get(n), b'GCCONTROLLER', b'XBOXCONTROLLER').replace(b'gpad,gpad,', b'gpa2,gpa2,')
    # pitch select: the fifth pitch's label at the top right, as on the GameCube (its group OTHER)
    for n in ('fes_hudleft.fel', 'fes_hudright.fel'):
        feln[n] = adopt(fel_get(n), b'OTHER', b'XBOX', parent=b'RIGHTSHLDR')
    # the in-game help bar (pause menu, bullpen): the GameCube's places, the START icon further left and the text
    # further right of A, B, X and Y. The GameCube sheet has B in bu03 and X in bu01, the menus' Xbox slots the
    # other way round, so the copied icon lists swap them back.
    for n in ('fes_navbar.fel', 'fes_ingamebullpen.fel'):
        feln[n] = adopt(fel_get(n), b'NAVGROUPGC', b'NAVGROUPXBOX', swap=[(b'SE:bu01', b'SE:bu03')])
    # replay: the camera name on its black strip at the right, and SHOW with the GameCube's button for it (Y, bu02;
    # the Xbox's is Black)
    # (SHOW starts hidden as on the Xbox; the Xbox code shows it with the panel hidden)
    t = adopt(fel_get('fes_ingamereplay.fel'), b'GC', b'XBOX')
    t2 = t.replace(b'  GR:SHOWCONTROLS,1,0,507,408,', b'  GR:SHOWCONTROLS,0,0,507,408,')
    assert t2 != t
    feln['fes_ingamereplay.fel'] = t2
    # overlay: the cutoff throw shows the R picture (bu05) as the GameCube's SH3 does, not Black (bu07); argue and
    # charge the mound are Xbox Y, GameCube B, and bu01 holds the GameCube B (bu03 holds X for the menus' Y)
    n = 'fes_ingameoverlay.fel'
    t = fel_get(n)
    t2 = t.replace(b'SH:SH1,1,0,377,412,32,32,0,1,1,0,2,bu07,bu07,', b'SH:SH1,1,0,377,412,32,32,0,1,1,0,2,bu05,bu05,')
    t2 = t2.replace(b'SH:BUTTON,1,0,176,295,29,29,1,1,1,1,2,bu03,bu03,', b'SH:BUTTON,1,0,176,295,29,29,1,1,1,1,2,bu01,bu01,')
    t2 = t2.replace(b'SH:BUTTON,1,0,441,379,32,32,1,1,1,1,2,bu03,bu03,', b'SH:BUTTON,1,0,441,379,32,32,1,1,1,1,2,bu01,bu01,')
    assert t2.count(b'bu01,bu01') == 2 and b'2,bu07,bu07' not in t2
    feln[n] = t2

    # front end layouts (frontend.big): the same treatment. The help bar along the bottom of the menus and the on-screen
    # keyboard's put their text 5 px further from the icons, in the GameCube's grey; team select draws the pads, the
    # CPU outlines and the arrows where the GameCube does; the draft and staff screens' Auto Finish box sits as on
    # the GameCube.
    fe = {n: b for n, b in read_big(os.path.join(xb, 'frontend', 'frontend.big'))}
    fel_fe = {}
    def fe_get(n): return fel_fe.get(n) or unpack(fe[n])
    sw = [(b'SE:bu01', b'SE:bu03'), (b'bu01,bu01', b'bu03,bu03')]
    fel_fe['fes_navbar.fel'] = adopt(fe_get('fes_navbar.fel'), b'NAVGROUPGC', b'NAVGROUPXBOX', swap=sw)
    fel_fe['fes_tkeyboard.fel'] = adopt(fe_get('fes_tkeyboard.fel'), b'GCNAVBAR', b'XBOXNAVBAR', swap=sw)
    fel_fe['fes_controllerselect.fel'] = adopt(fe_get('fes_controllerselect.fel'), b'GC', b'XBOX')
    for n in ('fes_fdraftplayer.fel', 'fes_fhirestaff.fel'):
        fel_fe[n] = adopt(fe_get(n), b'AUTOFINISHGC', b'AUTOFINISHXBOX')

    pack.MAXTRIES = 1024
    # replacements per archive: frontend.big and ingame.big both hold an fes_navbar.fel, each its own
    rep = {'shared.big': {'helpbuts.xsh': xh}, 'igonly.big': {'ingameov.xsh': xi_new, 'replay.xsh': xr_new},
           'ingame.big': feln, 'frontend.big': fel_fe}
    # mini games (minigame.big): every screen as the GameCube draws it (see as_platform). Select Controller's pads
    # are the GameCube's, drawn from gpa2 as in game.
    def mg_extra(n, t):
        if n == 'fes_igminicontrolmenu.fel': t = t.replace(b'gpad,gpad,', b'gpa2,gpa2,')
        return t, ()
    mg = minigame(xb, 'gc', mg_extra)
    if mg is not None: rep['minigame.big'] = mg
    os.makedirs(os.path.join(out, 'data', 'frontend'), exist_ok=True)
    for name in rep:
        files = []
        for n, b in read_big(os.path.join(xb, 'frontend', name)):
            if n in rep[name]:
                c = pack.refpack(rep[name][n])
                assert unrefpack(c) == rep[name][n]
                files.append((n, c))
            else:
                files.append((n, b))
        dst = os.path.join(out, 'data', 'frontend', name)
        pack.write_big(dst, files)
        print('wrote', dst)
    # loading screens 0-7, the ones with a controller (Hitter's Eye, baserunning, Pure Swing, Big Play Control,
    # fielding, pitching, steals): the GameCube's pictures. Both are 1024x512 DXT1 (the GameCube's CMPR is the same
    # blocks laid out differently), so the GameCube's blocks go in as they are. 8-48 are the same tips on both;
    # 49-58 are the Xbox's Xbox Live tips.
    import struct
    from iconlib.cmpr import gc_cmpr_to_dxt1
    for i in range(8):
        xp, gp = (os.path.join(d, 'frontend', 'load%d.big' % i) for d in (xb, gc))
        if not (os.path.exists(xp) and os.path.exists(gp)):
            print('no load%d.big in both data folders, its loading screen stays' % i)
            continue
        (xn, xbig), = read_big(xp)
        (gn, gbig), = read_big(gp)
        xu, gu = unpack(xbig), unpack(gbig)
        xo, go = entries(xu)[0][0][1], entries(gu)[0][0][1]
        xw, xh = struct.unpack_from('<HH', xu, xo + 4)
        gw, gh = struct.unpack_from('>HH', gu, go + 4)
        assert xu[xo] == 0x60 and gu[go] == 0x1E and (xw, xh) == (gw, gh), (i, hex(xu[xo]), hex(gu[go]))
        blocks = gc_cmpr_to_dxt1(gu, go, gw, gh)
        new = xu[:xo + 16] + blocks + xu[xo + 16 + len(blocks):]
        c = pack.refpack(new)
        assert unrefpack(c) == new
        dst = os.path.join(out, 'data', 'frontend', 'load%d.big' % i)
        pack.write_big(dst, [(xn, c)])
        print('wrote', dst)

    os.makedirs(os.path.join(out, 'data', 'igshapes'), exist_ok=True)
    dst = os.path.join(out, 'data', 'igshapes', 'igcrsr.xsh')
    open(dst, 'wb').write(cr_new)
    print('wrote', dst)

if __name__ == '__main__':
    main()
