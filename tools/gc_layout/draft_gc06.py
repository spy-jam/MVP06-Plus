#!/usr/bin/env python3
"""Draft an experimental GameCube action table for MVP 06 NCAA (there was no GameCube release).

usage: draft_gc06.py gc_tables.json(05 GC) xbox_tables.json(05 Xbox) xbox_tables_mvp06.json out_sheet [out_json]

How:
  1. Line up the 05 Xbox table with the 06 Xbox table (difflib over the entries).
  2. Every 06 action that matches a 05 action takes the real 05 GameCube binding (action references remapped
     through the same alignment).
  3. Every new or changed 06 action keeps the 06 Xbox binding: the virtual buttons land on the GameCube's own
     buttons (B jobs on X, Back on Z, ...) exactly as in 05. The few that use a stick click (no GameCube button)
     are decided one by one from the nearest 05 GameCube precedent (DECIDED). All are listed as proposals to test.
     The substitution counts in the sheet show what 05 GameCube did, for reference.
The tables name virtual buttons (v1..v24); each release maps them to its own buttons (see the sheet's header).
"""
import collections, difflib, json, sys

GC_CH = {1: 'D-Right', 2: 'D-Left', 3: 'D-Down', 4: 'D-Up', 5: 'Z', 6: 'A', 7: 'B', 8: 'X', 9: 'Y', 10: 'Start',
         11: 'L', 12: 'R', 13: 'Stick right', 14: 'Stick left', 15: 'Stick up', 16: 'Stick down',
         17: 'C right', 18: 'C left', 19: 'C up', 20: 'C down'}
XB_CH = {1: 'D-Up', 2: 'D-Down', 3: 'D-Left', 4: 'D-Right', 5: 'Start', 6: 'Back', 7: 'LS click', 8: 'RS click',
         9: 'A', 10: 'B', 11: 'X', 12: 'Y', 13: 'Black', 14: 'White', 15: 'LT', 16: 'RT', 17: 'Stick right',
         18: 'Stick left', 19: 'Stick up', 20: 'Stick down', 21: 'RS right', 22: 'RS left', 23: 'RS up', 24: 'RS down'}
MODES = {0: 'press', 1: 'release', 2: 'hold', 3: 'mode3', 4: 'repeat', 5: 'analog'}
OPS = {-1: '', 0: '{a} or {b}', 1: '{a} + {b}', 2: '{a} (without {b})', 3: '{a} minus {b}', 4: 'while {a}: {b}',
       5: 'unless {a}: {b}'}


# New 06 actions that use a stick click (no GameCube button), decided from the nearest 05 GameCube precedent.
# Virtual buttons: 2 Back/Z, 4 B/X, 7 LT/L, 8 RT/R, 11 LS click, 12 RS click (see the sheet's header).
DECIDED = {
    0x018: ((2, -1, 4, -1, -1), 'LS click repeat -> Z repeat: the menus\' L3 (the ballpark editor Hide, drawn as Z). 05 GC, '
                                'without an L3, left it and 0x019 empty'),
    0x019: ((2, -1, 1, -1, -1), 'LS click release -> Z release, as 0x018'),
    0x02F: ((2, -1, 0, -1, -1), 'LS click press -> Z press (05 GC put LS click jobs on Z most often)'),
    0x075: ((2, 4, 2, 0, 1), 'Back without LT -> Z hold + X press, as 05 GC bound the same action (05 0x076)'),
    0x076: ((2, -1, 0, -1, -1), 'LS click press -> Z press, as 05 GC bound its LS click neighbour (05 0x071)'),
    0x074: ((7, 14, 2, 2, 2), 'LT hold without LS click hold -> L hold without D-Down hold. The pitching handler (0x2A01E0) '
                              'checks 0x0AD (hit the batter) each frame and else this (pickoff, state 2); 05 GC dropped the '
                              'exclusion, so with D-Down as a press, L still held turned hit-batter into pickoff a frame later'),
    0x0AD: ((7, 14, 2, 2, 1), 'LT hold + LS click hold (hit the batter) -> L hold + D-Down hold: both held, as the Xbox reads '
                              'it (05 GC had D-Down as a press, which holds for one frame only)'),
    0x0BA: ((2, 3, 2, 2, 1), 'RS click hold (bunt) -> Z hold + A hold, the 05 GameCube bunt (05 0x0B9: Z + A, the Xbox RS/LS click hold)'),
    0x0BF: ((2, 3, 2, 2, 1), 'RS click hold -> Z hold + A hold, as 0x0BA'),
    0x0DA: ((8, -1, 2, -1, -1), 'RT analog -> R hold, as 05 GC made its neighbours 0x0D9/0x0DB'),
}


def load_xb(p):
    x = json.load(open(p))
    t = {int(k): tuple(v[0][:5]) for k, v in x['defaults'].items()}
    for k, v in x['xbox'].items(): t[int(k)] = tuple(v[0][:5])
    return t


def load_gc(p):
    g = json.load(open(p))
    t = {int(k): tuple(v['shorts'][:5]) for k, v in g['defaults']['table'].items()}
    for k, v in g['gc_layout']['table'].items(): t[int(k)] = tuple(v['shorts'][:5])
    return t


def main():
    gc5, xb5, xb6 = load_gc(sys.argv[1]), load_xb(sys.argv[2]), load_xb(sys.argv[3])
    A5, A6 = 0xED, 0xF4                                    # virtual-button alias blocks
    gcn = {v: GC_CH.get(gc5[A5 + v - 1][0], 'nothing') for v in range(1, 25)}
    xbn5 = {v: XB_CH.get(xb5[A5 + v - 1][0], 'nothing') for v in range(1, 25)}
    xbn6 = {v: XB_CH.get(xb6[A6 + v - 1][0], 'nothing') for v in range(1, 25)}
    assert xbn5 == xbn6, 'the virtual buttons moved between 05 and 06'
    n5, n6 = 0x10A, 0x111

    # 1. alignment over the action entries (not the alias block)
    a = [xb5.get(i) for i in range(A5)]
    b = [xb6.get(j) for j in range(A6)]
    m56 = {}
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == 'equal' or (op == 'replace' and i2 - i1 == j2 - j1):
            for k in range(i2 - i1): m56[j1 + k] = (i1 + k, op == 'equal')
    inv = {i: j for j, (i, eq) in m56.items()}

    def remap(e):  # values > 24 are fixed analog-source ids (181, 185, ...): the same in 05 and 06, not renumbered
        return tuple(e)

    # 2. what the 05 GameCube release did to each Xbox virtual button, where it changed the binding
    subst = collections.defaultdict(collections.Counter)
    for i in range(A5):
        x, g = xb5.get(i), gc5.get(i)
        if not x or not g: continue
        for k in (0, 1):
            if 0 < x[k] <= 24: subst[x[k]][g[k]] += 1
    best = {v: c.most_common(1)[0][0] for v, c in subst.items()}

    def one(v, m, names):
        if v == -2: return 'unbound'
        if v == -1: return 'nothing'
        if v > 24: return 'analog source %d' % v
        return '%s [%s]' % (names.get(v, 'nothing'), MODES.get(m, m))

    def desc(e, names):
        a_, b_, ma, mb, op = e
        if a_ == -2: return 'unbound'
        return one(a_, ma, names) if op == -1 else OPS[op].format(a=one(a_, ma, names), b=one(b_, mb, names))

    gc6, src = {}, {}
    for j in range(A6):
        x6 = xb6[j]
        if j in DECIDED:  # (first: a decision also overrides a 05 match that doesn't fit 06)
            gc6[j] = DECIDED[j][0]; src[j] = 'PROPOSED: ' + DECIDED[j][1]
        elif j in m56 and m56[j][1] and m56[j][0] in gc5:
            gc6[j] = remap(gc5[m56[j][0]]); src[j] = '05 GC 0x%03X' % m56[j][0]
        else:
            gc6[j] = x6; src[j] = 'PROPOSED: as Xbox (buttons translate)'
    for j in range(A6, A6 + 24): gc6[j] = ('alias', j - A6 + 1)

    lines = ['MVP 06 NCAA: DRAFT GameCube controls (experimental; there was no GameCube release)',
             'Built from the real MVP 2005 GameCube table: actions that match 05 take its GameCube binding;',
             'actions new or changed in 06 are PROPOSED: kept as the Xbox binds them (each button lands on the GameCube',
             'button for the same virtual button, as in 05), except the few that use a stick click, decided one by one.', '',
             'Buttons (virtual button: Xbox / GameCube, as in 05):']
    for v in range(1, 25): lines.append('  v%-3d %-12s %s' % (v, xbn6[v], gcn[v]))
    lines += ['', 'Substitutions 05 GameCube made (Xbox button -> GameCube button, count):']
    for v in sorted(subst):
        c = subst[v]; tot = sum(c.values()); top = c.most_common(3)
        lines.append('  %-10s -> %s' % (xbn5[v], ', '.join('%s %d/%d' % ((gcn[g] if 0 < g <= 24 else {-1: 'nothing', -2: 'unbound'}.get(g, 'act 0x%X' % g)), k, tot) for g, k in top)))
    lines += ['', 'Every 06 action whose GameCube binding differs from the Xbox, and every new 06 action:', '',
              '%-6s %-44s %-44s %s' % ('Action', 'Xbox', 'GameCube (draft)', 'source')]
    nprop = 0
    for j in range(A6):
        dx, dg = desc(xb6[j], xbn6), desc(gc6[j], gcn)
        if dx != dg or src[j].startswith('PROPOSED'):
            lines.append('0x%03X  %-44s %-44s %s' % (j, dx, dg, src[j]))
            nprop += src[j].startswith('PROPOSED')
    lines += ['', '%d actions from 05 GameCube, %d proposed (%d of them judgment calls, marked with a reason).' % (
        sum(1 for j in range(A6) if not src[j].startswith('PROPOSED')), nprop, len(DECIDED))]
    open(sys.argv[4], 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    if len(sys.argv) > 5:
        json.dump({'gc06': {str(k): v for k, v in gc6.items()}, 'source': {str(k): v for k, v in src.items()}},
                  open(sys.argv[5], 'w'), indent=1)


main()
