"""DSH-derived binary chalk extraction. Destructive: not a source of truth.

Adapted from the earlier L07 fast_chalk.py script, preserving the formulae,
board-neighborhood gate, density filter, and isolated-stroke removal.
"""
import numpy as np
import cv2
from PIL import Image

_area = {}
def _mean(a, r):
    h, w = a.shape
    key = (h, w, r)
    den = _area.get(key)
    if den is None:
        den = cv2.boxFilter(np.ones((h,w), np.float32), -1,
            (2*r+1, 2*r+1), normalize=False, borderType=cv2.BORDER_CONSTANT)
        _area[key] = den
    return cv2.boxFilter(a.astype(np.float32), -1, (2*r+1, 2*r+1),
        normalize=False, borderType=cv2.BORDER_CONSTANT) / den

def dsh_chalk_mask(rgb, k=15.0, r_bg=21, r_board=12, thr_board=.40):
    """DSH-style local brightness, board neighborhood and density filter."""
    rgb = rgb.astype(np.float32, copy=False)
    L = .299*rgb[...,0] + .587*rgb[...,1] + .114*rgb[...,2]
    green = (rgb[...,1] > rgb[...,0]+3) & (rgb[...,2] < rgb[...,1]-6)
    near = _mean(green, r_board) > thr_board
    if near.mean() < .10:
        return None
    m = (L - _mean(L, r_bg) > k) & near
    m &= _mean(m, 6) < .5
    n = cv2.filter2D(m.astype(np.uint8), cv2.CV_8U,
        np.ones((3,3), np.uint8), borderType=cv2.BORDER_CONSTANT)
    return m & (n>=2)

def dsh_tile(rgb, k=15.0):
    mask = dsh_chalk_mask(rgb, k=k)
    if mask is None:
        # Source did this for non-board shots. Preserve RGB rather than black.
        return Image.fromarray(rgb, "RGB"), "fallback-rgb"
    return Image.fromarray((mask.astype(np.uint8)*255), "L").convert("1"), "binary"



def encode_dsh(mosaic):
    from io import BytesIO
    out=BytesIO()
    mosaic.save(out,format="PNG",compress_level=6)
    return out.getvalue(),{"gate":"destructive_binary"}
