#!/usr/bin/env python3
"""Verify / recompute the checksums in an MVP Baseball 2005 (GameCube, GV4E69) dynasty .gci

Recovered from the decomp (fn_8017037C / fn_80170420 -> fn_80400560) and checked against a real save.

GC file layout (offsets in the .gci file, header = 0x40 bytes of GCI directory entry):
  0x2088  4 x u32 BE checksums:  [0] header body  [1] payload  [2] icon block  [3] banner block
  0x2098  4 x u32 BE sizes:      0xB0, payload size, 0x840, 0x1840
  0x20A8  blocks, 0x20AC flags (0x01101311 = franchise/dynasty), names ...
  0x2138  payload (size from header, 0x186C00 for a dynasty save)

Checksum function fn_80400560 (EA): read first 4 bytes big-endian, invert, then for each remaining byte
  crc = ((crc << 8) | byte) ^ T[crc >> 24];  result = ~crc     (T = standard MSB-first CRC32 table, poly 0x04C11DB7)

Checksums [2] and [3] could NOT be reproduced from file bytes. They are left untouched (assumed constant per
game build); verify this with a second save that has a different dynasty name.

usage: gc_checksums.py FILE.gci            # verify
       gc_checksums.py FILE.gci --fix      # rewrite checksums [0] and [1]
"""
import struct, sys

def make_table():
    t = []
    for i in range(256):
        c = i << 24
        for _ in range(8):
            c = ((c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if c & 0x80000000 else (c << 1) & 0xFFFFFFFF
        t.append(c)
    return t
T = make_table()

def ea_crc(p: bytes) -> int:
    if len(p) <= 3:
        return 0
    crc = (~struct.unpack('>I', p[:4])[0]) & 0xFFFFFFFF
    for b in p[4:]:
        crc = (((crc << 8) & 0xFFFFFFFF) | b) ^ T[crc >> 24]
    return (~crc) & 0xFFFFFFFF

H = 0x2088
def check(buf: bytearray, fix=False):
    cs = list(struct.unpack('>4I', buf[H:H+16]))
    sizes = struct.unpack('>4I', buf[H+0x10:H+0x20])
    hsize, psize = sizes[0], sizes[1]
    assert hsize == 0xB0, 'unexpected header size'
    P = H + hsize
    want0 = ea_crc(bytes(buf[H+0x10:H+hsize]))
    want1 = ea_crc(bytes(buf[P:P+psize]))
    print('header  stored %08x  computed %08x  %s' % (cs[0], want0, 'OK' if cs[0] == want0 else 'MISMATCH'))
    print('payload stored %08x  computed %08x  %s' % (cs[1], want1, 'OK' if cs[1] == want1 else 'MISMATCH'))
    print('icon    stored %08x  (not verifiable, left as is)' % cs[2])
    print('banner  stored %08x  (not verifiable, left as is)' % cs[3])
    if fix:
        # header checksum covers bytes +0x10.. so it does not depend on the checksum words themselves
        struct.pack_into('>II', buf, H, want0, want1)
    return cs[0] == want0 and cs[1] == want1

if __name__ == '__main__':
    path = sys.argv[1]
    buf = bytearray(open(path, 'rb').read())
    ok = check(buf, '--fix' in sys.argv)
    if '--fix' in sys.argv:
        open(path, 'wb').write(buf); print('rewritten')
    sys.exit(0 if ok else 1)
