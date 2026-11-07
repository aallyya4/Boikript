"""Pembuatan dan pembukaan 'rilisan' lagu: pesan dipecah ke cover, audio, lirik, lampiran."""
import io
import json
import os
import re
import secrets
import wave
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from PIL import Image, ImageOps

from . import blockchain, db, keys
from .crypto_file import decrypt_bytes, encrypt_bytes
from .crypto_text import decrypt_text, encrypt_text
from .stego_audio import embed_audio, extract_audio
from .stego_image import embed_image, extract_image, to_png
from .stego_text import embed_text, extract_text

STORAGE = os.environ.get("SONICVAULT_STORAGE", "storage")
ALLOWED = {"audio.wav", "cover.png", "lyrics.txt", "attach.enc", "meta.json"}
RID_RE = re.compile(r"^[0-9a-f]{8}$")
FAIL = (ValueError, InvalidTag, wave.Error, OSError)  # gagal ekstrak/dekripsi = slot kosong


def _dir(rid: str) -> Path:
    if not RID_RE.match(str(rid)):
        raise ValueError("Kode tidak valid.")
    return Path(STORAGE) / rid


def _text_keys(root: bytes, name: str):
    return keys.slot_key(root, f"{name}-aes"), keys.slot_key(root, f"{name}-vig", 16)


def create_release(db_key, owner, title, artist, carrier_wav, cover_img, lyrics,
                   password=None, cover_text=None, voice=None, lyrics_text=None, attach=None):
    """Buat lagu. Semua pesan rahasia opsional; tanpa satu pun, hasilnya lagu biasa.
    db_key boleh None untuk lagu publik (upload dari pemutar biasa)."""
    wants = any([cover_text, voice, lyrics_text, attach])
    if wants and not password:
        raise ValueError("Isi kunci pesan untuk menyimpan pesan rahasia.")
    rid = secrets.token_hex(4)
    salt = keys.new_salt()
    root = keys.root_key(password, salt) if wants else None

    cover_png, audio, public = to_png(cover_img), carrier_wav, lyrics
    attach_blob = None
    if cover_text:  # slot cover: super enkripsi + LSB gambar
        ek, vk = _text_keys(root, "cover")
        cover_png = embed_image(cover_png, encrypt_text(cover_text, ek, vk), keys.slot_key(root, "cover-pos"))
    if voice:       # slot audio: ChaCha20 + LSB audio
        blob = encrypt_bytes(voice, keys.slot_key(root, "audio-enc"))
        audio = embed_audio(audio, blob, keys.slot_key(root, "audio-pos"))
    if lyrics_text:  # slot lirik: super enkripsi + zero-width
        ek, vk = _text_keys(root, "lyrics")
        public = embed_text(lyrics, encrypt_text(lyrics_text, ek, vk))
    if attach:      # slot lampiran: ChaCha20
        name, data = attach
        nb = name.encode("utf-8")
        attach_blob = encrypt_bytes(len(nb).to_bytes(2, "big") + nb + data, keys.slot_key(root, "attach-enc"))

    meta = {"id": rid, "title": title, "artist": artist, "salt": salt.hex()}
    files = {"audio.wav": audio, "cover.png": cover_png, "lyrics.txt": public.encode("utf-8")}
    if attach_blob:
        files["attach.enc"] = attach_blob
    d = _dir(rid)
    d.mkdir(parents=True)
    for fname, blob in files.items():
        (d / fname).write_bytes(blob)
    (d / "meta.json").write_text(json.dumps(meta))

    blockchain.add_block({"release": rid, "owner": owner,
                          "files": {n.split(".")[0]: keys.sha256_hex(b) for n, b in files.items()}})
    if db_key is not None:  # lagu publik (tanpa dongle) tidak masuk katalog terenkripsi
        db.put_track(db_key, owner, rid, meta)
    return rid


def list_public() -> list:
    """Daftar lagu untuk pemutar publik (judul dan artis saja), dibaca tanpa dongle."""
    out = []
    metas = sorted(Path(STORAGE).glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for m in metas:
        try:
            meta = json.loads(m.read_text())
            if RID_RE.match(str(meta["id"])):
                out.append({k: meta[k] for k in ("id", "title", "artist")})
        except (OSError, ValueError, KeyError):
            continue
    return out


def read_audio(rid: str) -> bytes:
    return (_dir(rid) / "audio.wav").read_bytes()


def read_lyrics(rid: str) -> str:
    return (_dir(rid) / "lyrics.txt").read_bytes().decode("utf-8")


def cover_thumb(rid: str, size: int = 300) -> bytes:
    """Thumbnail persegi (JPEG) untuk kartu lagu."""
    im = Image.open(_dir(rid) / "cover.png").convert("RGB")
    buf = io.BytesIO()
    ImageOps.fit(im, (size, size)).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def cover_color(rid: str):
    """Warna rata-rata cover (dibatasi agar teks putih tetap terbaca), untuk latar gradasi."""
    im = Image.open(_dir(rid) / "cover.png").convert("RGB").resize((1, 1), Image.LANCZOS)
    r, g, b = im.getpixel((0, 0))
    m = max(r, g, b, 1)
    k = 150 / m if m > 150 else 1
    return int(r * k), int(g * k), int(b * k)


def read_public(rid: str) -> dict:
    d = _dir(rid)
    if not (d / "meta.json").exists():
        raise ValueError("Kode tidak ditemukan.")
    attach = (d / "attach.enc").read_bytes() if (d / "attach.enc").exists() else None
    return {"audio": (d / "audio.wav").read_bytes(), "cover": (d / "cover.png").read_bytes(),
            "lyrics": (d / "lyrics.txt").read_bytes().decode("utf-8"), "attach": attach}


def open_release(rid: str, password: str) -> dict:
    """Coba buka tiap slot. Slot yang gagal dianggap kosong (lagu biasa / kunci salah)."""
    pub = read_public(rid)
    meta = json.loads((_dir(rid) / "meta.json").read_text())
    root = keys.root_key(password, bytes.fromhex(meta["salt"]))
    out = {"meta": meta, "pub": pub, "cover": None, "audio": None, "lyrics": None, "attach": None}
    try:
        ek, vk = _text_keys(root, "cover")
        out["cover"] = decrypt_text(extract_image(pub["cover"], keys.slot_key(root, "cover-pos")), ek, vk)
    except FAIL:
        pass
    try:
        blob = extract_audio(pub["audio"], keys.slot_key(root, "audio-pos"))
        out["audio"] = decrypt_bytes(blob, keys.slot_key(root, "audio-enc"))
    except FAIL:
        pass
    try:
        ek, vk = _text_keys(root, "lyrics")
        out["lyrics"] = decrypt_text(extract_text(pub["lyrics"]), ek, vk)
    except FAIL:
        pass
    if pub["attach"]:
        try:
            raw = decrypt_bytes(pub["attach"], keys.slot_key(root, "attach-enc"))
            n = int.from_bytes(raw[:2], "big")
            out["attach"] = (raw[2:2 + n].decode("utf-8"), raw[2 + n:])
        except FAIL:
            pass
    return out


def export_zip(rid: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for f in _dir(rid).iterdir():
            if f.name in ALLOWED:
                z.write(f, f.name)
    return buf.getvalue()


def import_zip(db_key, owner, data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        if "meta.json" not in names or not names <= ALLOWED:
            raise ValueError("Paket tidak valid.")
        meta = json.loads(z.read("meta.json"))
        rid = str(meta["id"])
        d = _dir(rid)
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            (d / n).write_bytes(z.read(n))
    db.put_track(db_key, owner, rid, {k: meta[k] for k in ("id", "title", "artist", "salt")})
    return rid