# tiny straight-line x86 emulator for objdump intel text (mov/lea/movss/xor/or/add/sub/push/pop)
import re,sys,struct
R32=['eax','ecx','edx','ebx','esp','ebp','esi','edi']
R16={'ax':'eax','cx':'ecx','dx':'edx','bx':'ebx','si':'esi','di':'edi','bp':'ebp','sp':'esp'}
R8={'al':('eax',0),'cl':('ecx',0),'dl':('edx',0),'bl':('ebx',0),'ah':('eax',8),'ch':('ecx',8),'dh':('edx',8),'bh':('ebx',8)}
XBE=open('default.xbe','rb').read()
SECS=[(0x58db20,0x57f000,0x9dcc8),(0x62b800,0x61d000,0x24158),(0x11000,0x1000,0x4326a8)]
def rdmem(va,n):
    for v,r,s in SECS:
        if v<=va<v+s: return int.from_bytes(XBE[va-v+r:va-v+r+n],'little')
    raise Exception('rd %x'%va)
class Emu:
    def __init__(s,this=0x10000000):
        s.r={k:0 for k in R32}; s.r['ecx']=this; s.r['esp']=0x7f000000; s.r['ebp']=0x7f000000
        s.x={}; s.mem={}; s.writes=[]
    def ea(s,t):
        m=re.match(r'(?:(\w+) PTR )?(?:ds:)?\[?([^\]]*)\]?',t)
        e=t[t.index('[')+1:t.index(']')] if '[' in t else t.split('ds:')[1]
        v=0
        for term in re.findall(r'[+-]?[^+-]+',e):
            sg=-1 if term.startswith('-') else 1; term=term.lstrip('+-')
            if '*' in term: a,b=term.split('*'); v+=sg*s.get(a)*int(b,0)
            elif term in s.r: v+=sg*s.r[term]
            else: v+=sg*int(term,0)
        return v&0xffffffff
    def size(s,t):
        if t.startswith('BYTE'): return 1
        if t.startswith('WORD'): return 2
        if t.startswith('DWORD'): return 4
        return None
    def rd(s,a,n):
        v=0
        for i in range(n):
            b=s.mem.get(a+i)
            if b is None: b=(rdmem(a,n)>>(8*i))&0xff if a<0x7000000 else 0
            v|=b<<(8*i)
        return v
    def wr(s,a,n,v):
        for i in range(n): s.mem[a+i]=(v>>(8*i))&0xff
        s.writes.append((a,n,v))
    def get(s,o,n=4):
        if o in s.r: return s.r[o]
        if o in R16: return s.r[R16[o]]&0xffff
        if o in R8: r,sh=R8[o]; return (s.r[r]>>sh)&0xff
        if o in s.x or o.startswith('xmm'): return s.x.get(o,0)
        if 'PTR' in o or o.startswith('ds:'): return s.rd(s.ea(o),s.size(o) or n)
        return int(o,0)&0xffffffff
    def put(s,o,v,n=4):
        if o in s.r: s.r[o]=v&0xffffffff
        elif o in R16: s.r[R16[o]]=(s.r[R16[o]]&0xffff0000)|(v&0xffff)
        elif o in R8: r,sh=R8[o]; s.r[r]=(s.r[r]&~(0xff<<sh))|((v&0xff)<<sh)
        elif o.startswith('xmm'): s.x[o]=v
        else: s.wr(s.ea(o),s.size(o) or n,v)
    def step(s,ins):
        m=re.match(r'(\w+)\s*(.*)',ins); op,args=m.group(1),m.group(2)
        a=[x.strip() for x in re.split(r',(?![^\[]*\])',args)] if args else []
        if op in('mov','movss','movd','movzx','movsx'):
            n=s.size(a[0]) or (2 if a[0] in R16 else 1 if a[0] in R8 else 4)
            if op=='movss' and 'PTR' in a[1]: v=s.rd(s.ea(a[1]),4)
            else: v=s.get(a[1],n)
            if op=='movsx':
                sz=s.size(a[1]) or 2
                if v>>(8*sz-1): v|=~((1<<(8*sz))-1)
            s.put(a[0],v,n)
        elif op=='lea': s.put(a[0],s.ea(a[1]))
        elif op=='xor': s.put(a[0],s.get(a[0])^s.get(a[1]))
        elif op=='or': s.put(a[0],s.get(a[0])|s.get(a[1]))
        elif op=='and': s.put(a[0],s.get(a[0])&s.get(a[1]))
        elif op=='add': s.put(a[0],s.get(a[0])+s.get(a[1]))
        elif op=='sub': s.put(a[0],s.get(a[0])-s.get(a[1]))
        elif op=='inc': s.put(a[0],s.get(a[0])+1)
        elif op=='dec': s.put(a[0],s.get(a[0])-1)
        elif op=='push': s.r['esp']-=4; s.wr(s.r['esp'],4,s.get(a[0]))
        elif op=='pop': s.put(a[0],s.rd(s.r['esp'],4)); s.r['esp']+=4
        elif op=='xorps': s.x[a[0]]=0
        elif op in('ret','int3','nop'): return False
        else: raise Exception('unhandled '+ins)
        return True
def run_lines(lines,this=0x10000000):
    e=Emu(this)
    for l in lines:
        ins=l.split(None,1)[1]
        if not e.step(ins): break
    return e
def entries(e,this=0x10000000):
    out={}
    for a,n,v in e.writes:
        o=a-this
        if 4<=o<4+0x10b*16:
            out.setdefault((o-4)//16,bytearray(b'\xee'*16))
            idx=(o-4)//16; off=(o-4)%16
            for i in range(n): out[idx][off+i]=(v>>(8*i))&0xff
    res={}
    for i,b in out.items():
        sh=struct.unpack_from('<5h',b,0); f=struct.unpack_from('<f',b,12)[0]
        res[i]=(sh,f)
    return res
if __name__=='__main__':
    lines=open(sys.argv[1]).read().splitlines()
    e=run_lines(lines)
    for i,(sh,f) in sorted(entries(e).items()):
        print('%3d 0x%03x  chA=%3d chB=%3d modA=%3d modB=%3d op=%3d  scale=%g'%(i,i,*sh,f))
