import struct
from PIL import Image

def entries(u):
    le = u[:4] in (b'SHPX', b'SHPS')
    E='<' if le else '>'
    n=struct.unpack_from(E+'I',u,8)[0]
    out=[]
    for k in range(n):
        nm=u[16+8*k:20+8*k].decode('latin1'); off=struct.unpack_from(E+'I',u,20+8*k)[0]
        out.append((nm,off))
    return out,E

def blocks(u,off,E):
    """the image header and its attachments: (offset, type, next, header bytes)"""
    res=[]; o=off
    while True:
        t=u[o]; nxt=int.from_bytes(u[o+1:o+4],'little' if E=='<' else 'big')
        res.append((o,t,nxt))
        if nxt==0 or o+nxt>=len(u): break
        o+=nxt
        if len(res)>8: break
    return res

def unswizzle(w,h):
    # Xbox texture swizzle (Morton order, square-ish)
    def part1by1(n):
        n&=0xffff; n=(n|(n<<8))&0x00FF00FF; n=(n|(n<<4))&0x0F0F0F0F; n=(n|(n<<2))&0x33333333; n=(n|(n<<1))&0x55555555; return n
    idx=[0]*(w*h)
    # general Xbox swizzle for non-square: interleave bits up to min dimension
    for y in range(h):
        for x in range(w):
            sx=x; sy=y; off=0; bit=0; mw=w; mh=h; i=0; o=0
            while mw>1 or mh>1:
                if mw>1: o|=(sx&1)<<i; sx>>=1; i+=1; mw>>=1
                if mh>1: o|=(sy&1)<<i; sy>>=1; i+=1; mh>>=1
            idx[y*w+x]=o
    return idx

def decode_xbox(u,off):
    t=u[off]; w,h=struct.unpack_from('<HH',u,off+4)
    data=u[off+16:]
    img=Image.new('RGBA',(w,h))
    px=img.load()
    if t==0x7d:
        idx=unswizzle(w,h)
        for y in range(h):
            for x in range(w):
                i=idx[y*w+x]*4
                b,g,r,a=data[i:i+4]
                px[x,y]=(r,g,b,a)
        return img
    raise ValueError('xbox type %x'%t)

def rgb5a3(v):
    if v&0x8000:
        r=(v>>10)&31; g=(v>>5)&31; b=v&31; return (r*255//31,g*255//31,b*255//31,255)
    a=(v>>12)&7; r=(v>>8)&15; g=(v>>4)&15; b=v&15
    return (r*17,g*17,b*17,a*255//7)

def decode_gc(u,off):
    t=u[off]; w,h=struct.unpack_from('>HH',u,off+4)
    bl=blocks(u,off,'>')
    pal=None
    for o,tt,n in bl[1:]:
        if tt in (0x2a,0x32,0x22,0x24):
            pw=struct.unpack_from('>H',u,o+4)[0]
            raw=u[o+16:o+16+2*pw]
            pal=[rgb5a3(struct.unpack_from('>H',raw,2*i)[0]) for i in range(pw)]
    data=u[off+16:]
    img=Image.new('RGBA',(w,h)); px=img.load()
    if t==0x19:   # C8, 8x4 tiles
        i=0
        for ty in range(0,h,4):
            for tx in range(0,w,8):
                for y in range(4):
                    for x in range(8):
                        c=data[i]; i+=1
                        if tx+x<w and ty+y<h: px[tx+x,ty+y]=pal[c] if pal and c<len(pal) else (c,c,c,255)
        return img
    if t==0x16:   # RGBA8, 4x4 tiles of AR then GB
        i=0
        for ty in range(0,h,4):
            for tx in range(0,w,4):
                ar=data[i:i+32]; gb=data[i+32:i+64]; i+=64
                for k in range(16):
                    x=tx+k%4; y=ty+k//4
                    if x<w and y<h: px[x,y]=(ar[2*k+1],gb[2*k],gb[2*k+1],ar[2*k])
        return img
    raise ValueError('gc type %x'%t)

def encode_xbox_into(u, off, img):
    """write img (same size) into the SHPX image at off, ARGB8888 swizzled"""
    t=u[off]; w,h=struct.unpack_from('<HH',u,off+4)
    assert t==0x7d and img.size==(w,h), (hex(t),img.size,(w,h))
    idx=unswizzle(w,h); px=img.load()
    buf=bytearray(w*h*4)
    for y in range(h):
        for x in range(w):
            r,g,b,a=px[x,y]; i=idx[y*w+x]*4
            buf[i:i+4]=bytes((b,g,r,a))
    return u[:off+16]+bytes(buf)+u[off+16+len(buf):]
