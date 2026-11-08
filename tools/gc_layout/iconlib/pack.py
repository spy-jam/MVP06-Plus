import struct
def refpack_store(data):
    """a valid RefPack stream with literal blocks only (no matches): larger, but every EA reader accepts it"""
    out=bytearray(b'\x10\xfb')+len(data).to_bytes(3,'big')
    i=0; n=len(data)
    while n-i>=4:
        k=min(112,(n-i)//4*4)
        out.append(0xE0+((k-4)>>2)); out+=data[i:i+k]; i+=k
    r=n-i; out.append(0xFC+r); out+=data[i:i+r]
    return bytes(out)

def write_big(path, files, trailer=b'L234\x00\x00\x00\x01'):
    dir_len=16+sum(8+len(n)+1 for n,_ in files)
    hdr=dir_len+len(trailer)
    offs=[]; pos=(hdr+3)&~3  # every file starts on 4 bytes, the first one too, as on the discs
    for n,b in files:
        offs.append(pos); pos+=len(b); pos=(pos+3)&~3
    total=offs[-1]+len(files[-1][1])
    out=bytearray(b'BIGF')+struct.pack('<I',total)+struct.pack('>II',len(files),hdr)
    for (n,b),o in zip(files,offs): out+=struct.pack('>II',o,len(b))+n.encode('latin1')+b'\0'
    out+=trailer
    for (n,b),o in zip(files,offs):
        out+=b'\0'*(o-len(out)); out+=b
    open(path,'wb').write(out)

MAXTRIES=48
def refpack(data):
    """EA RefPack (0x10FB) with matches: greedy LZ over hash chains"""
    n=len(data); out=bytearray(b'\x10\xfb')+n.to_bytes(3,'big')
    head={}; prev=[-1]*n
    lit_start=0; i=0
    def emit_literals(upto, keep):
        nonlocal lit_start
        # literal blocks of 4..112 until fewer than 4 (or keep<=3) remain
        while upto-lit_start>=4 and upto-lit_start>keep:
            k=min(112,(upto-lit_start)//4*4)
            out.append(0xE0+((k-4)>>2)); out.extend(data[lit_start:lit_start+k]); lit_start+=k
    def insert(p):
        if p+3<=n:
            h=data[p:p+3]; prev[p]=head.get(h,-1); head[h]=p
    while i<n:
        best_len=0; best_off=0
        if i+3<=n:
            c=head.get(data[i:i+3],-1); tries=0
            while c>=0 and i-c<=131072 and tries<MAXTRIES:
                l=3; mx=min(1028,n-i)
                while l<mx and data[c+l]==data[i+l]: l+=1
                if l>best_len or (l==best_len and i-c<best_off):
                    best_len=l; best_off=i-c
                    if l==mx: break
                c=prev[c]; tries+=1
        o=best_off
        ok = best_len>=3 and (o<=1024 and best_len<=10 or best_len>=4 and o<=16384 or best_len>=5)
        if not ok:
            insert(i); i+=1; continue
        # literals before the match: blocks of 4, then 0..3 carried in the match
        emit_literals(i, 3)
        lit=i-lit_start; L=best_len
        if o<=1024 and L<=10:
            out.append((((o-1)>>3)&0x60)|((L-3)<<2)|lit); out.append((o-1)&0xff)
        elif o<=16384 and L<=67:
            if L<4: L=4
            out.append(0x80|(L-4)); out.append((lit<<6)|((o-1)>>8)); out.append((o-1)&0xff)
        else:
            L=max(5,min(L,1028))
            out.append(0xC0|(((o-1)>>12)&0x10)|(((L-5)>>6)&0x0c)|lit); out.append(((o-1)>>8)&0xff); out.append((o-1)&0xff); out.append((L-5)&0xff)
        out.extend(data[lit_start:i]); 
        for p in range(i,i+L): insert(p)
        i+=L; lit_start=i
    emit_literals(n,3)
    r=n-lit_start; out.append(0xFC+r); out.extend(data[lit_start:n])
    return bytes(out)
