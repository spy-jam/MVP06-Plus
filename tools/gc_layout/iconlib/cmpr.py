import numpy as np

def gc_cmpr_to_dxt1(u, off, w, h):
    """GameCube CMPR texture data (8x8 tiles of 2x2 blocks; big-endian colours, first pixel in the high bits) as
    the Xbox's linear DXT1 blocks: the same compressed blocks, so nothing is lost"""
    n = (w // 4) * (h // 4)
    raw = np.frombuffer(u, np.uint8, n * 8, off + 16).reshape(h // 8, w // 8, 2, 2, 8)
    raw = raw.transpose(0, 2, 1, 3, 4).reshape(h // 4, w // 4, 8)
    out = raw.copy()
    out[..., 0], out[..., 1], out[..., 2], out[..., 3] = raw[..., 1], raw[..., 0], raw[..., 3], raw[..., 2]
    ib = raw[..., 4:8]
    out[..., 4:8] = ((ib & 0x03) << 6) | ((ib & 0x0c) << 2) | ((ib & 0x30) >> 2) | ((ib & 0xc0) >> 6)
    return out.tobytes()
