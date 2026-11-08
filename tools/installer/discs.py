"""Reading the three discs' file systems, with nothing but Python.

Xbox:      XDVDFS, in a Redump image (game partition after the video one), an xiso, or an extracted folder.
GameCube:  GCM with its FST (.iso / .gcm); .rvz / .gcz / .ciso / .wia are converted first by DolphinTool.
PS2:       ISO 9660 (.iso); .chd is converted first by chdman.

Each reader gives `files()` (path -> (offset, size), paths lower case with '/') and `read(path)` / `copy(path, dest)`,
so only the files that are asked for are read from a disc.
"""
import os
import shutil
import struct
import subprocess
import tempfile

XBOX_TITLE = 0x4541008D   # MVP 06 NCAA Baseball (EA, 0x8D)
GC_GAME_ID = b"GV4E69"    # MVP Baseball 2005: there was no GameCube MVP 06 (the reader stays for other uses)
PS2_SERIAL = "SLUS_213.67"
GAME_NAME = "MVP 06 NCAA Baseball"

SECTOR = 2048
CHUNK = 1 << 20


class DiscError(Exception):
    pass


class Image:
    """A disc image file; subclasses fill self.entries {path: (offset, size)}."""

    def __init__(self, path, f=None):
        """f: a file-like object to read instead of the file itself (a compressed image's contents)."""
        self.path = path
        self.f = f or open(path, "rb")
        self.size = f.size if f is not None else os.fstat(self.f.fileno()).st_size
        self.entries = {}

    def close(self):
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def at(self, off, n):
        self.f.seek(off)
        b = self.f.read(n)
        if len(b) != n:
            raise DiscError(f"{os.path.basename(self.path)} ends early (wanted {n} bytes at {off:#x}): incomplete image?")
        return b

    def files(self):
        return self.entries

    def find(self, path):
        e = self.entries.get(path.replace("\\", "/").lower().strip("/"))
        if e is None:
            raise DiscError(f"{path} isn't on {os.path.basename(self.path)}")
        return e

    def read(self, path):
        off, n = self.find(path)
        return self.at(off, n)

    def copy(self, path, dest, progress=None):
        off, n = self.find(path)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        self.f.seek(off)
        left = n
        with open(dest + ".part", "wb") as o:
            while left:
                b = self.f.read(min(CHUNK, left))
                if not b:
                    raise DiscError(f"{os.path.basename(self.path)} ends inside {path}: incomplete image?")
                o.write(b)
                left -= len(b)
                if progress:
                    progress(len(b))
        os.replace(dest + ".part", dest)


# ---------------------------------------------------------------- Xbox (XDVDFS)

XDVDFS_MAGIC = b"MICROSOFT*XBOX*MEDIA"
# where the game partition starts: an xiso, then Redump images of XGD1, XGD2, XGD3 discs
XBOX_PARTITIONS = (0, 0x18300000, 0xFD90000, 0x2080000)


class XboxImage(Image):
    def __init__(self, path):
        super().__init__(path)
        for base in XBOX_PARTITIONS:
            vd = base + 32 * SECTOR
            if vd + SECTOR > self.size:
                continue
            h = self.at(vd, SECTOR)
            if h[:20] == XDVDFS_MAGIC and h[0x7EC:0x800] == XDVDFS_MAGIC:
                self.base = base
                root, rsize = struct.unpack_from("<II", h, 20)
                self._walk(root, rsize, "", set())
                break
        else:
            raise DiscError(f"{os.path.basename(path)} isn't an Xbox disc image (no XDVDFS volume found)")

    def _walk(self, sector, size, prefix, seen):
        if size == 0 or sector in seen:
            return
        seen.add(sector)
        table = self.at(self.base + sector * SECTOR, size)
        todo = [0]
        while todo:
            o = todo.pop()
            if o + 14 > len(table):
                continue
            left, right, start, length, attr, nlen = struct.unpack_from("<HHIIBB", table, o)
            if left == 0xFFFF and right == 0xFFFF:  # padding at a sector's end
                continue
            name = table[o + 14:o + 14 + nlen].decode("latin-1")
            if left:
                todo.append(left * 4)
            if right:
                todo.append(right * 4)
            path = (prefix + name).lower()
            if attr & 0x10:
                self._walk(start, length, path + "/", seen)
            else:
                self.entries[path] = (self.base + start * SECTOR, length)


def xbe_title(xbe):
    if xbe[:4] != b"XBEH":
        raise DiscError("default.xbe isn't an Xbox program")
    base, cert = struct.unpack_from("<I", xbe, 0x104)[0], struct.unpack_from("<I", xbe, 0x118)[0]
    o = cert - base
    title_id = struct.unpack_from("<I", xbe, o + 8)[0]
    name = xbe[o + 12:o + 12 + 80].decode("utf-16le", "replace").split("\0")[0]
    return title_id, name


class XboxFolder:
    """Already extracted files, with default.xbe directly inside the folder."""

    def __init__(self, path):
        if not os.path.isfile(os.path.join(path, "default.xbe")):  # the folder that holds it, picked one level up
            subs = [os.path.join(path, s) for s in os.listdir(path)
                    if os.path.isfile(os.path.join(path, s, "default.xbe"))]
            if len(subs) == 1:
                path = subs[0]
        self.path = path
        self.entries = {}
        for d, _, fs in os.walk(path):
            for f in fs:
                full = os.path.join(d, f)
                self.entries[os.path.relpath(full, path).replace(os.sep, "/").lower()] = (full, os.path.getsize(full))
        if "default.xbe" not in self.entries:
            raise DiscError(f"there's no default.xbe directly in {path}")

    def files(self):
        return self.entries

    def read(self, p):
        with open(self.entries[p][0], "rb") as f:
            return f.read()

    def copy(self, p, dest, progress=None):
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        shutil.copyfile(self.entries[p][0], dest)
        if progress:
            progress(self.entries[p][1])

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def open_xbox(path):
    d = XboxFolder(path) if os.path.isdir(path) else XboxImage(path)
    try:
        title_id, name = xbe_title(d.read("default.xbe"))
    except KeyError:
        d.close()
        raise DiscError("there's no default.xbe on that disc")
    if title_id != XBOX_TITLE:
        d.close()
        raise DiscError(f"that's {name or 'another game'} ({title_id:08X}), not {GAME_NAME} for Xbox")
    return d


# ---------------------------------------------------------------- GameCube (GCM / FST)

class BlockFile:
    """A compressed image read as the plain one: blocks unpacked as they're read (only the ones asked for)."""

    def __init__(self, path):
        self.raw = open(path, "rb")
        self.pos = 0
        self.cached = (None, b"")

    def block(self, i):  # the i-th block_size bytes of the plain image
        raise NotImplementedError

    def seek(self, pos):
        self.pos = pos

    def read(self, n):
        out = bytearray()
        while n > 0 and self.pos < self.size:
            i, off = divmod(self.pos, self.block_size)
            if self.cached[0] != i:
                self.cached = (i, self.block(i))
            piece = self.cached[1][off:off + n]
            if not piece:
                break
            out += piece
            self.pos += len(piece)
            n -= len(piece)
        return bytes(out)

    def close(self):
        self.raw.close()


class GczFile(BlockFile):
    """Dolphin's .gcz: zlib-compressed blocks (a block stored as it is has the top bit of its pointer set)."""

    def __init__(self, path):
        super().__init__(path)
        h = self.raw.read(32)
        magic, _, csize, dsize, bsize, nblocks = struct.unpack("<IIQQII", h)
        if magic != 0xB10BC001:
            raise DiscError(f"{os.path.basename(path)} isn't a .gcz image")
        self.size, self.block_size, self.csize = dsize, bsize, csize
        self.ptrs = struct.unpack(f"<{nblocks}Q", self.raw.read(8 * nblocks))
        self.data = 32 + 8 * nblocks + 4 * nblocks

    def block(self, i):
        import zlib
        p = self.ptrs[i] & ~(1 << 63)
        end = (self.ptrs[i + 1] & ~(1 << 63)) if i + 1 < len(self.ptrs) else self.csize
        self.raw.seek(self.data + p)
        b = self.raw.read(end - p)
        if self.ptrs[i] >> 63:
            return b
        try:
            return zlib.decompress(b)
        except zlib.error as e:
            raise DiscError(f"{os.path.basename(self.raw.name)} is damaged (block {i}: {e})")


class CisoFile(BlockFile):
    """.ciso: a map of which blocks are stored, then the stored ones in order (absent ones read as zeros)."""

    def __init__(self, path):
        super().__init__(path)
        h = self.raw.read(0x8000)
        if h[:4] != b"CISO":
            raise DiscError(f"{os.path.basename(path)} isn't a .ciso image")
        self.block_size = struct.unpack_from("<I", h, 4)[0]
        used = h[8:0x8000]
        last = max((i for i, v in enumerate(used) if v), default=-1)
        self.where, n = {}, 0
        for i in range(last + 1):
            if used[i]:
                self.where[i] = n
                n += 1
        self.size = 1459978240 if last < 0 else max(1459978240, (last + 1) * self.block_size)  # a whole disc

    def block(self, i):
        if i not in self.where:
            return bytes(self.block_size)
        self.raw.seek(0x8000 + self.where[i] * self.block_size)
        return self.raw.read(self.block_size)


class GameCubeImage(Image):
    def __init__(self, path, f=None):
        super().__init__(path, f)
        h = self.at(0, 0x440)
        if struct.unpack_from(">I", h, 0x1C)[0] != 0xC2339F3D:
            raise DiscError(f"{os.path.basename(path)} isn't a GameCube disc image")
        self.game_id = h[:6]
        self.name = h[0x20:0x60].split(b"\0")[0].decode("latin-1")
        fst, fst_size = struct.unpack_from(">II", h, 0x424)
        t = self.at(fst, fst_size)
        count = struct.unpack_from(">I", t, 8)[0]
        names = 12 * count

        def name_at(o):
            return t[names + o:t.index(b"\0", names + o)].decode("latin-1")

        # directories end at their "next" index: a stack of (end, prefix)
        stack = [(count, "")]
        for i in range(1, count):
            while i >= stack[-1][0]:
                stack.pop()
            w, a, b = struct.unpack_from(">III", t, 12 * i)
            nm = name_at(w & 0xFFFFFF)
            if w >> 24:
                stack.append((b, stack[-1][1] + nm.lower() + "/"))
            else:
                self.entries[stack[-1][1] + nm.lower()] = (a, b)


class ToolMissing(DiscError):
    """An outside program that a compressed image needs, not found: the Launcher asks where it is."""

    def __init__(self, tool, exe, what, ext):
        super().__init__(f"reading a {ext} image needs {exe}, which {what}. It wasn't found: choose it, or use a "
                         f"plain .iso.")
        self.tool, self.exe = tool, exe


TOOL_PATHS = {}  # tool -> the .exe someone chose (the Launcher fills it from its own file)
TOOLS = {"dolphin": ("DolphinTool.exe", ["DolphinTool", "dolphin-tool"], "*olphin*", "comes with Dolphin"),
         "chdman": ("chdman.exe", ["chdman"], "*ame*", "comes with MAME")}


def find_tool(tool):
    """The tool's program: chosen before, on PATH, or in the folders it's usually unzipped or installed in."""
    import glob
    exe, names, folder, _ = TOOLS[tool]
    if TOOL_PATHS.get(tool) and os.path.isfile(TOOL_PATHS[tool]):
        return TOOL_PATHS[tool]
    for n in names:
        if shutil.which(n):
            return shutil.which(n)
    home = os.path.expanduser("~")
    bases = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    bases += [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")]
    bases += [home] + [os.path.join(home, d) for d in ("Downloads", "Desktop", "Documents", "Games", "Emulators")]
    bases += ["C:\\", "C:\\Games", "C:\\Emulators"]
    for base in [b for b in bases if b and os.path.isdir(b)]:
        for pattern in (os.path.join(base, folder, exe), os.path.join(base, folder, "*", exe)):
            hits = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
            if hits:
                return hits[0]
    return None


def convert(tool, args_for, src):
    """A compressed image converted to a plain one in a temporary folder by an outside tool; (path, folder)."""
    exe, _, _, what = TOOLS[tool]
    found = find_tool(tool)
    if not found:
        raise ToolMissing(tool, exe, what, os.path.splitext(src)[1])
    tool = found
    tmp = tempfile.mkdtemp(prefix="mvp-installer-")
    out = os.path.join(tmp, "disc.iso")
    r = subprocess.run([tool] + args_for(src, out), capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode or not os.path.exists(out):
        shutil.rmtree(tmp, ignore_errors=True)
        raise DiscError(f"{os.path.basename(tool)} couldn't convert {os.path.basename(src)}:\n{(r.stderr or r.stdout)[-600:]}")
    return out, tmp


class Converted:
    """An image read from a converted copy, which goes when it's closed."""

    def __init__(self, image, tmp):
        self.image, self.tmp = image, tmp

    def __getattr__(self, k):
        return getattr(self.image, k)

    def close(self):
        self.image.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def open_gamecube(path):
    ext = os.path.splitext(path)[1].lower()
    tmp = None
    if ext in (".rvz", ".wia"):  # zstd / LZMA groups: Dolphin's own converter
        path, tmp = convert("dolphin", lambda s, o: ["convert", "-i", s, "-o", o, "-f", "iso"], path)
    try:
        d = GameCubeImage(path, GczFile(path) if ext == ".gcz" else CisoFile(path) if ext == ".ciso" else None)
    except Exception:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        raise
    if d.game_id != GC_GAME_ID:
        d.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        raise DiscError(f"that's {d.name or 'another game'} ({d.game_id.decode('latin-1')}), "
                        f"not MVP Baseball 2005 for GameCube ({GC_GAME_ID.decode()})")
    return Converted(d, tmp) if tmp else d


# ---------------------------------------------------------------- PS2 (ISO 9660)

class Iso9660Image(Image):
    def __init__(self, path):
        super().__init__(path)
        pvd = self.at(16 * SECTOR, SECTOR)
        if pvd[1:6] != b"CD001" or pvd[0] != 1:
            raise DiscError(f"{os.path.basename(path)} isn't a PS2 DVD image (no ISO 9660 volume)")
        self._walk(pvd[156:156 + 34], "", set())

    def _walk(self, rec, prefix, seen):
        extent, size = struct.unpack_from("<I", rec, 2)[0], struct.unpack_from("<I", rec, 10)[0]
        if extent in seen:
            return
        seen.add(extent)
        data = self.at(extent * SECTOR, size)
        o = 0
        while o < len(data):
            n = data[o]
            if n == 0:  # rest of this sector unused
                o = (o // SECTOR + 1) * SECTOR
                continue
            r = data[o:o + n]
            o += n
            nlen = r[32]
            raw = r[33:33 + nlen]
            if raw in (b"\0", b"\1"):
                continue
            name = raw.decode("latin-1").split(";")[0].rstrip(".").lower()
            if r[25] & 2:
                self._walk(r, prefix + name + "/", seen)
            else:
                ext, ln = struct.unpack_from("<I", r, 2)[0], struct.unpack_from("<I", r, 10)[0]
                self.entries[prefix + name] = (ext * SECTOR, ln)


def ps2_serial(cnf):
    for line in cnf.decode("latin-1").splitlines():
        if line.replace(" ", "").upper().startswith("BOOT2="):
            return line.split("\\")[-1].split(";")[0].strip().upper()
    return ""


def open_ps2(path):
    tmp = None
    if os.path.splitext(path)[1].lower() == ".chd":
        path, tmp = convert("chdman", lambda s, o: ["extractdvd", "-i", s, "-o", o, "-f"], path)
    try:
        d = Iso9660Image(path)
        serial = ps2_serial(d.read("system.cnf")) if "system.cnf" in d.entries else ""
    except Exception:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        raise
    if serial != PS2_SERIAL:
        d.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        raise DiscError(f"that's {serial or 'not a PS2 game'}, not {GAME_NAME} for PS2 ({PS2_SERIAL})")
    return Converted(d, tmp) if tmp else d


# ---------------------------------------------------------------- what the art needs from each

# MVP 06's PS2 art (tools/ps2_layout/make_ps2_icons06.py): the help icons, the two pitch overlays and the diamonds;
# the layouts come from the Xbox game's own files
PS2_ART_FILES = ["data/frontend/shared.big", "data/frontend/igonly.big", "data/frontend/coopov.big",
                 "data/igshapes/igcrsr.ssh"]


def extract(disc, names, dest, upper=False, progress=None):
    """Only these files from the disc, into dest (keeping their folders); upper-case names as the PS2 disc has them."""
    missing = [n for n in names if n not in disc.files()]
    if missing:
        raise DiscError("the disc is missing " + ", ".join(missing) + ": incomplete or modified image?")
    for n in names:
        disc.copy(n, os.path.join(dest, *(n.upper() if upper else n).split("/")), progress)
