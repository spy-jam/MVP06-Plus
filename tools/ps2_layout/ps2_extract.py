#!/usr/bin/env python3
"""Pull the MVP Baseball PS2 control tables out of the executable: MVP 2005 (SLUS_211.35) or MVP 06 NCAA (SLUS_213.67).

Same pad base class as the Xbox build: N 16-byte entries {short a, b, modeA, modeB, op, pad; float scale} at the pad
object's start. The defaults function writes the shared defaults, then calls vtable slot 39 (the vtable at +0x15EC on
MVP 06, 8-byte gcc entries, so +0x138/+0x13C), which for every PS2 pad class is the PS2 layout: it builds each entry on
the stack and copies it in with ldl/ldr/sdl/sdr.
  MVP 2005: defaults fn_0043CF70, layout fn_00102F70, 0x10B entries
  MVP 06:   defaults fn_00457B38, layout fn_00100AB0, 0x111 entries (three pad vtables, 0089C848/0089C9D8/0089CB68)
This runs both with a tiny MIPS interpreter over llvm-objdump's text and prints the table as JSON.
usage: ps2_extract.py SLUS_xxx.xx out.json
"""
import json, re, struct, subprocess, sys

GAMES = {
    'SLUS_211.35': ({'defaults': 0x43CF70, 'ps2_layout': 0x102F70}, 0x10B),  # MVP Baseball 2005
    'SLUS_213.67': ({'defaults': 0x457B38, 'ps2_layout': 0x100AB0}, 0x111),  # MVP 06 NCAA Baseball
}
FUNCS, N = GAMES['SLUS_211.35']

def load(path):
    e = open(path, 'rb').read()
    phoff, = struct.unpack_from('<I', e, 0x1c); phnum, = struct.unpack_from('<H', e, 0x2c)
    segs = []
    for k in range(phnum):
        _, off, va, _, fsz, msz = struct.unpack_from('<6I', e, phoff + 32 * k)
        segs.append((va, off, fsz))
    return e, segs

def disasm(path, va, maxlen=0x4000):
    out = subprocess.run(['llvm-objdump', '-d', '--triple=mipsel-unknown-unknown', '--mcpu=mips3',
                          '--start-address=0x%x' % va, '--stop-address=0x%x' % (va + maxlen), path],
                         capture_output=True, text=True, check=True).stdout
    ins = []
    for line in out.splitlines():
        m = re.match(r'\s*([0-9a-f]+):\s+(?:[0-9a-f]{2} ){4}\s*(.*)', line)
        if m:
            ins.append((int(m.group(1), 16), re.sub(r'\s*<[^>]*>', '', m.group(2)).strip().replace('\t', ' ')))
            if ins[-1][1].startswith('jr $ra'):
                nxt = True
            elif ins and len(ins) > 1 and ins[-2][1].startswith('jr $ra'):
                break
    return ins

class Mem:
    def __init__(s, e, segs): s.e, s.segs, s.w = e, segs, {}
    def rd(s, a, n):
        v = 0
        for i in reversed(range(n)):
            b = s.w.get(a + i)
            if b is None:
                b = 0
                for va, o, sz in s.segs:
                    if va <= a + i < va + sz: b = s.e[o + a + i - va]; break
            v = (v << 8) | b
        return v
    def wr(s, a, n, v, log=None):
        for i in range(n): s.w[a + i] = (v >> (8 * i)) & 0xff
        if log is not None: log.append((a, n, v))

def reg(x):
    x = x.strip().lstrip('$')
    names = {'zero': 0, 'sp': 29, 'fp': 30, 'ra': 31, 'gp': 28}
    return names.get(x, None) if not x.isdigit() else int(x)

def run(ins, mem, regs, log, warn):
    r = dict(regs); f = {}
    for a, t in ins:
        if not t: continue
        op, _, rest = t.partition(' ')
        args = [x.strip() for x in rest.split(',')] if rest else []
        def R(x): k = reg(x); return 0 if k == 0 else r.get(k, 0)
        def W(x, v):
            k = reg(x)
            if k: r[k] = v & 0xffffffffffffffff
        def EA(x):
            m = re.match(r'(-?(?:0x)?[0-9a-f]+)\((\$\w+)\)', x)
            return (R(m.group(2)) + int(m.group(1), 0)) & 0xffffffff
        if op == 'addiu': W(args[0], (R(args[1]) + int(args[2], 0)) & 0xffffffff)
        elif op == 'lui': W(args[0], (int(args[1], 0) << 16) & 0xffffffff)
        elif op == 'ori': W(args[0], R(args[1]) | int(args[2], 0))
        elif op in ('move', 'addu', 'daddu', 'or'):
            v = R(args[1]) if op == 'move' else (R(args[1]) + R(args[2]) if op != 'or' else R(args[1]) | R(args[2]))
            W(args[0], v & 0xffffffff)
        elif op == 'mtc1': f[args[1]] = R(args[0]) & 0xffffffff
        elif op == 'swc1': mem.wr(EA(args[1]), 4, f.get(args[0], 0), log)
        elif op == 'lwc1': f[args[0]] = mem.rd(EA(args[1]), 4)
        elif op == 'sh': mem.wr(EA(args[1]), 2, R(args[0]) & 0xffff, log)
        elif op == 'sw': mem.wr(EA(args[1]), 4, R(args[0]) & 0xffffffff, log)
        elif op == 'sd': mem.wr(EA(args[1]), 8, R(args[0]), log)
        elif op == 'lw': W(args[0], mem.rd(EA(args[1]), 4))
        elif op == 'lh': W(args[0], struct.unpack('<h', struct.pack('<H', mem.rd(EA(args[1]), 2)))[0] & 0xffffffff)
        elif op == 'ld': W(args[0], mem.rd(EA(args[1]), 8))
        elif op == 'ldr': W(args[0], mem.rd(EA(args[1]), 8))   # paired with ldl: an unaligned 8-byte load at the ldr address
        elif op == 'sdr': mem.wr(EA(args[1]), 8, R(args[0]), log)
        elif op in ('ldl', 'sdl', 'ext'): pass
        elif op in ('jal', 'jalr'): warn.append('%08x call %s' % (a, rest))
        elif op == 'jr': return r
        else: warn.append('%08x UNHANDLED %s' % (a, t))
    return r

def table(log, this):
    ent = {}
    for a, n, v in log:
        for k in range(n):
            o = a + k - this
            if 0 <= o < N * 16:
                ent.setdefault(o // 16, bytearray(b'\xee' * 16))[o % 16] = (v >> (8 * k)) & 0xff
    out = {}
    for i, b in sorted(ent.items()):
        out[i] = {'shorts': list(struct.unpack_from('<6h', b, 0)), 'scale': struct.unpack_from('<f', b, 12)[0], 'raw': b.hex()}
    return out

def main():
    global FUNCS, N
    import os
    name = os.path.basename(sys.argv[1]).upper()
    if name not in GAMES: raise SystemExit('unknown executable %s (one of %s)' % (name, ', '.join(GAMES)))
    FUNCS, N = GAMES[name]
    e, segs = load(sys.argv[1]); mem = Mem(e, segs)
    THIS = 0x01000000; res = {}
    for name, va in FUNCS.items():
        ins = disasm(sys.argv[1], va)
        open(sys.argv[2] + '.%s.s' % name, 'w').write('\n'.join('%08x  %s' % x for x in ins))
        log, warn = [], []
        run(ins, mem, {29: 0x00F00000, 4: THIS}, log, warn)
        res[name] = {'table': table(log, THIS), 'warnings': warn}
    json.dump(res, open(sys.argv[2], 'w'), indent=1)
    for k, v in res.items(): print(k, len(v['table']), 'entries;', v['warnings'])

if __name__ == '__main__': main()
