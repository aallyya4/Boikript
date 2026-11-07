"""Penurunan kunci: password -> root key (PBKDF2) -> kunci per slot (HKDF)."""
import hashlib
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 200_000


def new_salt(n: int = 16) -> bytes:
    return os.urandom(n)


def root_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    return kdf.derive(password.encode("utf-8"))


def slot_key(root: bytes, label: str, length: int = 32) -> bytes:
    """Kunci berbeda untuk tiap label, jadi satu kunci bocor tidak membuka slot lain."""
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None,
                info=label.encode("utf-8")).derive(root)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
