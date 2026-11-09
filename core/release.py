"""Pembuatan dan pembukaan 'rilisan' lagu: pesan dipecah ke cover, audio, lirik, lampiran."""
import io
import json
import os
import re
import secrets
import shutil
import wave
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from PIL import Image, ImageOps

from . import blockchain, db, keys
from .crypto_file import decrypt_bytes, encrypt_bytes
from .crypto_text import decrypt_text_steps, encrypt_text_steps
from .stego_audio import embed_audio, extract_audio
from .stego_image import embed_image, extract_image, to_png
from .stego_text import ONE, ZERO, embed_text, extract_text

STORAGE = os.environ.get("SONICVAULT_STORAGE", "storage")
ALLOWED = {"audio.wav", "cover.png", "lyrics.txt", "attach.enc", "meta.json"}
RID_RE = re.compile(r"^[0-9a-f]{8}$")
FAIL = (ValueError, InvalidTag, wave.Error, OSError)  # gagal ekstrak/dekripsi = slot kosong


def _dir(rid: str) -> Path:
    if not RID_RE.match(str(rid)):
        raise ValueError("Kode tidak valid.")
    return Path(STORAGE) / rid


def _hex(b: bytes, n: int = 48) -> str:
    return b[:n].hex() + (f" ... (total {len(b)} byte)" if len(b) > n else f"  ({len(b)} byte)")


def _t(trace, slot: str, label: str, steps: list):
    if trace is not None:
        trace.append({"slot": slot, "label": label, "steps": steps})


def _text_keys(root: bytes, name: str):
    return keys.slot_key(root, f"{name}-aes"), keys.slot_key(root, f"{name}-vig", 16)


SLOT_NAMES = {"cover": "Cover", "audio": "Audio", "lyrics": "Lirik", "attach": "Lampiran"}


def _root_getter(pw, salt: bytes):
    """Satu kunci induk per kata sandi unik (PBKDF2 mahal, jadi di-cache)."""
    cache = {}

    def root(slot: str) -> bytes:
        p = pw(slot)
        if p not in cache:
            cache[p] = keys.root_key(p, salt)
        return cache[p]
    return root


def create_release(db_key, owner, title, artist, carrier_wav, cover_img, lyrics,
                   password=None, cover_text=None, voice=None, lyrics_text=None, attach=None,
                   trace=None, slot_keys=None):
    """Buat lagu. Semua pesan rahasia opsional; tanpa satu pun, hasilnya lagu biasa.

    Tiap bagian punya kunci sendiri lewat slot_keys = {"cover": ..., "audio": ..., "lyrics": ..., "attach": ...}.
    Jika sebuah bagian tidak punya kunci sendiri, dipakai `password` (kunci bersama).
    db_key boleh None untuk lagu publik (upload dari pemutar biasa)."""
    slot_keys = slot_keys or {}

    def pw(slot):
        return slot_keys.get(slot) or password

    used = {"cover": cover_text, "audio": voice, "lyrics": lyrics_text, "attach": attach}
    for slot, val in used.items():
        if val and not pw(slot):
            raise ValueError(f"Isi kunci untuk bagian {SLOT_NAMES[slot]}.")
    rid = secrets.token_hex(4)
    salt = keys.new_salt()
    root = _root_getter(pw, salt)

    cover_png, audio, public = to_png(cover_img), carrier_wav, lyrics
    attach_blob = None
    if any(used.values()):
        _t(trace, "kunci", "Kunci", [("Penurunan kunci",
           "Tiap bagian punya kunci sendiri. Kunci + salt acak -> PBKDF2 (200.000 iterasi) -> HKDF -> kunci enkripsi "
           "dan kunci posisi bit. Satu kunci yang bocor tidak membuka bagian lain. Kunci tidak ditampilkan.")])
    if cover_text:  # slot cover: super enkripsi + LSB gambar
        ek, vk = _text_keys(root("cover"), "cover")
        vig, blob = encrypt_text_steps(cover_text, ek, vk)
        cover_png = embed_image(cover_png, blob, keys.slot_key(root("cover"), "cover-pos"))
        _t(trace, "cover", "Cover album (teks: super enkripsi + steganografi gambar)", [
            ("1. Teks asli (plaintext)", cover_text),
            ("2. Vigenere (klasik), hasil dalam hex", _hex(vig)),
            ("3. AES-256-GCM (modern) = ciphertext akhir: nonce + isi + tag, dalam hex", _hex(blob)),
            ("4. Steganografi LSB", f"{len(blob) * 8 + 32:,} bit disisipkan ke bit terakhir piksel cover "
                                    "(posisi diacak oleh kunci). Gambar tampak sama.")])
    if voice:       # slot audio: ChaCha20 + LSB audio
        blob = encrypt_bytes(voice, keys.slot_key(root("audio"), "audio-enc"))
        audio = embed_audio(audio, blob, keys.slot_key(root("audio"), "audio-pos"))
        _t(trace, "audio", "Audio (pesan suara: enkripsi file + steganografi audio)", [
            ("1. Pesan suara asli", f"file WAV {len(voice):,} byte"),
            ("2. ChaCha20-Poly1305 = ciphertext akhir: nonce + isi + tag, awalnya dalam hex", _hex(blob)),
            ("3. Steganografi LSB", f"{len(blob) * 8 + 32:,} bit disisipkan ke bit terakhir sampel lagu "
                                    "(posisi diacak oleh kunci). Lagu terdengar sama.")])
    if lyrics_text:  # slot lirik: super enkripsi + zero-width
        ek, vk = _text_keys(root("lyrics"), "lyrics")
        vig, blob = encrypt_text_steps(lyrics_text, ek, vk)
        public = embed_text(lyrics, blob)
        _t(trace, "lyrics", "Lirik (teks: super enkripsi + steganografi teks)", [
            ("1. Teks asli (plaintext)", lyrics_text),
            ("2. Vigenere (klasik), hasil dalam hex", _hex(vig)),
            ("3. AES-256-GCM (modern) = ciphertext akhir: nonce + isi + tag, dalam hex", _hex(blob)),
            ("4. Steganografi teks", f"{len(public) - len(lyrics):,} karakter tak terlihat (zero-width) "
                                     "ditambahkan di ujung lirik. Lirik tampak sama.")])
    if attach:      # slot lampiran: ChaCha20
        name, data = attach
        nb = name.encode("utf-8")
        attach_blob = encrypt_bytes(len(nb).to_bytes(2, "big") + nb + data, keys.slot_key(root("attach"), "attach-enc"))
        _t(trace, "attach", "Lampiran (enkripsi file)", [
            ("1. File asli", f"{name} ({len(data):,} byte)"),
            ("2. ChaCha20-Poly1305 = ciphertext akhir, awalnya dalam hex", _hex(attach_blob)),
            ("3. Disimpan sebagai", "attach.enc (isinya acak jika dibuka di Notepad)")])

    meta = {"id": rid, "title": title, "artist": artist, "salt": salt.hex()}
    files = {"audio.wav": audio, "cover.png": cover_png, "lyrics.txt": public.encode("utf-8")}
    if attach_blob:
        files["attach.enc"] = attach_blob
    d = _dir(rid)
    d.mkdir(parents=True)
    for fname, blob in files.items():
        (d / fname).write_bytes(blob)
    (d / "meta.json").write_text(json.dumps(meta))

    blockchain.add_block({"release": rid, "owner": owner, "action": "create",
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


HIDDEN = (ZERO, ONE)


def read_meta(rid: str) -> dict:
    return json.loads((_dir(rid) / "meta.json").read_text())


def visible_lyrics(rid: str) -> str:
    """Lirik tanpa karakter tak terlihat (bagian itu bisa membawa pesan rahasia)."""
    return "".join(c for c in read_lyrics(rid) if c not in HIDDEN)


def can_manage(rid: str, who: str) -> bool:
    """'publik' hanya boleh mengubah lagu publik. Pengguna mode kripto boleh mengubah lagu miliknya,
    lagu publik, dan lagu tanpa catatan pemilik (hasil impor)."""
    owner = blockchain.owner_of(rid)
    return owner == "publik" if who == "publik" else owner in (who, "publik", None)


def update_song(rid: str, who: str, db_key=None, title=None, artist=None, lyrics=None):
    """Ubah judul, artis, dan/atau lirik tampak. Pesan tersembunyi di lirik tetap dipertahankan."""
    if not can_manage(rid, who):
        raise ValueError("Tidak diizinkan mengubah lagu ini.")
    meta = read_meta(rid)
    if title is not None:
        if not title.strip():
            raise ValueError("Judul tidak boleh kosong.")
        meta["title"] = title.strip()
    if artist is not None:
        if not artist.strip():
            raise ValueError("Artis tidak boleh kosong.")
        meta["artist"] = artist.strip()
    d = _dir(rid)
    (d / "meta.json").write_text(json.dumps(meta))
    if lyrics is not None:
        old = read_lyrics(rid)
        hidden = "".join(c for c in old if c in HIDDEN)  # muatan tersembunyi ikut dipindah ke lirik baru
        new = "".join(c for c in lyrics if c not in HIDDEN) + hidden
        if new != old:
            raw = new.encode("utf-8")
            (d / "lyrics.txt").write_bytes(raw)
            blockchain.add_block({"release": rid, "owner": who, "action": "update",
                                  "files": {"lyrics": keys.sha256_hex(raw)}})
    if db_key is not None and db.has_track(rid):
        db.put_track(db_key, who, rid, meta)


def delete_song(rid: str, who: str):
    """Hapus lagu. Riwayatnya tetap ada di blockchain (rantai hanya bisa ditambah)."""
    if not can_manage(rid, who):
        raise ValueError("Tidak diizinkan menghapus lagu ini.")
    shutil.rmtree(_dir(rid))
    db.delete_track(rid)
    blockchain.add_block({"release": rid, "owner": who, "action": "delete", "files": {}})


def read_public(rid: str) -> dict:
    d = _dir(rid)
    if not (d / "meta.json").exists():
        raise ValueError("Kode tidak ditemukan.")
    attach = (d / "attach.enc").read_bytes() if (d / "attach.enc").exists() else None
    return {"audio": (d / "audio.wav").read_bytes(), "cover": (d / "cover.png").read_bytes(),
            "lyrics": (d / "lyrics.txt").read_bytes().decode("utf-8"), "attach": attach}


def open_release(rid: str, password=None, slot_keys=None) -> dict:
    """Coba buka tiap bagian dengan kuncinya masing-masing (slot_keys). Bagian tanpa kunci dilewati.
    Bagian yang gagal (kunci salah / memang kosong) dianggap kosong; keduanya tidak bisa dibedakan."""
    slot_keys = slot_keys or {}

    def pw(slot):
        return slot_keys.get(slot) or password

    pub = read_public(rid)
    meta = json.loads((_dir(rid) / "meta.json").read_text())
    root = _root_getter(pw, bytes.fromhex(meta["salt"]))
    tr = []
    out = {"meta": meta, "pub": pub, "cover": None, "audio": None, "lyrics": None, "attach": None,
           "skipped": [], "trace": tr}
    none = ("Hasil", "Tidak ada pesan, atau kunci salah (tag keaslian tidak cocok), jadi dianggap kosong.")
    skip = ("Hasil", "Kunci bagian ini belum diisi, bagian dilewati.")

    if not pw("cover"):
        out["skipped"].append("cover"); _t(tr, "cover", "Cover album", [skip])
    else:
        try:
            ek, vk = _text_keys(root("cover"), "cover")
            ct = extract_image(pub["cover"], keys.slot_key(root("cover"), "cover-pos"))
            vig, text = decrypt_text_steps(ct, ek, vk)
            out["cover"] = text
            _t(tr, "cover", "Cover album", [
                ("1. Ciphertext diambil dari bit terakhir piksel (hex)", _hex(ct)),
                ("2. Dekripsi AES-256-GCM, hasilnya tahap Vigenere (hex)", _hex(vig)),
                ("3. Balik Vigenere = teks asli", text)])
        except FAIL:
            _t(tr, "cover", "Cover album", [none])

    if not pw("audio"):
        out["skipped"].append("audio"); _t(tr, "audio", "Audio", [skip])
    else:
        try:
            blob = extract_audio(pub["audio"], keys.slot_key(root("audio"), "audio-pos"))
            out["audio"] = decrypt_bytes(blob, keys.slot_key(root("audio"), "audio-enc"))
            _t(tr, "audio", "Audio", [
                ("1. Ciphertext diambil dari bit terakhir sampel lagu (hex)", _hex(blob)),
                ("2. Dekripsi ChaCha20-Poly1305 = pesan suara asli", f"file WAV {len(out['audio']):,} byte (bisa diputar)")])
        except FAIL:
            _t(tr, "audio", "Audio", [none])

    if not pw("lyrics"):
        out["skipped"].append("lyrics"); _t(tr, "lyrics", "Lirik", [skip])
    else:
        try:
            ek, vk = _text_keys(root("lyrics"), "lyrics")
            ct = extract_text(pub["lyrics"])
            vig, text = decrypt_text_steps(ct, ek, vk)
            out["lyrics"] = text
            _t(tr, "lyrics", "Lirik", [
                ("1. Ciphertext diambil dari karakter tak terlihat di lirik (hex)", _hex(ct)),
                ("2. Dekripsi AES-256-GCM, hasilnya tahap Vigenere (hex)", _hex(vig)),
                ("3. Balik Vigenere = teks asli", text)])
        except FAIL:
            _t(tr, "lyrics", "Lirik", [none])

    if pub["attach"]:
        if not pw("attach"):
            out["skipped"].append("attach"); _t(tr, "attach", "Lampiran", [skip])
        else:
            try:
                raw = decrypt_bytes(pub["attach"], keys.slot_key(root("attach"), "attach-enc"))
                n = int.from_bytes(raw[:2], "big")
                out["attach"] = (raw[2:2 + n].decode("utf-8"), raw[2 + n:])
                _t(tr, "attach", "Lampiran", [
                    ("1. Isi attach.enc (ciphertext, hex)", _hex(pub["attach"])),
                    ("2. Dekripsi ChaCha20-Poly1305 = file asli", f"{out['attach'][0]} ({len(out['attach'][1]):,} byte)")])
            except FAIL:
                _t(tr, "attach", "Lampiran", [none])
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