"""Autentikasi: dongle (flashdisk), password (bcrypt), dan biometrik sidik jari (WebAuthn / Windows Hello)."""
import base64
import hashlib
import json
import os
import secrets

import bcrypt
import psutil

from . import db

KEYFILE = "SONICVAULT.key"
SKIP_BIOMETRIC = os.environ.get("SONICVAULT_SKIP_BIOMETRIC") == "1"  # hanya untuk uji tanpa sensor


# ------------------------------------------------------------------ dongle
def _is_removable(part) -> bool:
    if os.name == "nt":
        # terima semua drive kecuali drive sistem; banyak flashdisk dilaporkan "fixed" oleh Windows
        return not part.mountpoint.upper().startswith(os.environ.get("SystemDrive", "C:").upper())
    return part.mountpoint.startswith(("/media", "/run/media", "/Volumes", "/mnt"))


def _candidate_dirs():
    env = os.environ.get("SONICVAULT_DONGLE_DIR")  # untuk uji tanpa flashdisk
    if env:
        yield env
    for part in psutil.disk_partitions(all=False):
        if _is_removable(part):
            yield part.mountpoint


def find_dongle():
    """Return kunci dongle (32 byte) jika flashdisk berisi key file valid, else None."""
    for d in _candidate_dirs():
        path = os.path.join(d, KEYFILE)
        try:
            if os.path.isfile(path):
                raw = open(path, "r").read().strip()
                if len(raw) == 64:
                    return bytes.fromhex(raw)
        except (OSError, ValueError):
            continue
    return None


def make_dongle(directory: str, force: bool = False) -> str:
    path = os.path.join(directory, KEYFILE)
    if os.path.exists(path) and not force:
        raise FileExistsError("Dongle sudah ada. Membuat ulang akan membuat data lama tak bisa dibuka.")
    with open(path, "w") as f:
        f.write(secrets.token_hex(32))
    return path


# ---------------------------------------------------------------- password
def _prehash(password: str) -> bytes:
    # SHA-256 dulu supaya password panjang tidak terpotong oleh batas 72 byte bcrypt
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(12))


def check_password(password: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(_prehash(password), hashed)


# ---------------------------------------------------------------- sidik jari
def get_fp_record(db_key: bytes, username: str):
    """Data kredensial WebAuthn milik user (id, kunci publik, sign count), atau None."""
    row = db.get_user(username)
    if not row or not row.get("fp"):
        return None
    return json.loads(db.dec_field(db_key, row["fp"], username.encode()))


def save_fp_record(db_key: bytes, username: str, record: dict):
    db.set_fp(username, db.enc_field(db_key, json.dumps(record).encode(), username.encode()))


# ------------------------------------------------------ daftar dan masuk
def register(db_key: bytes, username: str, password: str, fp=None):
    """Akun baru: password + sidik jari (hasil verifikasi WebAuthn) wajib."""
    if not username or len(password) < 6:
        return False, "Username wajib diisi dan password minimal 6 karakter."
    if db.get_user(username):
        return False, "Username sudah dipakai."
    if not fp and not SKIP_BIOMETRIC:
        return False, "Daftarkan sidik jari dulu (klik tombol sidik jari lalu sentuh sensor)."
    fp_blob = db.enc_field(db_key, json.dumps(fp).encode(), username.encode()) if fp else None
    db.add_user(username, hash_password(password), None, fp_blob)
    return True, "Akun dibuat. Silakan masuk."


def login(db_key: bytes, username: str, password: str, fp_verified: bool = False):
    """Password wajib, ditambah verifikasi sidik jari yang sudah lolos di server."""
    row = db.get_user(username)
    if row is None or not check_password(password, row["pw_hash"]):
        return False, "Username atau password salah."
    if SKIP_BIOMETRIC:
        return True, "Masuk (mode uji, biometrik dilewati)."
    if not fp_verified:
        return False, "Verifikasi sidik jari dulu."
    return True, "Masuk."