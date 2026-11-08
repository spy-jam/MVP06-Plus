from PIL import Image
import numpy as np
from collections import deque

def glyph_masks(a, rect):
    """colored button glyphs inside rect: name -> (mask bbox, mask array in rect coords)"""
    rx,ry,w,h=rect
    c=np.array(a.crop((rx,ry,rx+w,ry+h))).astype(int)
    r,g,b,al=c[...,0],c[...,1],c[...,2],c[...,3]
    cores={
        'A': (g>120)&(r<90)&(b<90),
        'B': (r>140)&(g<80)&(b<80),
        'X': (b>150)&(r<130)&(g<160)&(b-r>50)&(r>50),
        'Y': (r>170)&(g>130)&(b<80),
        'K': (r<45)&(g<45)&(b<45)&(al>200),
    }
    return c,cores

def components(m):
    h,w=m.shape; seen=np.zeros_like(m,bool); out=[]
    for y in range(h):
        for x in range(w):
            if m[y,x] and not seen[y,x]:
                q=deque([(y,x)]); seen[y,x]=True; pts=[]
                while q:
                    cy,cx=q.popleft(); pts.append((cy,cx))
                    for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
                        ny,nx=cy+dy,cx+dx
                        if 0<=ny<h and 0<=nx<w and m[ny,nx] and not seen[ny,nx]: seen[ny,nx]=True; q.append((ny,nx))
                out.append(pts)
    return out

def inpaint(img, mask):
    """fill mask pixels from their unmasked neighbours, outside in"""
    a=np.array(img).astype(float); m=mask.copy()
    h,w=m.shape
    while m.any():
        newm=m.copy(); filled=0
        for y,x in zip(*np.nonzero(m)):
            acc=np.zeros(4); n=0
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    yy,xx=y+dy,x+dx
                    if 0<=yy<h and 0<=xx<w and not m[yy,xx]: acc+=a[yy,xx]; n+=1
            if n: a[y,x]=acc/n; newm[y,x]=False; filled+=1
        m=newm
        if not filled: break
    return Image.fromarray(a.round().astype('uint8'),'RGBA')

def fit(icon, box_w, box_h):
    bb=icon.getbbox() or (0,0,icon.width,icon.height)
    ic=icon.crop(bb)
    s=min(box_w/ic.width, box_h/ic.height)
    return ic.resize((max(1,round(ic.width*s)),max(1,round(ic.height*s))),Image.LANCZOS)

def replace_disc(atlas, cx, cy, r, icon, size):
    x0,y0=cx-r-2,cy-r-2; w=h=2*r+5
    region=atlas.crop((x0,y0,x0+w,y0+h))
    yy,xx=np.mgrid[0:h,0:w]
    mask=((xx-(cx-x0))**2+(yy-(cy-y0))**2)<=(r+0.8)**2
    region=inpaint(region,mask)
    g=fit(icon,size,size)
    region.alpha_composite(g,(cx-x0-g.width//2, cy-y0-g.height//2))
    atlas.paste(region,(x0,y0))

def replace_box(atlas, x0,y0,x1,y1, icon, pad=0):
    w,h=x1-x0+1,y1-y0+1
    region=atlas.crop((x0-1,y0-1,x1+2,y1+2))
    mask=np.zeros((h+2,w+2),bool); mask[1:-1,1:-1]=True
    region=inpaint(region,mask)
    g=fit(icon,w+pad,h+pad)
    region.alpha_composite(g,((w+2-g.width)//2,(h+2-g.height)//2))
    atlas.paste(region,(x0-1,y0-1))
