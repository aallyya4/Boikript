"""Super enkripsi untuk teks: Vigenere (klasik, level byte) -> AES-256-GCM (modern)."""
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def vigenere(data: bytes, key: bytes, decrypt: bool = False) -> bytes:
    sign = -1 if decrypt else 1
    return bytes((b + sign * key[i % len(key)]) % 256 for i, b in enumerate(data))


def encrypt_text(text: str, aes_key: bytes, vig_key: bytes) -> bytes:
    step1 = vigenere(text.encode("utf-8"), vig_key)          # lapis 1: klasik
    nonce = os.urandom(12)
    return nonce + AESGCM(aes_key).encrypt(nonce, step1, None)  # lapis 2: modern


def decrypt_text(blob: bytes, aes_key: bytes, vig_key: bytes) -> str:
    step1 = AESGCM(aes_key).decrypt(blob[:12], blob[12:], None)  # raise InvalidTag jika salah
    return vigenere(step1, vig_key, decrypt=True).decode("utf-8")
