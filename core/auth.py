"""Autentikasi: dongle (flashdisk), password (bcrypt), dan biometrik wajah (OpenCV LBPH)."""
import base64
import hashlib
import io
import os
import secrets

import bcrypt
import cv2
import numpy as np
import psutil

from . import db

KEYFILE = "SONICVAULT.key"
FACE_SIZE = (100, 100)
FACE_THRESHOLD = float(os.environ.get("SONICVAULT_FACE_THRESHOLD", "80"))  # makin kecil makin ketat
SKIP_FACE = os.environ.get("SONICVAULT_SKIP_FACE") == "1"                  # hanya untuk uji tanpa kamera
_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


# ------------------------------------------------------------------ dongle
def _is_removable(part) -> bool:
    if os.name == "nt":
        return "removable" in part.opts.lower()
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


# ------------------------------------------------------------------- wajah
def extract_face(image_bytes: bytes):
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    faces = _CASCADE.detectMultiScale(img, 1.2, 5, minSize=(80, 80))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return cv2.equalizeHist(cv2.resize(img[y:y + h, x:x + w], FACE_SIZE))


def _pack(faces) -> bytes:
    buf = io.BytesIO()
    np.save(buf, np.stack(faces))
    return buf.getvalue()


def _unpack(blob: bytes):
    return np.load(io.BytesIO(blob), allow_pickle=False)


def verify_face(image_bytes: bytes, enrolled):
    face = extract_face(image_bytes)
    if face is None:
        return False, -1.0
    rec = cv2.face.LBPHFaceRecognizer_create()
    rec.train(list(enrolled), np.zeros(len(enrolled), dtype=np.int32))
    _, dist = rec.predict(face)
    return dist < FACE_THRESHOLD, dist


# ------------------------------------------------------ daftar dan masuk
def register(db_key: bytes, username: str, password: str, photos):
    if not username or len(password) < 6:
        return False, "Username wajib diisi dan password minimal 6 karakter."
    if db.get_user(username):
        return False, "Username sudah dipakai."
    faces = [f for f in (extract_face(p) for p in photos) if f is not None]
    if not SKIP_FACE and len(faces) < 3:
        return False, f"Wajah terdeteksi di {len(faces)} foto, butuh minimal 3. Ulangi dengan wajah jelas dan cahaya cukup."
    blob = db.enc_field(db_key, _pack(faces), username.encode()) if faces else None
    db.add_user(username, hash_password(password), blob)
    return True, "Akun dibuat. Silakan masuk."


def login(db_key: bytes, username: str, password: str, photo):
    row = db.get_user(username)
    if row is None or not check_password(password, row["pw_hash"]):
        return False, "Username atau password salah."
    if SKIP_FACE:
        return True, "Masuk (mode uji, verifikasi wajah dilewati)."
    if photo is None:
        return False, "Ambil foto wajah dulu."
    if row["face"] is None:
        return False, "Akun ini tidak punya data wajah."
    faces = _unpack(db.dec_field(db_key, row["face"], username.encode()))
    ok, dist = verify_face(photo, faces)
    if dist < 0:
        return False, "Wajah tidak terdeteksi pada foto."
    return (True, "Masuk.") if ok else (False, f"Wajah tidak cocok (jarak {dist:.0f}, batas {FACE_THRESHOLD:.0f}).")
