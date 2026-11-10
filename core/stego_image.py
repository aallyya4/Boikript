"""Steganografi gambar: LSB pada kanal RGB PNG."""
import io

import numpy as np
from PIL import Image

from .stego_common import capacity, embed_bits, extract_bits


def to_png(data: bytes) -> bytes:
    out = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGB").save(out, format="PNG")
    return out.getvalue()


def image_capacity(data: bytes) -> int:
    im = Image.open(io.BytesIO(data))
    return capacity(im.width * im.height * 3)


def _png(arr: np.ndarray) -> bytes:
    out = io.BytesIO()
    Image.fromarray(arr).save(out, format="PNG")
    return out.getvalue()


def _thumb(arr: np.ndarray, size: int = 320) -> bytes:
    im = Image.fromarray(arr)
    im.thumbnail((size, size))
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def _diff_img(changed: np.ndarray, size: int = 320) -> bytes:
    """Peta lokasi piksel yang berubah (titik hijau). Piksel digabung per blok agar titik tetap terlihat."""
    h, w = changed.shape
    f = max(1, -(-max(h, w) // size))
    hh, ww = -(-h // f) * f, -(-w // f) * f
    pad = np.zeros((hh, ww), bool)
    pad[:h, :w] = changed
    small = pad.reshape(hh // f, f, ww // f, f).any(axis=(1, 3))
    dil = small.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            dil |= np.roll(np.roll(small, dy, 0), dx, 1)
    img = np.full((*dil.shape, 3), 18, np.uint8)
    img[dil] = (29, 185, 84)
    scale = max(1, size // max(dil.shape))
    if scale > 1:
        img = np.kron(img, np.ones((scale, scale, 1), np.uint8))
    return _png(img)


def embed_image(png: bytes, payload: bytes, seed: bytes, probe=None) -> bytes:
    arr = np.array(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.uint8)
    p = {} if probe is not None else None
    flat = embed_bits(arr.reshape(-1).copy(), payload, seed, p)
    new = flat.reshape(arr.shape)
    if probe is not None:
        probe.update(p)
        probe.update(width=int(arr.shape[1]), values_changed=int((arr != new).sum()),
                     before_img=_thumb(arr), after_img=_thumb(new), diff_img=_diff_img((arr != new).any(axis=2)))
    return _png(new)


def extract_image(png: bytes, seed: bytes, probe=None) -> bytes:
    arr = np.array(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.uint8)
    if probe is not None:
        probe["width"] = int(arr.shape[1])
    return extract_bits(arr.reshape(-1), seed, probe)