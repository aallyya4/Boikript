"""Enkripsi file/audio: ChaCha20-Poly1305 (sengaja beda dari algoritma teks)."""
import os

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + ChaCha20Poly1305(key).encrypt(nonce, data, None)


def decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    return ChaCha20Poly1305(key).decrypt(blob[:12], blob[12:], None)
