"""JPEG snapshots for the page. The PNG on disk is the record; these are for looking."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image


def to_jpeg(pixels: np.ndarray, max_width: int = 640, quality: int = 80) -> bytes:
    im = Image.fromarray(pixels)
    if im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)), Image.BILINEAR)
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=quality)
    return out.getvalue()
