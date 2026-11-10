"""LSB steganografi dengan posisi bit diacak memakai kunci.

Tanpa kunci, penyerang tidak tahu di mana header panjang pesan berada,
jadi lagu/gambar biasa dan lagu/gambar berpesan sulit dibedakan.
"""
import hashlib

import numpy as np

HEADER_BITS = 32


def _order(n: int, seed: bytes) -> np.ndarray:
    s = int.from_bytes(hashlib.sha256(seed).digest()[:8], "big")
    return np.random.default_rng(s).permutation(n)


def capacity(n_slots: int) -> int:
    """Kapasitas dalam byte untuk n_slots elemen (1 bit per elemen)."""
    return max((n_slots - HEADER_BITS) // 8, 0)


def embed_bits(flat: np.ndarray, payload: bytes, seed: bytes, probe=None) -> np.ndarray:
    """Sisipkan payload ke bit terakhir elemen flat. Jika probe (dict) diberikan, isi dengan rincian proses."""
    data = len(payload).to_bytes(4, "big") + payload
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    if bits.size > flat.size:
        raise ValueError(
            f"Pembawa terlalu kecil: muat ±{capacity(flat.size)} byte, pesan butuh {len(payload)} byte."
        )
    idx = _order(flat.size, seed)[: bits.size]
    before = flat[idx].copy()
    new = ((before >> 1) << 1) | bits.astype(flat.dtype)
    flat[idx] = new
    if probe is not None:
        probe.update(
            n_bits=int(bits.size), total=int(flat.size), flips=int(((before ^ new) & 1).sum()),
            rows=[[int(idx[i]), int(before[i]), int(new[i]), int(bits[i])] for i in range(min(10, bits.size))])
    return flat


def extract_bits(flat: np.ndarray, seed: bytes, probe=None) -> bytes:
    order = _order(flat.size, seed)
    head = (flat[order[:HEADER_BITS]] & 1).astype(np.uint8)
    n = int.from_bytes(np.packbits(head).tobytes(), "big")
    if probe is not None:
        probe.update(total=int(flat.size), length=n,
                     rows=[[int(order[i]), int(flat[order[i]]), int(flat[order[i]] & 1)]
                           for i in range(min(10, flat.size))])
    if n == 0 or HEADER_BITS + n * 8 > flat.size:
        raise ValueError("Tidak ada pesan (atau kunci salah).")
    body = (flat[order[HEADER_BITS: HEADER_BITS + n * 8]] & 1).astype(np.uint8)
    if probe is not None:
        probe["n_bits"] = HEADER_BITS + n * 8
    return np.packbits(body).tobytes()