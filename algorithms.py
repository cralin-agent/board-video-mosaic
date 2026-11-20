"""Two image codecs: faithful AVIF and DSH-derived chalk extraction.
DSH mask is adapted from L07_compact_1fps/fast_chalk.py (2026-11-20
source session). The 1-bit image is intentionally destructive.
"""
from io import BytesIO
import numpy as np
import cv2
from PIL import Image
import pillow_avif  # noqa: F401 -- register AVIF with Pillow
from skimage.metrics import structural_similarity

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

def _gray(image):
    return cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)

def fidelity(reference, candidate):
    a, b = _gray(reference), _gray(candidate)
    ssim = float(structural_similarity(a, b, data_range=255))
    e = cv2.dilate(cv2.Canny(a,50,140), np.ones((3,3),np.uint8)) > 0
    delta = np.abs(a.astype(np.float32)-b.astype(np.float32))
    return ssim, float(delta[e].mean() if np.any(e) else delta.mean())

def encode_avif(image, adaptive=True, q=55, ssim_min=.980, edge_mae_max=5.0):
    """Decode and check actual AVIF. Conservative fallback never claims PASS."""
    image=image.convert("RGB")
    quals = [q] if not adaptive else list(range(40, 86, 5))
    trials=[]
    last=None
    for quality in quals:
        out=BytesIO()
        image.save(out, format="AVIF", quality=quality, speed=7)
        payload=out.getvalue()
        last=(payload,quality)
        if not adaptive:
            return payload,{"quality":quality,"gate":"not_checked"}
        with Image.open(BytesIO(payload)) as decoded:
            ssim,mae=fidelity(image,decoded)
        passed=ssim>=ssim_min and mae<=edge_mae_max
        trials.append({"quality":quality,"ssim":round(ssim,5),
                       "edge_mae":round(mae,3),"pass":passed})
        if passed:
            return payload,{"quality":quality,"gate":"pass","trials":trials}
    payload,quality=last
    return payload,{"quality":quality,"gate":"fail","trials":trials}

def encode_dsh(mosaic):
    out=BytesIO()
    mosaic.save(out,format="PNG",compress_level=6)
    return out.getvalue(),{"gate":"destructive_binary"}
