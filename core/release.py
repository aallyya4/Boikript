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


LABELS = {"kunci": "🔑 Kunci", "cover": "📍 Cover", "audio": "🎙️ Audio", "lyrics": "🕒 Lirik", "attach": "📎 Dokumen"}


def _hex(b: bytes, n: int = 48) -> str:
    return b[:n].hex() + (f" ... (total {len(b)} byte)" if len(b) > n else f"  ({len(b)} byte)")


def _t(trace, slot: str, steps: list, flow=None):
    if trace is not None:
        trace.append({"slot": slot, "label": LABELS[slot], "steps": steps, "flow": flow or []})


def _step(title: str, kind: str, value, algo=None, note=None) -> dict:
    """kind: text | hex | table | parts | images."""
    return {"title": title, "kind": kind, "value": value, "algo": algo, "note": note}


def _chars(data: bytes, n: int = 8) -> dict:
    rows = [[chr(b) if 32 <= b < 127 else "·", b, f"{b:02x}", f"{b:08b}"] for b in data[:n]]
    return {"cols": ["Karakter", "Desimal", "Hex", "Biner"], "rows": rows}


def _vig(inp: bytes, key: bytes, out: bytes, back: bool = False, n: int = 8) -> dict:
    op = "−" if back else "+"
    rows = [[i + 1, inp[i], key[i % len(key)], out[i]] for i in range(min(n, len(inp)))]
    return {"cols": ["#", "Byte masuk", "Byte kunci", f"Hasil (masuk {op} kunci) mod 256"], "rows": rows, "secret": [2]}


def _parts(blob: bytes) -> list:
    nonce, tag, body = blob[:12], blob[-16:], blob[12:-16]
    return [("Nonce, 12 byte (acak, diletakkan di depan)", nonce.hex()),
            (f"Isi terenkripsi, {len(body)} byte", _hex(body)),
            ("Tag keaslian, 16 byte", tag.hex())]


def _bits(payload: bytes) -> str:
    s = "".join(f"{b:08b}" for b in len(payload).to_bytes(4, "big") + payload)
    group = lambda x: " ".join(x[i:i + 8] for i in range(0, len(x), 8))
    return (f"Header panjang (32 bit):  {group(s[:32])}\n"
            f"Isi, 64 bit pertama:     {group(s[32:96])}\n"
            f"Total {len(s):,} bit = 32 bit header + {len(payload) * 8:,} bit ciphertext")


def _img_rows(rows: list, width: int, read: bool = False) -> dict:
    out = []
    for r in rows:
        pix, c = divmod(r[0], 3)
        where = f"({pix % width}, {pix // width}) kanal {'RGB'[c]}"
        out.append([where, r[1], r[2]] if read else [where, r[1], r[2], r[3]])
    cols = ["Lokasi (piksel x,y)", "Nilai warna", "Bit paling kanan"] if read else \
           ["Lokasi (piksel x,y)", "Nilai sebelum", "Nilai sesudah", "Bit pesan"]
    return {"cols": cols, "rows": out}


def _smp_rows(rows: list, read: bool = False) -> dict:
    out = [[f"sampel #{r[0]}"] + r[1:] for r in rows]
    cols = ["Lokasi", "Nilai sampel", "Bit paling kanan"] if read else ["Lokasi", "Nilai sebelum", "Nilai sesudah", "Bit pesan"]
    return {"cols": cols, "rows": out}


def _fail(e) -> dict:
    why = ("Ciphertext terbaca, tetapi tag keaslian tidak cocok" if isinstance(e, InvalidTag)
           else "Panjang pesan yang terbaca tidak masuk akal, atau format tidak valid")
    return _step("Hasil", "text", f"{why}.\nArtinya tidak ada pesan di bagian ini, atau kuncinya salah. Bagian ini dianggap kosong.")


def _text_enc_steps(text: str, vk: bytes, vig: bytes, blob: bytes) -> list:
    raw = text.encode("utf-8")
    return [
        _step("Teks asli diubah menjadi byte (UTF-8)", "table", _chars(raw),
              note=f"{len(raw)} byte. Tabel menampilkan 8 byte pertama."),
        _step("Tahap 1: Vigenère (sandi klasik)", "table", _vig(raw, vk, vig), algo="Vigenère",
              note="Tiap byte teks ditambah byte kunci (kunci diulang), lalu dibagi sisa 256. Hasilnya sudah tidak terbaca."),
        _step("Hasil tahap 1 (hex)", "hex", _hex(vig), note="Sandi klasik sendirian lemah, sehingga ditumpuk dengan tahap 2."),
        _step("Tahap 2: AES-256-GCM (sandi modern)", "parts", _parts(blob), algo="AES-256-GCM",
              note="Hasil tahap 1 dienkripsi lagi. Nonce acak dibuat baru tiap enkripsi, jadi teks yang sama menghasilkan "
                   "ciphertext berbeda. Tag 16 byte mendeteksi kunci salah atau data yang diubah. Ini ciphertext akhir (acak)."),
        _step("Ciphertext diubah menjadi deretan bit", "text", _bits(blob),
              note="Bit inilah yang akan disembunyikan. 32 bit pertama memberi tahu panjang pesan."),
    ]


def _text_dec_steps(ct: bytes, vig: bytes, vk: bytes, text: str) -> list:
    return [
        _step("Bit digabung menjadi ciphertext", "parts", _parts(ct),
              note=f"Panjang terbaca {len(ct)} byte: nonce, isi terenkripsi, dan tag."),
        _step("Tahap 1 terbalik: AES-256-GCM dekripsi", "hex", _hex(vig), algo="AES-256-GCM",
              note="Tag dicek lebih dulu: cocok, jadi kunci benar dan data tidak diubah. Hasil dekripsi (hex) adalah keluaran Vigenère."),
        _step("Tahap 2 terbalik: Vigenère", "table", _vig(vig, vk, text.encode("utf-8"), back=True), algo="Vigenère",
              note="Tiap byte dikurangi byte kunci, lalu dibagi sisa 256."),
        _step("Teks asli kembali", "text", text),
    ]


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
    db_key boleh None untuk lagu publik (upload dari pemutar biasa).
    trace (list) diisi rincian tiap tahap enkripsi dan penyembunyian untuk ditampilkan."""
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
        _t(trace, "kunci", [_step(
            "Dari kunci yang kamu ketik menjadi kunci enkripsi", "text",
            f"Salt acak (tidak rahasia): {salt.hex()}\n"
            f"PBKDF2-SHA256: {keys.ITERATIONS:,} iterasi (membuat tebak-tebakan kunci jadi lambat)\n"
            "HKDF: kunci dipecah per bagian dan per fungsi, misalnya cover-aes, cover-vig, cover-pos\n"
            "Satu kunci yang bocor tidak membuka bagian lain. Nilai kunci tidak ditampilkan.",
            algo="PBKDF2 + HKDF")],
            flow=["Kunci ketikan", "PBKDF2 + salt", "Kunci induk", "HKDF per bagian", "Kunci enkripsi dan posisi"])

    if cover_text:  # slot cover: super enkripsi + LSB gambar
        ek, vk = _text_keys(root("cover"), "cover")
        vig, blob = encrypt_text_steps(cover_text, ek, vk)
        probe = {}
        cover_png = embed_image(cover_png, blob, keys.slot_key(root("cover"), "cover-pos"), probe)
        steps = _text_enc_steps(cover_text, vk, vig, blob) + [
            _step("Bit disisipkan ke bit paling kanan piksel cover", "table", _img_rows(probe["rows"], probe["width"]), algo="LSB",
                  note=f"{probe['n_bits']:,} bit disisipkan ke {probe['n_bits']:,} dari {probe['total']:,} nilai warna. Posisinya diacak "
                       "oleh kunci posisi (kolom Lokasi). Hanya bit paling kanan yang diganti, jadi nilai warna berubah paling banyak 1. "
                       "Tabel menampilkan 10 bit pertama."),
            _step("Hasil: yang terlihat sekarang", "images",
                  [("Cover sebelum", probe["before_img"]), ("Cover sesudah", probe["after_img"]),
                   ("Peta perubahan (titik hijau)", probe["diff_img"])],
                  note=f"Hanya {probe['values_changed']:,} dari {probe['total']:,} nilai warna yang benar-benar berubah "
                       f"({probe['values_changed'] / probe['total']:.3%}), masing-masing ±1. Gambar sebelum dan sesudah tampak "
                       "sama; pesan aslinya tidak terlihat lagi, yang ada hanya ciphertext acak yang tersebar.")]
        _t(trace, "cover", steps, flow=["Teks asli", "Vigenère", "AES-256-GCM", "Deretan bit", "LSB piksel", "Cover tampak biasa"])

    if voice:       # slot audio: ChaCha20 + LSB audio
        blob = encrypt_bytes(voice, keys.slot_key(root("audio"), "audio-enc"))
        probe = {}
        audio = embed_audio(audio, blob, keys.slot_key(root("audio"), "audio-pos"), probe)
        _t(trace, "audio", [
            _step("Pesan suara asli (file)", "text", f"File WAV {len(voice):,} byte\n16 byte pertama (hex): {voice[:16].hex()}  → 'RIFF....WAVE'",
                  note="File diperlakukan sebagai deretan byte, bukan teks."),
            _step("Enkripsi file: ChaCha20-Poly1305", "parts", _parts(blob), algo="ChaCha20-Poly1305",
                  note="Algoritma sengaja berbeda dari yang dipakai untuk teks (syarat dosen). Nonce acak di depan, tag 16 byte di belakang."),
            _step("Ciphertext diubah menjadi deretan bit", "text", _bits(blob)),
            _step("Bit disisipkan ke bit paling kanan sampel lagu", "table", _smp_rows(probe["rows"]), algo="LSB",
                  note=f"{probe['n_bits']:,} bit masuk ke {probe['n_bits']:,} dari {probe['total']:,} sampel. Lokasi diacak oleh kunci posisi."),
            _step("Hasil: yang terdengar sekarang", "text",
                  f"{probe['flips']:,} dari {probe['total']:,} sampel benar-benar berubah, masing-masing paling banyak 1 "
                  f"dari rentang ±32.768 (sekitar −90 dB).\nTelinga tidak bisa membedakannya; lagu terdengar sama persis dan "
                  "pesan aslinya tidak terdengar.")],
            flow=["File suara", "ChaCha20-Poly1305", "Deretan bit", "LSB sampel", "Lagu terdengar biasa"])

    if lyrics_text:  # slot lirik: super enkripsi + zero-width
        ek, vk = _text_keys(root("lyrics"), "lyrics")
        vig, blob = encrypt_text_steps(lyrics_text, ek, vk)
        public = embed_text(lyrics, blob)
        hidden = public[len(lyrics):]
        sym = hidden.replace(ZERO, "0").replace(ONE, "1")
        _t(trace, "lyrics", _text_enc_steps(lyrics_text, vk, vig, blob) + [
            _step("Bit diubah menjadi karakter tak terlihat", "table",
                  {"cols": ["Bit", "Karakter yang ditempel", "Kode Unicode"],
                   "rows": [[0, "zero-width space (tak terlihat)", "U+200B"], [1, "zero-width non-joiner (tak terlihat)", "U+200C"]]},
                  algo="Zero-width",
                  note=f"Tiap bit menjadi satu karakter yang lebarnya nol, ditempel di ujung lirik: {len(hidden):,} karakter."),
            _step("Hasil: yang terlihat sekarang", "text",
                  f"Lirik tampak : {lyrics[:80]}{'…' if len(lyrics) > 80 else ''}\n"
                  f"Panjang      : {len(lyrics):,} karakter sebelum → {len(public):,} karakter sesudah ({len(hidden):,} tak terlihat)\n"
                  f"Jika karakter tak terlihat dibuat tampak (0/1): {sym[:64]}…",
                  note="Di layar, lirik sebelum dan sesudah tampak identik. Pesan aslinya tidak ada; yang tersimpan hanya bit ciphertext.")],
            flow=["Teks asli", "Vigenère", "AES-256-GCM", "Deretan bit", "Karakter tak terlihat", "Lirik tampak biasa"])

    if attach:      # slot dokumen pendukung: ChaCha20
        name, data = attach
        nb = name.encode("utf-8")
        attach_blob = encrypt_bytes(len(nb).to_bytes(2, "big") + nb + data, keys.slot_key(root("attach"), "attach-enc"))
        _t(trace, "attach", [
            _step("Dokumen asli (file)", "text", f"{name}  ({len(data):,} byte)\n16 byte pertama (hex): {data[:16].hex()}",
                  note="Nama file dan isinya digabung, lalu diperlakukan sebagai deretan byte."),
            _step("Enkripsi file: ChaCha20-Poly1305", "parts", _parts(attach_blob), algo="ChaCha20-Poly1305"),
            _step("Disimpan sebagai attach.enc", "text",
                  "Dokumen tidak disisipkan ke gambar atau audio. Ia disimpan sebagai file terenkripsi di dalam paket lagu.\n"
                  "Jika dibuka dengan Notepad, isinya hanya karakter acak.")],
            flow=["Dokumen", "ChaCha20-Poly1305", "attach.enc (acak)"])

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
    """Daftar semua lagu untuk pemutar (judul dan artis saja), dibaca tanpa dongle."""
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


def owner_of(rid: str) -> str:
    """Pemilik lagu: 'm:<username>' (akun pemutar), 'k:<username>' (akun mode kripto), atau 'legacy'
    untuk lagu lama/impor tanpa pemilik."""
    o = blockchain.owner_of(rid)
    if o in (None, "publik"):
        return "legacy"
    if o.startswith(("m:", "k:")):
        return o
    return "k:" + o  # data lama: pemilik = akun mode kripto


def can_manage(rid: str, who: str) -> bool:
    """Hanya pemilik yang boleh mengedit/menghapus. who = 'm:<username>' atau 'k:<username>'.
    Lagu tanpa pemilik (lama/impor) bisa dikelola oleh akun mode kripto mana pun."""
    o = owner_of(rid)
    return o == who or (o == "legacy" and who.startswith("k:"))


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
    (_dir(rid) / "meta.json").write_text(json.dumps(meta))
    if lyrics is not None:
        old = read_lyrics(rid)
        hidden = "".join(c for c in old if c in HIDDEN)  # muatan tersembunyi ikut dipindah ke lirik baru
        new = "".join(c for c in lyrics if c not in HIDDEN) + hidden
        if new != old:
            raw = new.encode("utf-8")
            (_dir(rid) / "lyrics.txt").write_bytes(raw)
            blockchain.add_block({"release": rid, "owner": who, "action": "update",
                                  "files": {"lyrics": keys.sha256_hex(raw)}})
    if db_key is not None and db.has_track(rid):
        db.put_track(db_key, who, rid, {k: meta[k] for k in ("id", "title", "artist", "salt")})


def delete_song(rid: str, who: str):
    """Hapus lagu permanen. Riwayatnya tetap ada di blockchain (rantai hanya bisa ditambah)."""
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
    skip = _step("Hasil", "text", "Kunci bagian ini belum diisi, jadi bagian ini dilewati dan tetap terkunci.")

    # --- cover ---
    if not pw("cover"):
        out["skipped"].append("cover"); _t(tr, "cover", [skip])
    else:
        probe = {}
        try:
            ek, vk = _text_keys(root("cover"), "cover")
            ct = extract_image(pub["cover"], keys.slot_key(root("cover"), "cover-pos"), probe)
            vig, text = decrypt_text_steps(ct, ek, vk)
            out["cover"] = text
            _t(tr, "cover", [
                _step("Mengambil bit dari bit paling kanan piksel", "table", _img_rows(probe["rows"], probe["width"], read=True), algo="LSB",
                      note="Lokasi acak dihitung ulang dari kunci posisi. 32 bit pertama = panjang pesan, sisanya isi. "
                           "Tabel menampilkan 10 bit pertama.")]
                + _text_dec_steps(ct, vig, vk, text),
                flow=["Hitung lokasi dari kunci", "Baca bit", "Ciphertext", "AES-256-GCM", "Vigenère", "Teks asli"])
        except FAIL as e:
            _t(tr, "cover", [_fail(e)])

    # --- audio ---
    if not pw("audio"):
        out["skipped"].append("audio"); _t(tr, "audio", [skip])
    else:
        probe = {}
        try:
            blob = extract_audio(pub["audio"], keys.slot_key(root("audio"), "audio-pos"), probe)
            out["audio"] = decrypt_bytes(blob, keys.slot_key(root("audio"), "audio-enc"))
            _t(tr, "audio", [
                _step("Mengambil bit dari bit paling kanan sampel lagu", "table", _smp_rows(probe["rows"], read=True), algo="LSB",
                      note="Lokasi dihitung dari kunci posisi. Tabel menampilkan 10 bit pertama (bagian header panjang)."),
                _step("Bit digabung menjadi ciphertext", "parts", _parts(blob), note=f"{len(blob):,} byte."),
                _step("Dekripsi ChaCha20-Poly1305", "text",
                      f"Tag cocok, jadi kunci benar dan data tidak diubah.\nPesan suara asli kembali: file WAV {len(out['audio']):,} byte (bisa diputar).",
                      algo="ChaCha20-Poly1305")],
                flow=["Hitung lokasi dari kunci", "Baca bit", "Ciphertext", "ChaCha20-Poly1305", "File suara"])
        except FAIL as e:
            _t(tr, "audio", [_fail(e)])

    # --- lirik ---
    if not pw("lyrics"):
        out["skipped"].append("lyrics"); _t(tr, "lyrics", [skip])
    else:
        try:
            ek, vk = _text_keys(root("lyrics"), "lyrics")
            hidden = "".join(c for c in pub["lyrics"] if c in (ZERO, ONE))
            ct = extract_text(pub["lyrics"])
            vig, text = decrypt_text_steps(ct, ek, vk)
            out["lyrics"] = text
            sym = hidden.replace(ZERO, "0").replace(ONE, "1")
            _t(tr, "lyrics", [
                _step("Mengumpulkan karakter tak terlihat di lirik", "text",
                      f"Ditemukan {len(hidden):,} karakter tak terlihat.\nJika dibuat tampak (0/1): {sym[:64]}…",
                      algo="Zero-width", note="Karakter tak terlihat diubah kembali menjadi bit (U+200B = 0, U+200C = 1).")]
                + _text_dec_steps(ct, vig, vk, text),
                flow=["Kumpulkan karakter tak terlihat", "Ciphertext", "AES-256-GCM", "Vigenère", "Teks asli"])
        except FAIL as e:
            _t(tr, "lyrics", [_fail(e)])

    # --- dokumen pendukung ---
    if pub["attach"]:
        if not pw("attach"):
            out["skipped"].append("attach"); _t(tr, "attach", [skip])
        else:
            try:
                raw = decrypt_bytes(pub["attach"], keys.slot_key(root("attach"), "attach-enc"))
                n = int.from_bytes(raw[:2], "big")
                out["attach"] = (raw[2:2 + n].decode("utf-8"), raw[2 + n:])
                _t(tr, "attach", [
                    _step("Isi attach.enc (ciphertext)", "parts", _parts(pub["attach"])),
                    _step("Dekripsi ChaCha20-Poly1305", "text",
                          f"Tag cocok. File asli kembali: {out['attach'][0]} ({len(out['attach'][1]):,} byte)",
                          algo="ChaCha20-Poly1305")],
                    flow=["attach.enc (acak)", "ChaCha20-Poly1305", "Dokumen asli"])
            except FAIL as e:
                _t(tr, "attach", [_fail(e)])
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