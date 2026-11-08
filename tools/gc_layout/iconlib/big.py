import struct,sys,os
def read_big(p):
    d=open(p,'rb').read()
    n,hs=struct.unpack_from('>II',d,8); o=16; out=[]
    for i in range(n):
        off,sz=struct.unpack_from('>II',d,o); o+=8
        e=d.index(b'\0',o); name=d[o:e].decode('latin1'); o=e+1
        out.append((name,d[off:off+sz]))
    return out
if __name__=='__main__':
    for p in sys.argv[1:]:
        print('==',p)
        for n,b in read_big(p): print('  %-40s %8d %r'%(n,len(b),b[:4]))
