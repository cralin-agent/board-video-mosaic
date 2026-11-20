"""Color AVIF adaptive codec from L07 board_frame_codec.py.

Decoded SSIM + edge MAE are heuristic quality gates, not math recognition.
"""
from io import BytesIO
import numpy as np
import cv2
from PIL import Image
import pillow_avif  # registers AVIF
from skimage.metrics import structural_similarity

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
