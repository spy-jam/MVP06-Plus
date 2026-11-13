"""PS2 memory card images (PCSX2's .ps2, or a card dumped from a console): the saves on them read out, nothing written.

The card is 512-byte pages, each followed by 16 bytes of error-correcting code in a full image (8 MB cards:
8,650,752 bytes), in clusters of two pages. A superblock at the start gives the allocation start, the root
directory's cluster and the clusters holding the FAT (by an indirect list); a file's clusters are chained through
the FAT. Directory entries are 512 bytes: mode, length, first cluster, name.
"""
import struct

MAGIC = b"Sony PS2 Memory Card Format "
DF_EXISTS, DF_DIR, DF_FILE = 0x8000, 0x0020, 0x0010


class CardError(Exception):
    pass


class Card:
    def __init__(self, data):
        if data[:28] != MAGIC:
            raise CardError("not a PS2 memory card image")
        (self.page_len, self.ppc, _, _, self.clusters, self.alloc_off, self.alloc_end,
         self.rootdir) = struct.unpack_from("<HHHHIIII", data, 40)
        if self.page_len != 512 or self.ppc != 2:
            raise CardError("a PS2 memory card this doesn't read (page or cluster size)")
        self.ifc = [c for c in struct.unpack_from("<32I", data, 0x50) if c]
        self.data = data
        pages = self.clusters * self.ppc
        if len(data) == pages * 528:
            self.stride = 528  # with the error-correcting bytes
        elif len(data) == pages * 512:
            self.stride = 512
        else:
            raise CardError("the card image isn't a whole card")
        self.cluster_len = self.page_len * self.ppc
        self._fat = None

    def page(self, n):
        o = n * self.stride
        return self.data[o:o + self.page_len]

    def cluster(self, c):
        return b"".join(self.page(c * self.ppc + i) for i in range(self.ppc))

    def fat(self):
        """The FAT as one list of entries (cluster numbers relative to the allocation start)."""
        if self._fat is None:
            per = self.cluster_len // 4
            out = []
            for ic in self.ifc:
                for fc in struct.unpack(f"<{per}I", self.cluster(ic)):
                    if fc == 0xFFFFFFFF:
                        break
                    out.extend(struct.unpack(f"<{per}I", self.cluster(fc)))
            self._fat = out
        return self._fat

    def chain(self, first):
        fat, out, c = self.fat(), [], first
        while len(out) <= self.clusters:
            out.append(c)
            if c >= len(fat):
                raise CardError("the card's file table is damaged")
            nxt = fat[c]
            if not nxt & 0x80000000:
                raise CardError("the card's file table is damaged")
            nxt &= 0x7FFFFFFF
            if nxt == 0x7FFFFFFF:
                return out
            c = nxt
        raise CardError("the card's file table loops")

    def read(self, first, length):
        out = b"".join(self.cluster(self.alloc_off + c) for c in self.chain(first))
        if len(out) < length:
            raise CardError("a file on the card is cut short")
        return out[:length]

    def entries(self, first, count):
        """[{name, mode, length, cluster}] of a directory (its . and .. left out)."""
        raw = self.read(first, count * 512)
        out = []
        for i in range(count):
            e = raw[i * 512:(i + 1) * 512]
            mode, length = struct.unpack_from("<HxxI", e, 0)
            cluster = struct.unpack_from("<I", e, 0x10)[0]
            name = e[0x40:0x60].split(b"\0")[0].decode("latin-1")
            if mode & DF_EXISTS and name not in (".", ".."):
                out.append({"name": name, "mode": mode, "length": length, "cluster": cluster})
        return out

    def root(self):
        first = self.page(self.alloc_off * self.ppc + self.rootdir * self.ppc)
        count = struct.unpack_from("<I", first, 4)[0]  # the root's "." entry holds the directory's length
        return self.entries(self.rootdir, count)

    def saves(self):
        """{save folder name: {file name: bytes}} for every save on the card."""
        out = {}
        for d in self.root():
            if not d["mode"] & DF_DIR:
                continue
            files = {}
            for f in self.entries(d["cluster"], d["length"]):
                if f["mode"] & DF_FILE:
                    files[f["name"]] = self.read(f["cluster"], f["length"]) if f["length"] else b""
            out[d["name"]] = files
        return out


def to_psu(folder, files):
    """A save as a .psu (EMS/uLaunchELF's format): a header for the folder, its . and .., then each file."""
    def entry(mode, length, name):
        e = bytearray(512)
        struct.pack_into("<HxxI", e, 0, mode, length)
        e[0x40:0x40 + len(name)] = name.encode("latin-1")[:32]
        return bytes(e)
    out = bytearray(entry(0x8427, len(files) + 2, folder) + entry(0x8427, 0, ".") + entry(0x8427, 0, ".."))
    for name, data in files.items():
        out += entry(0x8497, len(data), name) + data + b"\0" * ((-len(data)) % 1024)
    return bytes(out)
