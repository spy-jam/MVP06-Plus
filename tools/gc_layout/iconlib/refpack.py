def unrefpack(src):
    i=0
    flags=(src[0]<<8)|src[1]; i=2
    if flags & 0x8000:   # 4-byte sizes
        if flags & 0x0100: i+=4
        size=int.from_bytes(src[i:i+4],'big'); i+=4
    else:
        if flags & 0x0100: i+=3
        size=int.from_bytes(src[i:i+3],'big'); i+=3
    out=bytearray()
    while i<len(src):
        b0=src[i]
        if b0<0x80:
            b1=src[i+1]; i+=2
            n=b0&3; out+=src[i:i+n]; i+=n
            ln=((b0&0x1c)>>2)+3; off=((b0&0x60)<<3)+b1+1
        elif b0<0xC0:
            b1,b2=src[i+1],src[i+2]; i+=3
            n=(b1>>6)&3; out+=src[i:i+n]; i+=n
            ln=(b0&0x3f)+4; off=((b1&0x3f)<<8)+b2+1
        elif b0<0xE0:
            b1,b2,b3=src[i+1],src[i+2],src[i+3]; i+=4
            n=b0&3; out+=src[i:i+n]; i+=n
            ln=((b0&0x0c)<<6)+b3+5; off=((b0&0x10)<<12)+(b1<<8)+b2+1
        elif b0<0xFC:
            i+=1; n=((b0&0x1f)<<2)+4; out+=src[i:i+n]; i+=n; continue
        else:
            i+=1; n=b0&3; out+=src[i:i+n]; i+=n; break
        s=len(out)-off
        for k in range(ln): out.append(out[s+k])
    return bytes(out)
