#!/usr/bin/env python3
"""Build gc_icons for MVP 06 NCAA (EXPERIMENTAL): the Xbox game's button art redrawn as a GameCube 06 might have had
it. There was no GameCube MVP 06, so this is an estimate: 2005's GameCube art, changed the way the Xbox and PS2 art
changed from 2005 to 06.

usage: python make_gc_icons06.py <Xbox 06 data folder> <MVP 2005 gc_icons folder> <output gc_icons folder>
  e.g. python make_gc_icons06.py "C:\\MVP06\\assets\\data" "C:\\MVP05\\gc_icons" gc_icons
The second folder is the one make_icons.py built for MVP 2005 (beside MVP05.exe): its GameCube pictures are the
source. Needs Python 3, Pillow 11.2 or later, numpy, scipy and OpenCV (pip install pillow numpy scipy
opencv-python). Nothing from any disc is stored here.

What it changes (the game looks these up by name):
  data/frontend/shared.big   helpbuts.xsh: the help icons. The buttons are 2005's GameCube pictures; the controller
                             pictures (gpad, gpa2 at 48%, the gpdx outline, the new co-op gpco) are the GameCube pad
                             cut out of 2005's GameCube loading screen 3, at the 06 pads' size; the 06-only pictures:
                             the sticks (bq08 control stick, bq09 C-stick, drawn after 2005's loading screens),
                             L3/R3 (bu08/bu09) as Z (the experimental table puts the stick-click jobs on Z), the
                             flash (mi02/mi10) drawn
  data/frontend/igonly.big   ingameov.xsh: pitch select. The Xbox 06 cross with the GameCube buttons in 2005's
                             GameCube arrangement at 90% of its spacing (B left, X right, Y top, A bottom), 2005's
                             sizes; the fifth pitch's tile at the top right with R (as PS2 06 and GameCube 2005);
                             PICK on L; the stick and D-pad direction pictures (bu10-bu21) redrawn GameCube style.
                             replay.xsh: 2005's GameCube replay panel
  data/frontend/coopov.big   the co-op games' copy of igonly's sheets (their own older pitch pictures), the same way
  data/igshapes/igcrsr.xsh   the base runner and fielder diamonds: 2005's GameCube ones
  data/frontend/frontend.big, ingame.big, minigame.big, cooplay.big, cbplay.big, apt.big: the layouts, every screen
                             as the GameCube draws it where the GameCube group is complete (strict; MVP 06's GameCube
                             groups are partly 2005's); online and voice chat labels keep the Xbox's flags
"""
import os, sys, re, math
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as nd
from iconlib.big import read_big
from iconlib.refpack import unrefpack
from iconlib import pack
from iconlib.shp import entries, decode_xbox, encode_xbox_into
import make_icons
from make_icons import sheet, records, as_platform, unpack

LAYOUT_ARCHIVES = ('frontend.big', 'ingame.big', 'minigame.big', 'cooplay.big', 'cbplay.big', 'apt.big')
# The help sheet holds each GameCube button in the slot of the Xbox button whose jobs it does (virtual buttons: Xbox
# B's jobs on GameCube X, X's on B): bu01 the X picture, bu02 B, bu03 Y. 2005's GameCube layouts name the GameCube's
# own (bu01 B, bu02 Y, bu03 X), so what a GameCube group draws is renamed B -> bu02, Y -> bu03, X -> bu01 (the two
# swaps in turn).
GC_SWAP = [(b'bu01', b'bu02'), (b'bu01', b'bu03'), (b'bp01', b'bp02'), (b'bp01', b'bp03')]
# The nav bars (kept as the Xbox's: 06's GameCube ones are 2005's and show nothing or placeholder text) pick their
# icon from a list by job: accept, back, the X job, the Y job, start. 2005's GameCube menus: back on B, the X job
# (Random) on Y, the Y job (profile) on X.
NAV_GROUPS = (b'NAVGROUPXBOX', b'XBOXNAVBAR')
NAV_LIST = {b'SE:bu01': b'SE:bu02', b'SE:bu02': b'SE:bu03', b'SE:bu03': b'SE:bu01'}
ONLINE = re.compile(rb'LIVE|ONLINE|VCHAT|VOIP|CHAT|DNAS')


def font(size):
    for f in ('DejaVuSans-Bold.ttf', 'arialbd.ttf', 'Arial Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
              'C:\\Windows\\Fonts\\arialbd.ttf'):
        try: return ImageFont.truetype(f, size)
        except OSError: pass
    return ImageFont.load_default()


# ---------------------------------------------------------------- picture helpers
def atlas(raw):
    off = entries(raw)[0][0][1]
    return off, decode_xbox(raw, off), records(raw, off, '<')

def crops(raw):
    _, a, rec = atlas(raw)
    return {n: a.crop((x, y, x + w, y + h)) for n, (x, y, w, h) in rec.items()}

def bbox_crop(im):
    return im.crop(im.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox())

def fit(im, size, grow=True):
    c = bbox_crop(im); s = min(size[0] / c.width, size[1] / c.height)
    if not grow: s = min(s, 1)
    c = c.resize((max(1, round(c.width * s)), max(1, round(c.height * s))), Image.LANCZOS)
    out = Image.new('RGBA', size, (0, 0, 0, 0)); out.alpha_composite(c, ((size[0] - c.width) // 2, (size[1] - c.height) // 2))
    return out

def ss(fn, size, k=8):  # drawn k times larger, then scaled down
    big = Image.new('RGBA', (size[0] * k, size[1] * k), (0, 0, 0, 0)); fn(ImageDraw.Draw(big), k, big)
    return big.resize(size, Image.LANCZOS)

def octagon(cx, cy, r):
    return [(cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a))) for a in range(0, 360, 45)]


# ---------------------------------------------------------------- the drawn pictures (after 2005's loading screens)
CREAM = (198, 195, 148)

def indigo_disc(d, cx, cy, R, k):
    d.ellipse([cx - R - 1.2 * k, cy - R - 1.2 * k, cx + R + 1.2 * k, cy + R + 1.2 * k], fill=(8, 6, 10, 255))
    for i in range(32):
        t = i / 31; rr = R * (1 - 0.12 * t); oy = R * 0.10 * t
        d.ellipse([cx - rr, cy - rr + oy, cx + rr, cy + rr + oy], fill=(int(118 - 55 * t), int(120 - 56 * t), int(150 - 46 * t), 255))

def stick(size, kind):
    """the control stick (kind 'control': grey ridged octagonal cap) or the C-stick ('c': yellow, raised C)"""
    def f(d, k, big):
        W, H = big.size; cx, cy = W / 2, H / 2; R = min(W, H) / 2 - 1.3 * k
        indigo_disc(d, cx, cy, R, k); r = R * 0.74
        d.polygon(octagon(cx, cy + R * 0.04, r + 1.4 * k), fill=(14, 12, 18, 255))
        for i in range(24):
            t = i / 23; rr = r * (1 - 0.10 * t); o = -r * 0.07 * t
            c = (int(115 + 70 * t), int(118 + 70 * t), int(122 + 70 * t), 255) if kind == 'control' else \
                (int(150 + 70 * t), int(142 + 70 * t), int(40 + 60 * t), 255)
            d.polygon([(x + o, y + o) for x, y in octagon(cx, cy, rr)], fill=c)
        if kind == 'control':
            for fr in (0.72, 0.46, 0.22):
                rr = r * fr; w = max(1, int(r * 0.10))
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(80, 84, 86, 255), width=w)
                d.arc([cx - rr + w * 0.7, cy - rr + w * 0.7, cx + rr + w * 0.7, cy + rr + w * 0.7], 20, 160, fill=(215, 218, 220, 255), width=max(1, w // 2))
        else:
            ri = r * 0.60
            d.ellipse([cx - ri + k, cy - ri + k, cx + ri + k, cy + ri + k], fill=(120, 110, 25, 255))
            for i in range(12):
                t = i / 11; rr = ri * (1 - 0.15 * t); o = -ri * 0.08 * t
                d.ellipse([cx - rr + o, cy - rr + o, cx + rr + o, cy + rr + o], fill=(int(185 + 50 * t), int(178 + 50 * t), int(60 + 60 * t), 255))
            fo = font(int(ri * 1.5)); tb = d.textbbox((0, 0), 'C', font=fo)
            d.text((cx - (tb[0] + tb[2]) / 2, cy - (tb[1] + tb[3]) / 2), 'C', font=fo, fill=(150, 136, 30, 255))
    return ss(f, size)

def dpad(size, lit):
    def f(d, k, big):
        W, H = big.size; cx, cy = W / 2, H / 2; R = min(W, H) / 2 - 1.3 * k
        indigo_disc(d, cx, cy, R, k); L = R * 0.80; w = L * 0.36
        def arm(a, col, o=0):
            x0, x1, y0, y1 = {'up': (cx - w, cx + w, cy - L, cy), 'down': (cx - w, cx + w, cy, cy + L),
                              'left': (cx - L, cx, cy - w, cy + w), 'right': (cx, cx + L, cy - w, cy + w)}[a]
            d.rectangle([x0 - o, y0 - o, x1 + o, y1 + o], fill=col)
        A = ('up', 'down', 'left', 'right')
        for a in A: arm(a, (14, 12, 18, 255), 1.1 * k)
        for a in A: arm(a, (172, 176, 178, 255))
        d.rectangle([cx - w, cy - w, cx + w, cy + w], fill=(172, 176, 178, 255))
        if lit: arm(lit, (240, 215, 40, 255))
        d.ellipse([cx - w * 0.6, cy - w * 0.6, cx + w * 0.6, cy + w * 0.6], fill=(140, 144, 146, 255))
        for a in A:
            ux, uy = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}[a]
            tx, ty = cx + ux * L * 0.68, cy + uy * L * 0.68; s = w * 0.55
            pts = [(tx + ux * s * 0.6, ty + uy * s * 0.6), (tx - ux * s * 0.4 - uy * s * 0.6, ty - uy * s * 0.4 - ux * s * 0.6),
                   (tx - ux * s * 0.4 + uy * s * 0.6, ty - uy * s * 0.4 + ux * s * 0.6)]
            d.polygon(pts, fill=(110, 112, 114, 255) if a != lit else (170, 140, 20, 255))
    return ss(f, size)

def z_button(size, w=0.92, h=0.55):  # the GameCube Z: an indigo shoulder button with a white Z
    def f(d, k, big):
        W, H = big.size; bw, bh = W * w, H * h; x0, y0 = (W - bw) / 2, (H - bh) / 2; rad = bh * 0.45
        d.rounded_rectangle([x0 - k, y0 - k, x0 + bw + k, y0 + bh + k], rad + k, fill=(20, 18, 40, 255))
        for i in range(24):
            t = i / 23; inset = t * bh * 0.18
            d.rounded_rectangle([x0 + inset, y0 + inset * 0.7, x0 + bw - inset, y0 + bh - inset * 1.3], max(1, rad - inset),
                                fill=(int(70 + 60 * t), int(60 + 55 * t), int(150 + 70 * t), 255))
        fo = font(int(bh * 0.78)); tb = d.textbbox((0, 0), 'Z', font=fo)
        tx = W / 2 - (tb[0] + tb[2]) / 2; ty = H / 2 - (tb[1] + tb[3]) / 2
        d.text((tx + k * 0.8, ty + k * 0.8), 'Z', font=fo, fill=(20, 18, 40, 200)); d.text((tx, ty), 'Z', font=fo, fill=(245, 245, 255, 255))
    return ss(f, size)

def flash(size, light):  # the 06 flash glyph (mi02 dark, mi10 light)
    def f(d, k, big):
        W, H = big.size
        pts = [(0.62, 0.02), (0.18, 0.55), (0.46, 0.55), (0.30, 0.98), (0.84, 0.38), (0.54, 0.38), (0.72, 0.02)]
        P = [(x * W, y * H) for x, y in pts]
        d.polygon(P, fill=(225, 225, 230, 255) if light else (28, 28, 30, 255))
    return ss(f, size)

def cream_arrows(img):
    a = np.asarray(img).astype(float); lum = a[..., :3].mean(-1); m = a[..., 3] > 0
    if not m.any(): return img
    t = np.clip((lum - 40) / (0.75 * (lum[m].max() - 40) + 1e-6), 0, 1)[..., None]
    a[..., :3] = np.where(m[..., None], (1 - t) * np.array([20, 18, 14]) + t * np.array(CREAM), a[..., :3])
    return Image.fromarray(a.astype(np.uint8))


# ---------------------------------------------------------------- the pad (2005's GameCube loading screen 3)
def loading_pad(gc5):
    """the controller cut out of 'Big Play Control - Slides' (load3: 1024x512 DXT1 in the 2005 gc_icons)"""
    import cv2, struct
    raw = sheet(os.path.join(gc5, 'data', 'frontend', 'load3.big'), 'load3.xsh')
    o = entries(raw)[0][0][1]; w, h = struct.unpack_from('<HH', raw, o + 4)
    img = np.asarray(Image.frombytes('RGBA', (w, h), bytes(raw[o + 16:o + 16 + w * h // 2]), 'bcn', 1).convert('RGB'))
    img = img[120:460, 60:560].copy()
    rgb = img.astype(int); r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    indigo = (b > g + 18) & (b > r + 5) & (b > 45)
    box = np.zeros_like(indigo); box[30:280, 12:452] = True
    mask = np.full(img.shape[:2], cv2.GC_PR_BGD, np.uint8); mask[~box] = cv2.GC_BGD
    mask[indigo & box] = cv2.GC_PR_FGD; mask[nd.binary_erosion(indigo & box, iterations=3)] = cv2.GC_FGD
    cv2.setRNGSeed(0)
    cv2.grabCut(img[..., ::-1].copy(), mask, None, np.zeros((1, 65)), np.zeros((1, 65)), 10, cv2.GC_INIT_WITH_MASK)
    m = (mask == 1) | (mask == 3)
    m = nd.binary_opening(m, iterations=3); lab, n = nd.label(m); s = nd.sum(m, lab, range(1, n + 1))
    m = nd.binary_fill_holes(nd.binary_closing(lab == (np.argmax(s) + 1), iterations=3))
    pad = Image.fromarray(np.dstack([img, (nd.gaussian_filter(m.astype(float), 0.8) * 255).astype(np.uint8)]))
    return pad.crop(pad.getbbox())

def place(im, size, width, cy):
    s = width / im.width; p = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    out = Image.new('RGBA', size, (0, 0, 0, 0)); out.alpha_composite(p, ((size[0] - p.width) // 2, int(cy - p.height / 2)))
    return out

def dark_edge(im):
    a = np.asarray(im).astype(float); al = a[..., 3] / 255
    ring = np.clip(nd.maximum_filter(al, 3) - al, 0, 1)
    out = np.zeros_like(a); out[..., :3] = a[..., :3] * al[..., None] + 12 * (1 - al[..., None])
    out[..., 3] = np.clip(al + ring, 0, 1) * 255
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

def mask_ss(pad, size, k=4, close=4, blur=2.2):
    big = pad.resize((size[0] * k, size[1] * k), Image.LANCZOS); m = np.asarray(big)[..., 3] > 110
    m = nd.binary_fill_holes(nd.binary_closing(np.pad(m, 8 * k), iterations=close * k))[8 * k:-8 * k, 8 * k:-8 * k]
    return nd.gaussian_filter(m.astype(float), blur * k) > 0.5, k

def grown(pic, px, k=4):
    """pic's shape (its alpha) grown px pixels, as a white picture of the same size (outline_from and silhouette_from
    add 1 px of dark edge outside it)"""
    w, h = pic.size
    a = np.asarray(pic.resize((w * k, h * k), Image.LANCZOS))[..., 3] > 60
    a = nd.binary_dilation(nd.binary_fill_holes(a), iterations=px * k)
    out = np.zeros(a.shape + (4,), np.uint8); out[a] = (255, 255, 255, 255)
    return Image.fromarray(out).resize((w, h), Image.LANCZOS)

def outline_from(pad, size, **kw):
    m, k = mask_ss(pad, size, **kw); e3 = nd.binary_erosion(m, iterations=int(2.6 * k)); e4 = nd.binary_erosion(m, iterations=int(3.6 * k))
    white = m & ~e3; dark = (nd.binary_dilation(m, iterations=k) & ~m) | (e3 & ~e4)
    a = np.zeros(m.shape + (4,), np.uint8); a[dark] = (15, 15, 15, 255); a[white] = (232, 232, 232, 255)
    return Image.fromarray(a).resize(size, Image.LANCZOS)

def silhouette_from(pad, size, **kw):
    m, k = mask_ss(pad, size, **kw); a = np.zeros(m.shape + (4,), np.uint8)
    a[nd.binary_dilation(m, iterations=k)] = (20, 20, 20, 255); a[m] = (224, 224, 224, 255)
    sh = nd.binary_erosion(m, iterations=k) & ~nd.binary_erosion(m, iterations=3 * k); sh[:m.shape[0] // 2] = False
    a[sh] = (200, 200, 200, 255)
    return Image.fromarray(a).resize(size, Image.LANCZOS)


# ---------------------------------------------------------------- help icons
def help_pictures(G5, pad):
    E = {}
    for n in ('bu00', 'bu04', 'bu05', 'bu06', 'bu07', 'bp04', 'bp05', 'bp06', 'bp07'):
        E[n] = G5[n]
    # by job (virtual button): the Xbox B slot shows GameCube X, the X slot B, the Y slot Y (2005's sheet: bu01 B,
    # bu02 Y, bu03 X)
    E['bu01'], E['bu02'], E['bu03'] = G5['bu03'], G5['bu01'], G5['bu02']
    # START ending where the Xbox's buttons end (x 26 of 32: the label starts just past it, pause's START Resume),
    # free to the left, so it isn't smaller than the buttons beside it
    for n in ('bq00', 'bq01'):
        p = bbox_crop(G5[n]); s = min(27 / p.width, 26 / p.height)
        p = p.resize((round(p.width * s), round(p.height * s)), Image.LANCZOS); c = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
        c.alpha_composite(p, (27 - p.width, (32 - p.height) // 2)); E[n] = c
    # the kidney buttons no taller or wider than 25 px (2005's X was 30 tall, and stood out beside an Xbox-sized row)
    for n in ('bu01', 'bu03'):
        E[n] = fit(E[n], (25, 25), grow=False); c = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
        c.alpha_composite(E[n], (4, 3)); E[n] = c
    E['gpad'] = dark_edge(place(pad, (64, 64), 42, 33))  # the Xbox pad's width: four sit side by side on team select
    g2 = np.asarray(E['gpad']).copy(); g2[..., 3] = (g2[..., 3] * 0.48).astype(np.uint8); E['gpa2'] = Image.fromarray(g2)
    # the silhouette (drawn under each pad on Select Controller) and the CPU outline: the pad's own shape grown 3 px
    # all round, as the Xbox's are (its gpco/gpdx are its gpad's bounds plus 3), so only a rim shows round the pad
    shape = grown(E['gpad'], 2)  # (lightly smoothed, so the dip between the handles stays)
    E['gpdx'] = outline_from(shape, (64, 64), close=1, blur=0.8); E['gpco'] = silhouette_from(shape, (64, 64), close=1, blur=0.8)
    E['bq08'] = stick((32, 32), 'control'); E['bq09'] = stick((32, 32), 'c')
    E['mi02'] = flash((16, 16), False); E['mi10'] = flash((16, 16), True)
    E['bu09'] = z_button((32, 32)); E['bu08'] = z_button((64, 64), 0.8, 0.46)
    return E

def help_icons(xb, G5, pad):
    xh = sheet(os.path.join(xb, 'frontend', 'shared.big'), 'helpbuts.xsh')
    E = help_pictures(G5, pad)
    for n, off in entries(xh)[0]:
        if n not in E:
            print('  helpbuts: no GameCube picture for %s, the Xbox one stays' % n); continue
        w, h = decode_xbox(xh, off).size
        pic = E[n] if E[n].size == (w, h) else fit(E[n], (w, h))
        xh = encode_xbox_into(xh, off, pic.convert('RGBA'))
    return xh


# ---------------------------------------------------------------- pitch select
GC05_OFF = {'A': (0.5, 21), 'X': (-23, 0), 'B': (26.5, 1.5), 'Y': (1, -25)}  # by the Xbox slot each GameCube button takes
GC05_SIZE = {'A': 36, 'B': 29, 'X': 32, 'Y': 32}  # on the Xbox spots, a little under 2005's 38/34 (GameCube X, on
#                                                    the Xbox B spot, a little smaller: James, v13)
NUDGE = {'Y': (0, -3), 'B': (-2, 0)}  # Y up a little; GameCube X (Xbox B spot) in toward the hub (James, v13)
SLOT_PIC = {'A': 'bu00', 'B': 'bu03', 'X': 'bu01', 'Y': 'bu02'}  # Xbox B's jobs on GameCube X, Xbox X's on B (2005)
SPREAD = 0.9                                                       # option A: 90% of 2005's GameCube spacing
MAIN = dict(sx=17.25, sy=19.0, d=19.0)                             # the Xbox 06 igonly pictures' button spacing/size

def xbox_buttons(img):
    """the Xbox face buttons: {'A'|'B'|'X'|'Y': (cx, cy, diameter)}, from each coloured disc's box"""
    a = np.asarray(img).astype(int); r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    sel = {'A': (g > r + 30) & (g > b + 20), 'B': (r > g + 50) & (r > b + 50), 'X': (b > r + 40) & (b > g + 20), 'Y': (r > b + 60) & (g > b + 60)}
    out = {}
    for k, s in sel.items():
        m = nd.binary_fill_holes(nd.binary_closing(nd.binary_opening(s & (al > 150)), iterations=3)); lab, n = nd.label(m)
        if not n: continue
        sz = nd.sum(m, lab, range(1, n + 1)); i = int(np.argmax(sz)) + 1
        if sz[i - 1] < 25: continue
        ys, xs = np.where(lab == i)
        out[k] = ((xs.min() + xs.max() + 1) / 2, (ys.min() + ys.max() + 1) / 2, max(xs.max() - xs.min(), ys.max() - ys.min()) + 1)
    return out

def hub_columns(img):
    a = np.asarray(img)[..., 3]; ys = np.where((a > 128).any(1))[0]; row = a[ys.max() - 6]
    xs = np.where(row > 128)[0]
    runs = np.split(xs, np.where(np.diff(xs) > 1)[0] + 1)
    run = min(runs, key=lambda r: r[0])  # the vertical piece: the leftmost run at the bottom
    return int(run[0]), int(run[-1])

def refill(img, mask, hub):
    """the old buttons' pixels refilled: the bars from their own part of the cross (same row), the hub's inside with
    that row's flat hub colour (rows with none interpolated)"""
    a = np.asarray(img).copy(); H, W = mask.shape
    reg = np.zeros(W, int); reg[hub[0]:hub[1] + 1] = 1; reg[hub[1] + 1:] = 2
    for y in range(H):
        for x in np.where(mask[y])[0]:
            ok = np.where(~mask[y] & (a[y, :, 3] > 200) & (reg == reg[x]))[0]
            if len(ok): a[y, x] = a[y, ok[np.argmin(abs(ok - x))]]
    src = np.asarray(img).astype(float); x0, x1 = hub[0] + 3, hub[1] - 1; vals = {}
    for y in range(H):
        row = src[y, x0:x1]; lum = row[:, :3].mean(-1)
        ok = ~mask[y, x0:x1] & (row[:, 3] > 200) & (lum > 45) & (lum < 115) & ((row[:, :3].max(-1) - row[:, :3].min(-1)) < 30)
        if ok.sum() >= 3: vals[y] = np.median(row[ok], axis=0)
    if vals:
        ys = np.array(sorted(vals)); V = np.array([vals[y] for y in ys])
        for y in range(H):
            sel = mask[y, x0:x1] & (src[y, x0:x1, 3] > 200)
            if not sel.any(): continue
            cur = a[y, x0:x1].astype(float)
            hubpx = sel & ~((cur[:, :3].mean(-1) >= 130) & ((cur[:, :3].max(-1) - cur[:, :3].min(-1)) < 30))  # all but bar white
            cur[hubpx] = [np.interp(y, ys, V[:, i]) for i in range(4)]; a[y, x0:x1] = cur.astype(np.uint8)
    return Image.fromarray(a)

def pitch_cross(pics, G5):
    """ps00-ps03 with the GameCube buttons; pics: the Xbox sheet's own pictures"""
    B2 = xbox_buttons(pics['ps02'])
    sx = (B2['B'][0] - B2['X'][0]) / 2; sy = (B2['A'][1] - B2['Y'][1]) / 2
    d = np.mean([v[2] for v in B2.values()])
    centre = (B2['A'][0], (B2['B'][1] + B2['X'][1]) / 2)
    fx, fy, fs = sx / MAIN['sx'], sy / MAIN['sy'], d / MAIN['d']
    hub = hub_columns(pics['ps02'])
    out = {}
    for n in ('ps00', 'ps01', 'ps02', 'ps03'):
        base = pics[n].copy(); btn = xbox_buttons(base)
        H, W = base.height, base.width; yy, xx = np.mgrid[:H, :W]; m = np.zeros((H, W), bool)
        for cx, cy, dd in btn.values(): m |= (xx - cx) ** 2 + (yy - cy) ** 2 <= (dd / 2 + 3.5) ** 2
        a0 = np.asarray(base).astype(int); sat = (a0[..., :3].max(-1) - a0[..., :3].min(-1)) > 50
        stray = nd.binary_dilation(sat & (a0[..., 3] > 0), iterations=1); stray[:, :hub[0]] = False; stray[:, hub[1] + 1:] = False
        base = refill(base, m | stray, hub)   # and any coloured edge pixel of the old buttons left in the hub
        if n == 'ps03':  # the fifth pitch: the Xbox's black-button tile (bottom right) to the top right with R
            a = np.asarray(base).copy(); right = hub[1] + 1
            wid = (a[:, right:, 3] > 0).sum(1); full = wid.max()
            y = H - 1
            while y >= 0 and wid[y] == 0: y -= 1
            bottom = y
            while y >= 0 and wid[y] < 0.6 * full: y -= 1            # the tile's slanted foot
            while y >= 0 and wid[y] >= 0.6 * full: y -= 1           # the tile, from the bottom up
            tile_top = y + 1
            while y >= 0 and wid[y] < 0.6 * full: y -= 1            # the ball above it (and any gap)
            gone_top = y + 1
            tile = Image.fromarray(a[tile_top:bottom + 1, right:].copy()).transpose(Image.FLIP_TOP_BOTTOM)
            a[gone_top:, right:] = 0; base = Image.fromarray(a)
            base.alpha_composite(tile, (right, 0))
            # R tucked right under the tile, touching it, as PS2 06 puts R1 and 2005's GameCube its R (the picture's
            # own empty margin cropped, so it doesn't float below)
            rsz = (round(30 * fs), round(22 * fs)); r = bbox_crop(fit(G5['bu05'], rsz))
            tb = tile.getbbox()
            base.alpha_composite(r, (right + (tb[0] + tb[2] - r.width) // 2, tb[3] - 2))
        for k in ('Y', 'X', 'B', 'A'):  # A last, on top, as 2005
            if k not in btn: continue
            cx, cy = btn[k][0], btn[k][1]  # the Xbox button's own spot: the pitch names sit just beyond it
            dx, dy = NUDGE.get(k, (0, 0)); cx += dx * fs; cy += dy * fs
            sz = round(GC05_SIZE[k] * fs); ic = G5[SLOT_PIC[k]].resize((sz, sz), Image.LANCZOS)
            base.alpha_composite(ic, (int(round(cx - sz / 2)), int(round(cy - sz / 2))))
        out[n] = base
    return out

def pick(xpick, OG):
    pk = xpick.copy(); a = np.asarray(pk).copy(); cut = round(xpick.height * 27 / 44); a[cut:, :, 3] = 0; pk = Image.fromarray(a)
    lm = fit(bbox_crop(OG['pick'].crop((0, 27, 44, 41))), (round(30 * xpick.width / 46), round(16 * xpick.height / 44)))
    pk.alpha_composite(lm, ((pk.width - lm.width) // 2, cut)); return pk

def direction_pictures(pics):
    out = {}
    for i in range(10, 22):
        n = 'bu%02d' % i
        if n not in pics: continue
        a = np.asarray(pics[n]).astype(int); W = a.shape[1]
        yel = (a[..., 0] > 150) & (a[..., 1] > 150) & (a[..., 2] < 110) & (a[..., 3] > 150)
        if yel.sum() > 20:
            ys, xs = np.where(yel); dx, dy = xs.mean() - W / 2, ys.mean() - a.shape[0] / 2
            lit = ('right' if dx > 0 else 'left') if abs(dx) > abs(dy) else ('down' if dy > 0 else 'up')
            out[n] = dpad(pics[n].size, lit); continue
        m = a[..., 3] > 40; dist = nd.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
        cy, cx = np.unravel_index(np.argmax(dist), dist.shape); rad = dist.max()
        yy, xx = np.mgrid[:a.shape[0], :W]; disc = (xx - cx) ** 2 + (yy - cy) ** 2 <= (rad + 1.5) ** 2
        b = a.astype(np.uint8).copy(); b[disc] = 0; im = cream_arrows(Image.fromarray(b))
        sz = int(round(2 * rad + 3))
        im.alpha_composite(stick((sz, sz), 'c' if i <= 13 else 'control'), (int(round(cx + 0.5 - sz / 2)), int(round(cy + 0.5 - sz / 2))))
        out[n] = im
    return out

def overlay_sheets(xb, gc5, archive, G5, OG, GR):
    xi_raw = sheet(os.path.join(xb, 'frontend', archive), 'ingameov.xsh')
    off, a, rec = atlas(xi_raw); pics = {n: a.crop((x, y, x + w, y + h)) for n, (x, y, w, h) in rec.items()}
    new = pitch_cross(pics, G5)
    if 'pick' in pics: new['pick'] = pick(pics['pick'], OG)
    new.update(direction_pictures(pics))
    for n, p in new.items():
        x, y, w, h = rec[n]
        a.paste(Image.new('RGBA', (w, h), (0, 0, 0, 0)), (x, y)); a.alpha_composite(p.convert('RGBA'), (x, y))
    print('  %s ingameov: %s' % (archive, ' '.join(sorted(new))))
    res = {'ingameov.xsh': encode_xbox_into(xi_raw, off, a)}
    xr_raw = sheet(os.path.join(xb, 'frontend', archive), 'replay.xsh')
    roff, r, rrec = atlas(xr_raw)
    if 'rep1' in rrec and 'rep1' in GR and GR['rep1'].size == rrec['rep1'][2:]:
        x, y, w, h = rrec['rep1']
        r.paste(Image.new('RGBA', (w, h), (0, 0, 0, 0)), (x, y)); r.alpha_composite(GR['rep1'], (x, y))
        res['replay.xsh'] = encode_xbox_into(xr_raw, roff, r); print('  %s replay: rep1' % archive)
    return res


def diamonds(xb, gc5):
    cr_raw = open(os.path.join(xb, 'igshapes', 'igcrsr.xsh'), 'rb').read()
    g5 = open(os.path.join(gc5, 'data', 'igshapes', 'igcrsr.xsh'), 'rb').read()
    coff, c, crec = atlas(cr_raw); _, g, grec = atlas(g5)
    # 06 picks each base's picture by the channel of the button bound to it (PXB + the Xbox letter: the PS2 build's
    # Square/Triangle/Circle show right that way); the GameCube buttons sit on the Xbox channels of their own letters,
    # so each name takes its letter: 2005's sheet held them by base (PXBX B, PXBB X)
    for n, g5 in (('PXBX', 'PXBB'), ('PXBY', 'PXBY'), ('PXBB', 'PXBX')):
        x, y, w, h = grec[g5]; X, Y, W, H = crec[n]
        assert (w, h) == (W, H), n
        c.paste(Image.new('RGBA', (W, H), (0, 0, 0, 0)), (X, Y)); c.alpha_composite(g.crop((x, y, x + w, y + h)), (X, Y))
    return encode_xbox_into(cr_raw, coff, c)


# ---------------------------------------------------------------- layouts
def keep_online(fel):
    """online and voice chat labels: the GameCube flag set to the Xbox's, so they stay as they are"""
    out = []
    for l in fel.split(b'\n'):
        v = l.split(b',')
        if len(v) > 10 and all(x in (b'0', b'1') for x in v[7:11]) and ONLINE.search(v[0].split(b':')[-1]):
            v[10] = v[9]; l = b','.join(v)
        out.append(l)
    return b'\n'.join(out)

def nav_lists(fel):
    """inside the Xbox nav bars, each icon list in the GameCube menus' order (NAV_LIST)"""
    L = fel.split(b'\n'); out = []; inside = None
    for l in L:
        d = len(l) - len(l.lstrip(b' ')); st = l.strip()
        if inside is not None and st and d <= inside: inside = None
        if st.split(b',')[0].split(b':')[-1] in NAV_GROUPS and st.startswith(b'GR:'): inside = d
        elif inside is not None and st.rstrip(b'\r') in NAV_LIST:
            cr = b'\r' if l.endswith(b'\r') else b''
            l = l[:d] + NAV_LIST[st.rstrip(b'\r')] + cr
        out.append(l)
    return b'\n'.join(out)


def details_x(fel, name=''):
    """the menus' DETAILS button (pause Show Info, the option, roster and tuning menus): the Xbox's Y there is
    action 0x004, which 2005's GameCube (and so this table) does with X: its picture taken as the nav bars take
    theirs (NAV_LIST: bu03 -> bu01, the X picture)"""
    L = fel.split(b'\n'); out = []; inside = None
    for l in L:
        d = len(l) - len(l.lstrip(b' ')); st = l.strip()
        if inside is not None and st and d <= inside: inside = None
        if st.startswith((b'GR:DETAILS,', b'GG:DETAILS,')) or (name == 'fes_ballpark_hud.fel' and st.startswith(b'GR:BOTTOM,')):
            inside = d  # (the ballpark editor's Reset, the Xbox's Y, is X too)
        elif inside is not None and st.startswith(b'SH:'):  # an icon the Xbox draws (SH:XBOX; the editor's SH:BUTTON1)
            v = l.rstrip(b'\r').split(b','); cr = b'\r' if l.endswith(b'\r') else b''
            key = b'SE:' + v[12] if len(v) > 12 else b''
            if len(v) > 12 and v[9].strip() == b'1' and key in NAV_LIST: v[12] = NAV_LIST[key][3:]; l = b','.join(v) + cr
        out.append(l)
    return b'\n'.join(out)


def layouts(path):
    if not os.path.exists(path): return None
    res = {}
    for n, b in read_big(path):
        if not n.endswith('.fel'): continue
        t = unpack(b)
        t2, log = as_platform(nav_lists(keep_online(t)), 'gc', skip=NAV_GROUPS, swap=GC_SWAP, strict='leaves')
        t2 = details_x(t2, n)
        if t2 != t: res[n] = t2
        for x in log:
            if 'takes' in x or 'lacks' in x or 'draws' in x: print('  %s %s: %s' % (os.path.basename(path), n, x))
    return res


def main():
    if len(sys.argv) != 4: raise SystemExit(__doc__)
    xb, gc5, out = sys.argv[1:]
    if not os.path.isdir(os.path.join(gc5, 'data', 'frontend')):
        raise SystemExit('%s is not a gc_icons folder (no data\\frontend in it)' % gc5)
    G5 = {n: decode_xbox(raw, o) for raw in [sheet(os.path.join(gc5, 'data', 'frontend', 'shared.big'), 'helpbuts.xsh')]
          for n, o in entries(raw)[0]}
    gi = os.path.join(gc5, 'data', 'frontend', 'igonly.big')
    OG = crops(sheet(gi, 'ingameov.xsh')); GR = crops(sheet(gi, 'replay.xsh'))
    print('the pad from the 2005 loading screen...')
    pad = loading_pad(gc5)
    rep = {'shared.big': {'helpbuts.xsh': help_icons(xb, G5, pad)}}
    for archive in ('igonly.big', 'coopov.big'):
        if os.path.exists(os.path.join(xb, 'frontend', archive)):
            rep[archive] = overlay_sheets(xb, gc5, archive, G5, OG, GR)
    print('layouts:')
    make_icons.KNOWN_PICTURES = make_icons.picture_names(xb)
    for archive in LAYOUT_ARCHIVES:
        r = layouts(os.path.join(xb, 'frontend', archive))
        if r is None: print('  no %s in the Xbox data folder' % archive)
        elif r: rep[archive] = {**rep.get(archive, {}), **r}
    pack.MAXTRIES = 1024
    os.makedirs(os.path.join(out, 'data', 'frontend'), exist_ok=True)
    for name, files_new in rep.items():
        files = []
        for n, b in read_big(os.path.join(xb, 'frontend', name)):
            if n in files_new:
                c = pack.refpack(files_new[n]); assert unrefpack(c) == files_new[n]; files.append((n, c))
            else:
                files.append((n, b))
        dst = os.path.join(out, 'data', 'frontend', name)
        pack.write_big(dst, files)
        print('wrote', dst, '(%d files changed)' % len(files_new))
    os.makedirs(os.path.join(out, 'data', 'igshapes'), exist_ok=True)
    dst = os.path.join(out, 'data', 'igshapes', 'igcrsr.xsh')
    open(dst, 'wb').write(diamonds(xb, gc5)); print('wrote', dst)


if __name__ == '__main__':
    main()
