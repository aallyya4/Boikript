"""Steganografi teks: ciphertext disembunyikan di lirik memakai karakter zero-width."""
ZERO, ONE = "\u200b", "\u200c"


def embed_text(cover: str, payload: bytes) -> str:
    data = len(payload).to_bytes(4, "big") + payload
    bits = "".join(f"{b:08b}" for b in data)
    return cover + "".join(ONE if c == "1" else ZERO for c in bits)


def extract_text(text: str) -> bytes:
    bits = "".join("1" if ch == ONE else "0" for ch in text if ch in (ZERO, ONE))
    if len(bits) < 32:
        raise ValueError("Tidak ada pesan di lirik.")
    n = int(bits[:32], 2)
    if n == 0 or len(bits) < 32 + n * 8:
        raise ValueError("Tidak ada pesan di lirik.")
    return int(bits[32: 32 + n * 8], 2).to_bytes(n, "big")
