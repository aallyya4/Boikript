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


def embed_image(png: bytes, payload: bytes, seed: bytes) -> bytes:
    arr = np.array(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.uint8)
    flat = embed_bits(arr.reshape(-1).copy(), payload, seed)
    out = io.BytesIO()
    Image.fromarray(flat.reshape(arr.shape)).save(out, format="PNG")
    return out.getvalue()


def extract_image(png: bytes, seed: bytes) -> bytes:
    arr = np.array(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.uint8)
    return extract_bits(arr.reshape(-1), seed)
