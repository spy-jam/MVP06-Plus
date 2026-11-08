import os, struct, sys, tempfile, random
sys.path.insert(0, sys.argv[1])
import discs
GC05_FILES = ["data/frontend/shared.big", "data/frontend/igonly.big"] + [f"data/frontend/load{i}.big" for i in range(8)] + ["data/igshapes/igcrsr.gsh"]
S = 2048
tmp = tempfile.mkdtemp()
rnd = random.Random(1)
def blob(n): return bytes(rnd.getrandbits(8) for _ in range(n))

def xbe(title):
    b = bytearray(0x1000); b[:4] = b"XBEH"
    struct.pack_into("<I", b, 0x104, 0x10000); struct.pack_into("<I", b, 0x118, 0x10000 + 0x200)
    struct.pack_into("<I", b, 0x200 + 8, title); b[0x200+12:0x200+12+30] = "MVP Baseball 2005".encode("utf-16le")[:30]
    return bytes(b)

# ---- XDVDFS: tree of dirs, files in a binary tree
def xiso(tree, base):
    img = bytearray(base + 34 * S)
    def alloc(data):
        nonlocal img
        sec = (len(img) + S - 1) // S; img += b"\0" * (sec * S - len(img)); img += data; return sec
    def dirtable(d):
        names = sorted(d, key=str.lower); recs = []
        for nm in names:
            v = d[nm]
            if isinstance(v, dict):
                t = dirtable(v); sec = alloc(t) if t else 0; recs.append((nm, sec, len(t), 0x10))
            else: recs.append((nm, alloc(v), len(v), 0x20))
        # balanced tree: entries laid out in order, left/right indices
        offs = []; o = 0
        for nm, *_ in recs: offs.append(o); o += (14 + len(nm) + 3) & ~3
        t = bytearray(o)
        def build(lo, hi):
            if lo >= hi: return None
            mid = (lo + hi) // 2; l = build(lo, mid); r = build(mid + 1, hi)
            nm, sec, ln, at = recs[mid]
            struct.pack_into("<HHIIBB", t, offs[mid], (offs[l]//4) if l is not None else 0, (offs[r]//4) if r is not None else 0, sec, ln, at, len(nm))
            t[offs[mid]+14:offs[mid]+14+len(nm)] = nm.encode(); return mid
        root = build(0, len(recs))
        if root != 0:  # root of the tree must be at offset 0: swap layout by rotating -- simpler: put root first
            pass
        return bytes(t), root
    # simpler: write each dir with the tree root first by ordering recs as preorder
    def dirtable2(d):
        names = sorted(d, key=str.lower)
        recs = []
        for nm in names:
            v = d[nm]
            if isinstance(v, dict):
                t = dirtable2(v); sec = alloc(t) if t else 0; recs.append([nm, sec, len(t), 0x10])
            else: recs.append([nm, alloc(v), len(v), 0x20])
        order = []
        def pre(lo, hi):
            if lo >= hi: return None
            mid = (lo + hi)//2; i = len(order); order.append([mid, None, None])
            order[i][1] = pre(lo, mid); order[i][2] = pre(mid+1, hi); return i
        pre(0, len(recs))
        offs = []; o = 0
        for m, *_ in order:
            sz = (14 + len(recs[m][0]) + 3) & ~3
            if o // S != (o + sz - 1) // S: o = (o // S + 1) * S  # don't straddle a sector
            offs.append(o); o += sz
        t = bytearray(b"\xff" * o)
        for i, (m, l, r) in enumerate(order):
            nm, sec, ln, at = recs[m]
            struct.pack_into("<HHIIBB", t, offs[i], offs[l]//4 if l is not None else 0, offs[r]//4 if r is not None else 0, sec, ln, at, len(nm))
            t[offs[i]+14:offs[i]+14+len(nm)] = nm.encode()
        return bytes(t)
    root = dirtable2(tree); rs = alloc(root)
    vd = bytearray(S); vd[:20] = discs.XDVDFS_MAGIC; struct.pack_into("<II", vd, 20, rs - base // S, len(root)); vd[0x7EC:] = discs.XDVDFS_MAGIC
    # sectors relative to partition: re-pack entries relative too -> simpler: base aligned, store absolute-base
    return img, vd

# files relative to the partition need sector numbers relative to base; easiest: build at base 0 then prepend padding
def make_xbox(tree, base):
    img, vd = xiso(tree, 0); img[32*S:33*S] = vd
    return b"\0" * base + bytes(img)

files = {"default.xbe": xbe(discs.XBOX_TITLE), "data": {"frontend": {"shared.big": blob(5000), "igonly.big": blob(3000), **{f"load{i}.big": blob(100+i) for i in range(8)}}, "igshapes": {"igcrsr.xsh": blob(77)}}, "Empty": {}}
files["data"]["many"] = {f"f{i:03d}.bin": blob(10) for i in range(300)}
def flat(d, p=""):
    for k, v in d.items():
        if isinstance(v, dict): yield from flat(v, p + k.lower() + "/")
        else: yield p + k.lower(), v
want = dict(flat(files))
for base in (0, 0x2080000):
    p = os.path.join(tmp, f"x{base}.iso"); open(p, "wb").write(make_xbox(files, base))
    with discs.open_xbox(p) as d:
        assert set(d.files()) == set(want), set(want) ^ set(d.files())
        for k, v in want.items(): assert d.read(k) == v, k
        d.copy("data/frontend/shared.big", os.path.join(tmp, "o", "s.big")); assert open(os.path.join(tmp,"o","s.big"),"rb").read() == want["data/frontend/shared.big"]
    print("xbox ok at", hex(base))
bad = dict(files); bad["default.xbe"] = xbe(0x45410056); p = os.path.join(tmp, "bad.iso"); open(p, "wb").write(make_xbox(bad, 0))
try: discs.open_xbox(p); print("FAIL no title check")
except discs.DiscError as e: print("xbox title check:", e)

# ---- GCM
def gcm(tree, gid):
    entries = []; names = bytearray()
    data_parts = []; data_off = [0x100000]
    def add(d, parent):
        for k in sorted(d):
            v = d[k]; no = len(names); names.extend(k.encode() + b"\0")
            if isinstance(v, dict):
                i = len(entries); entries.append([1 << 24 | no, parent, 0]); add(v, i); entries[i][2] = len(entries)
            else:
                entries.append([no, data_off[0], len(v)]); data_parts.append((data_off[0], v)); data_off[0] += (len(v) + 31) & ~31
    entries.append([1 << 24, 0, 0]); names_root = None
    add(tree, 0); entries[0][2] = len(entries)
    fst = b"".join(struct.pack(">III", *e) for e in entries) + bytes(names)
    img = bytearray(data_off[0] + len(fst) + 64)
    img[:6] = gid; struct.pack_into(">I", img, 0x1C, 0xC2339F3D); img[0x20:0x30] = b"MVP Baseball 05\0"
    fo = data_off[0]; struct.pack_into(">II", img, 0x424, fo, len(fst)); img[fo:fo+len(fst)] = fst
    for o, v in data_parts: img[o:o+len(v)] = v
    return bytes(img)
gtree = {"data": {"frontend": {"shared.big": blob(4000), "igonly.big": blob(100), **{f"load{i}.big": blob(50+i) for i in range(8)}}, "igshapes": {"igcrsr.gsh": blob(33)}, "zz": {}}, "opening.bnr": blob(9)}
p = os.path.join(tmp, "g.iso"); open(p, "wb").write(gcm(gtree, b"GV4E69"))
with discs.open_gamecube(p) as d:
    gw = dict(flat(gtree)); assert set(d.files()) == set(gw), set(gw) ^ set(d.files())
    for k, v in gw.items(): assert d.read(k) == v
    out = os.path.join(tmp, "gco"); discs.extract(d, GC05_FILES, out)
    assert open(os.path.join(out, "data", "igshapes", "igcrsr.gsh"), "rb").read() == gw["data/igshapes/igcrsr.gsh"]
print("gamecube ok, extracted", len(GC05_FILES))
p = os.path.join(tmp, "g2.iso"); open(p, "wb").write(gcm(gtree, b"GMBE8P"))
try: discs.open_gamecube(p); print("FAIL")
except discs.DiscError as e: print("gc id check:", e)

# ---- ISO 9660
def iso(tree):
    img = bytearray(18 * S)
    def alloc(data):
        nonlocal img
        sec = len(img) // S; img += data + b"\0" * (-len(data) % S); return sec
    def rec(name, ext, size, isdir):
        n = 33 + len(name); n += n & 1
        r = bytearray(n); r[0] = n; struct.pack_into("<I", r, 2, ext); struct.pack_into(">I", r, 6, ext)
        struct.pack_into("<I", r, 10, size); struct.pack_into(">I", r, 14, size); r[25] = 2 if isdir else 0; r[32] = len(name); r[33:33+len(name)] = name
        return bytes(r)
    def dodir(d, parent):
        kids = []
        for k in sorted(d):
            v = d[k]
            if isinstance(v, dict): kids.append(rec(k.encode(), *dodir(v, None), True))
            else: kids.append(rec(k.encode() + b";1", alloc(v), len(v), False))
        # pack into sectors
        body = bytearray(); recs = [rec(b"\0", 0, 0, True), rec(b"\1", 0, 0, True)] + kids
        for r in recs:
            if len(body) // S != (len(body) + len(r) - 1) // S: body += b"\0" * (-len(body) % S)
            body += r
        body += b"\0" * (-len(body) % S)
        return alloc(bytes(body)), len(body)
    ext, size = dodir(tree, None)
    pvd = bytearray(S); pvd[0] = 1; pvd[1:6] = b"CD001"; pvd[156:190] = rec(b"\0", ext, size, True)
    img[16*S:17*S] = pvd; return bytes(img)
ptree = {"SYSTEM.CNF": ("BOOT2 = cdrom0:\\" + discs.PS2_SERIAL + ";1\r\nVER = 1.00\r\n").encode(), "DATA": {"FRONTEND": {"SHARED.BIG": blob(7000), "IGONLY.BIG": blob(30), "COOPOV.BIG": blob(40), **{f"LOAD{i}.BIG": blob(20+i) for i in range(8)}, **{f"X{i:03d}.DAT": blob(3) for i in range(120)}}, "IGSHAPES": {"IGCRSR.SSH": blob(12)}}}
p = os.path.join(tmp, "p.iso"); open(p, "wb").write(iso(ptree))
with discs.open_ps2(p) as d:
    pw = dict(flat(ptree)); assert set(d.files()) == set(pw), set(pw) ^ set(d.files())
    for k, v in pw.items(): assert d.read(k) == v
    out = os.path.join(tmp, "pso"); discs.extract(d, discs.PS2_ART_FILES, out, upper=True)
    assert open(os.path.join(out, "DATA", "FRONTEND", "SHARED.BIG"), "rb").read() == pw["data/frontend/shared.big"]
print("ps2 ok")
ptree["SYSTEM.CNF"] = b"BOOT2 = cdrom0:\\SLUS_211.35;1\r\n"; p = os.path.join(tmp, "p2.iso"); open(p, "wb").write(iso(ptree))
try: discs.open_ps2(p); print("FAIL")
except discs.DiscError as e: print("ps2 serial check:", e)
# truncated image
open(p, "wb").write(iso(ptree)[:17*S+100])
try: discs.open_ps2(p); print("FAIL")
except discs.DiscError as e: print("truncated:", e)

# ---- compressed GameCube images: .gcz and .ciso read directly
import zlib
img = gcm(gtree, b"GV4E69")
def make_gcz(img, bs=0x4000):
    n = (len(img) + bs - 1) // bs
    ptrs, data = [], bytearray()
    for i in range(n):
        raw = img[i * bs:(i + 1) * bs].ljust(bs, b"\0")
        z = zlib.compress(raw)
        ptrs.append(len(data) | ((1 << 63) if len(z) >= len(raw) else 0))
        data += raw if len(z) >= len(raw) else z
    return struct.pack("<IIQQII", 0xB10BC001, 0, len(data), len(img), bs, n) + struct.pack(f"<{n}Q", *ptrs) + bytes(4 * n) + data
def make_ciso(img, bs=0x8000):
    n = (len(img) + bs - 1) // bs
    used, data = bytearray(0x8000 - 8), bytearray()
    for i in range(n):
        raw = img[i * bs:(i + 1) * bs].ljust(bs, b"\0")
        if any(raw):
            used[i] = 1; data += raw
    return b"CISO" + struct.pack("<I", bs) + bytes(used) + bytes(data)
gw = dict(flat(gtree))
for ext, maker in ((".gcz", make_gcz), (".ciso", make_ciso)):
    p = os.path.join(tmp, "g" + ext); open(p, "wb").write(maker(img))
    with discs.open_gamecube(p) as d:
        assert set(d.files()) == set(gw), set(gw) ^ set(d.files())
        for k, v in gw.items(): assert d.read(k) == v, (ext, k)
        out = os.path.join(tmp, "o" + ext); discs.extract(d, GC05_FILES, out)
    print("gamecube", ext, "ok,", os.path.getsize(p), "bytes for", len(img))

# ---- .rvz needs DolphinTool: found in a usual folder, or ToolMissing
home = os.path.join(tmp, "home"); os.makedirs(os.path.join(home, "Downloads"))
old = dict(os.environ); os.environ.update(HOME=home, USERPROFILE=home, PATH=tmp)
for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"): os.environ.pop(v, None)
try:
    p = os.path.join(tmp, "g.rvz"); open(p, "wb").write(b"RVZ\x01" + bytes(100))
    try: discs.open_gamecube(p); print("FAIL no ToolMissing")
    except discs.ToolMissing as e: print("rvz without Dolphin:", e.exe)
    t = os.path.join(home, "Downloads", "dolphin-2412-x64", "Dolphin-x64", "DolphinTool.exe")
    os.makedirs(os.path.dirname(t)); open(t, "w").close()
    print("found:", os.path.relpath(discs.find_tool("dolphin"), home))
finally:
    os.environ.clear(); os.environ.update(old)
