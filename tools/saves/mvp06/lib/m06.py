"""MVP 06 NCAA Baseball dynasty saves: PS2 (Matched.sav inside a .psu) <-> Xbox (data.dat).

Both platforms are little-endian and use the same stream (7 0xBEEFF00D markers, 22 tagged tables). The PS2
stream stores some fields with C struct padding where the Xbox stream writes them packed. Known differences
(from one PS2/Xbox pair of fresh dynasties, see NOTES.md):
  header      u8 + 3 pad (PS2) / u8 (Xbox) before a 32-byte roster-name buffer; then a run of settings ints,
              20 on PS2 and 18 on Xbox (which two are extra is not determined -> kept from the target template)
  conferences 16 records of 0x98 B: PS2 [u8 id][13 B short name][136 B][2 pad]
                                    Xbox [u32 id][12 B short name][136 B]
  two lists   [u8 flag][3 pad on PS2][u32 n][n x u32]
  schedule    one 16 B record: PS2 (a, b, c, d) = Xbox (c, a, b, d); 18 more trailing bytes on PS2 (zero here)
Everything else is copied byte for byte."""
import struct, re

MK = b'\x0d\xf0\xef\xbe'
TAG = b'\x1b\x3c\x8f\xf5'
PS2_PAYLOAD_LEN = 0x176800
XB_PAYLOAD_LEN = 0x212800

# offsets relative to marker 1 (start of section 2)
CONF_REL, CONF_N, CONF_LEN = 0x12d4, 16, 0x98
LIST1_REL = 0x1b1c7
# offset of the reordered record relative to marker 2, and the common prefix of the schedule section
SCHED_REC_REL = 0x195a0


class Unsupported(Exception):
    pass


def markers(d):
    m = [x.start() for x in re.finditer(re.escape(MK), d)]
    if len(m) < 7:
        raise Unsupported('expected 7 section markers, found %d' % len(m))
    return m[:7]


def tags(d):
    return [m.start() for m in re.finditer(re.escape(TAG), d[:0x150000]) if m.start() > 0x2000]


def _fill(start, end):
    return bytes(0x55 if (i & 1) == 0 else 0xAA for i in range(start, end))


# ------------------------------------------------------------------ section 2 pieces
def conf_p2x(r):
    if r[13] != 0:
        raise Unsupported('conference short name longer than the Xbox field')
    return struct.pack('<I', r[0]) + r[1:13] + r[14:0x96]


def conf_x2p(r, tpl):
    idv = struct.unpack_from('<I', r, 0)[0]
    if idv > 0xFF:
        raise Unsupported('conference id does not fit the PS2 field')
    return bytes([idv]) + r[4:16] + b'\0' + r[16:0x98] + tpl[0x96:0x98]


def list_p2x(d, o):
    n = struct.unpack_from('<I', d, o + 4)[0]
    if n > 4096:
        raise Unsupported('list length %d' % n)
    return d[o:o + 1] + d[o + 4:o + 8 + 4 * n], o + 8 + 4 * n


def list_x2p(d, o, pad=b'\0\0\0'):
    n = struct.unpack_from('<I', d, o + 1)[0]
    if n > 4096:
        raise Unsupported('list length %d' % n)
    return d[o:o + 1] + pad + d[o + 1:o + 5 + 4 * n], o + 5 + 4 * n


# ------------------------------------------------------------------ payload conversion
def _finish(body, total):
    end = len(body)
    body += MK + struct.pack('<I', end + 4)
    if len(body) > total:
        raise Unsupported('converted dynasty does not fit the target save (%d bytes over)' % (len(body) - total))
    return bytes(body) + _fill(len(body), total)


def p2x(P, Xt):
    """P: PS2 payload. Xt: Xbox template payload. Returns Xbox payload."""
    mp, mx = markers(P), markers(Xt)
    out = bytearray()
    out += P[0:0xF0]
    out += P[0xF0:0xF1]
    out += P[0xF4:0x114]
    out += Xt[0x111:0x159]                      # settings run kept from the template
    out += P[0x164:mp[1]]                       # name buffer, sliders, marker 0 section
    # section 2
    s = mp[1]
    out += P[s:s + CONF_REL]
    for k in range(CONF_N):
        out += conf_p2x(P[s + CONF_REL + CONF_LEN * k:s + CONF_REL + CONF_LEN * (k + 1)])
    o = s + CONF_REL + CONF_LEN * CONF_N
    out += P[o:s + LIST1_REL]
    l1, o = list_p2x(P, s + LIST1_REL)
    l2, o = list_p2x(P, o)
    out += l1 + l2
    tp = tags(P)
    out += P[o:mp[2]]                           # rest of section 2, all tables
    # schedule section
    s2 = mp[2]
    out += P[s2:s2 + SCHED_REC_REL]
    a, b, c, dd = struct.unpack_from('<4I', P, s2 + SCHED_REC_REL)
    out += struct.pack('<4I', c, a, b, dd)
    xs_len = mx[3] - mx[2]                      # Xbox schedule section is 18 bytes shorter
    tail = P[s2 + SCHED_REC_REL + 16:mp[3]]
    keep = xs_len - SCHED_REC_REL - 16
    if any(tail[keep:]):
        raise Unsupported('schedule section has data where the layouts differ (in-season save?)')
    out += tail[:keep]
    out += P[mp[3]:mp[6]]                       # user section, history
    return _finish(out, XB_PAYLOAD_LEN)


def x2p(X, Pt):
    """X: Xbox payload. Pt: PS2 template payload. Returns PS2 payload."""
    mx, mp = markers(X), markers(Pt)
    out = bytearray()
    out += X[0:0xF0]
    out += X[0xF0:0xF1] + Pt[0xF1:0xF4]
    out += X[0xF1:0x111]
    out += Pt[0x114:0x164]
    out += X[0x159:mx[1]]
    s = mx[1]; st = mp[1]
    out += X[s:s + CONF_REL]
    for k in range(CONF_N):
        out += conf_x2p(X[s + CONF_REL + CONF_LEN * k:s + CONF_REL + CONF_LEN * (k + 1)],
                        Pt[st + CONF_REL + CONF_LEN * k:st + CONF_REL + CONF_LEN * (k + 1)])
    o = s + CONF_REL + CONF_LEN * CONF_N
    out += X[o:s + LIST1_REL]
    l1, o = list_x2p(X, s + LIST1_REL)
    l2, o = list_x2p(X, o)
    out += l1 + l2
    out += X[o:mx[2]]
    s2 = mx[2]
    out += X[s2:s2 + SCHED_REC_REL]
    c, a, b, dd = struct.unpack_from('<4I', X, s2 + SCHED_REC_REL)
    out += struct.pack('<4I', a, b, c, dd)
    ps_len = mp[3] - mp[2]
    tail = X[s2 + SCHED_REC_REL + 16:mx[3]]
    if mx[3] - mx[2] != 104502:
        raise Unsupported('this dynasty has entries in the post-schedule log; the PS2 layout of those entries '
                          'is not known yet (needs a progressed PS2 save to compare)')
    out += tail + bytes(ps_len - SCHED_REC_REL - 16 - len(tail))
    out += X[mx[3]:mx[6]]
    return _finish(out, PS2_PAYLOAD_LEN)
