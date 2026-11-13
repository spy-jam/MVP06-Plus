"""Save file wrappers for MVP 06 NCAA Baseball.

PS2: a .psu (uLaunchELF/PCSX2 export) holding a folder with icon.sys, title.ico, a small marker file and
     <name>.sav. <name>.sav = 0xC8-byte header + 0x176800-byte payload. Header: 4 x u32 LE EA-CRC checksums
     [header 0x10..0xC8, payload, title.ico, icon.sys], 4 x u32 sizes, then names.
Xbox: data.dat = 2 x HMAC-SHA1 (key = 16 zero bytes in the recomp) + 0xB8-byte header + 0x212800-byte payload."""
import struct, hmac, hashlib
from gc_checksums import ea_crc

# ----------------------------------------------------------------------------- PS2 .psu
def psu_parse(buf):
    """-> list of entries: dict(off, mode, size, name, data_off)."""
    out = []; o = 0
    while o + 512 <= len(buf):
        mode, attr, size = struct.unpack_from('<HHI', buf, o)
        name = buf[o + 0x40:o + 0x60].split(b'\0')[0].decode('latin1')
        e = dict(off=o, mode=mode, size=size, name=name, data_off=None)
        o += 512
        if mode & 0x0010:
            e['data_off'] = o
            o += (size + 1023) // 1024 * 1024
        out.append(e)
        if mode == 0 and size == 0 and not name:
            break
    return out


def psu_sav(buf):
    for e in psu_parse(buf):
        if e['data_off'] is not None and e['name'].lower().endswith('.sav'):
            return e
    raise ValueError('no .sav file found in the .psu')


def psu_file(buf, name):
    for e in psu_parse(buf):
        if e['data_off'] is not None and e['name'] == name:
            return buf[e['data_off']:e['data_off'] + e['size']]
    return None


def ps2_payload(psu):
    e = psu_sav(psu); sav = psu[e['data_off']:e['data_off'] + e['size']]
    hl, pl = struct.unpack_from('<II', sav, 0x10)
    return sav[hl:hl + pl]


def ps2_check(psu):
    e = psu_sav(psu); sav = psu[e['data_off']:e['data_off'] + e['size']]
    cs = struct.unpack_from('<4I', sav, 0); hl, pl = struct.unpack_from('<II', sav, 0x10)
    want = (ea_crc(sav[0x10:hl]), ea_crc(sav[hl:hl + pl]), ea_crc(psu_file(psu, 'title.ico') or b''),
            ea_crc(psu_file(psu, 'icon.sys') or b''))
    return tuple(cs) == want


def ps2_build(template_psu, payload):
    """Template .psu with its .sav payload replaced; checksums recomputed."""
    out = bytearray(template_psu)
    e = psu_sav(template_psu); so = e['data_off']
    sav = bytearray(out[so:so + e['size']])
    hl, pl = struct.unpack_from('<II', sav, 0x10)
    assert len(payload) == pl, 'PS2 payload must be 0x%X bytes' % pl
    sav[hl:hl + pl] = payload
    c0 = ea_crc(bytes(sav[0x10:hl])); c1 = ea_crc(bytes(payload))
    c2 = ea_crc(psu_file(template_psu, 'title.ico') or b''); c3 = ea_crc(psu_file(template_psu, 'icon.sys') or b'')
    struct.pack_into('<4I', sav, 0, c0, c1, c2, c3)
    out[so:so + e['size']] = sav
    return bytes(out)

# ----------------------------------------------------------------------------- Xbox data.dat
XB_KEY = b'\0' * 16
XB_HDR, XB_HDR_LEN = 0x50, 0xB8


def xb_payload(buf):
    hdr_end, psz = struct.unpack_from('<II', buf, XB_HDR)
    return buf[hdr_end:hdr_end + psz]


def xb_check(buf):
    hdr_end, psz = struct.unpack_from('<II', buf, XB_HDR)
    s0 = hmac.new(XB_KEY, buf[XB_HDR:hdr_end], hashlib.sha1).digest()
    s1 = hmac.new(XB_KEY, buf[hdr_end:hdr_end + psz], hashlib.sha1).digest()
    return s0 == buf[:0x14] and s1 == buf[0x14:0x28]


def xb_build(template, payload):
    out = bytearray(template)
    hdr_end, psz = struct.unpack_from('<II', out, XB_HDR)
    assert len(payload) == psz, 'Xbox payload must be 0x%X bytes' % psz
    out[hdr_end:hdr_end + psz] = payload
    out[0:0x14] = hmac.new(XB_KEY, bytes(out[XB_HDR:hdr_end]), hashlib.sha1).digest()
    out[0x14:0x28] = hmac.new(XB_KEY, bytes(payload), hashlib.sha1).digest()
    return bytes(out)
