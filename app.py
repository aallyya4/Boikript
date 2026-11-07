"""Sonic Player: pemutar musik biasa dengan mode kripto tersembunyi.
Masuk mode kripto: ketik frasa rahasia di kotak cari + Enter, lalu colok dongle.
Jalankan: streamlit run app.py"""
import hashlib
import hmac
import io
import os
import time
import wave

import streamlit as st

from core import auth, blockchain, db, keys, release
from core.stego_audio import audio_capacity
from core.stego_image import image_capacity

APP_TITLE = "🎵 Sonic Player"
# Hash frasa rahasia (bawaan: "sonic vault"). Ganti dengan: python make_secret.py
SECRET_HASH = os.environ.get("SONICVAULT_SECRET_HASH", "7be2da100494715da8af7b461c7aacbc7a184a093cfd3a3c1f02c23eaaceba1f")

st.set_page_config(page_title="Sonic Player", page_icon="🎵", layout="wide")
db.init()
blockchain.ensure_genesis()

ss = st.session_state
for _k, _v in {"crypto": False, "user": None, "opened": None, "last": None, "reg_faces": [],
               "pub_n": 0, "pub_msg": None}.items():
    ss.setdefault(_k, _v)


def is_secret(text: str) -> bool:
    norm = " ".join(text.lower().split())
    return hmac.compare_digest(hashlib.sha256(norm.encode()).hexdigest(), SECRET_HASH)


def on_search():
    if is_secret(ss.search):
        ss.crypto = True
        ss.search = ""  # kotak cari kembali kosong, tidak meninggalkan jejak


def fmt_time(ts: float) -> str:
    return time.strftime("%d %b %Y %H:%M", time.localtime(ts))


def lock():
    ss.user = ss.opened = ss.last = None


# ====================== Mode biasa: pemutar musik (tanpa dongle) ======================
def player_mode():
    st.text_input("🔍 Cari lagu", key="search", on_change=on_search, placeholder="Cari judul atau artis…")
    q = ss.search.strip().lower()
    tracks = [t for t in release.list_public() if q in f'{t["title"]} {t["artist"]}'.lower()]
    if not tracks:
        st.info("Lagu tidak ditemukan." if q else "Belum ada lagu di perpustakaan.")
        return
    labels = {f'{t["title"]} — {t["artist"]} ({t["id"][:4]})': t["id"] for t in tracks}
    pick = st.selectbox("Pilih lagu", list(labels))
    pub = release.read_public(labels[pick])
    c1, c2 = st.columns([1, 2])
    c1.image(pub["cover"], width=320)
    with c2:
        st.subheader(pick)
        st.audio(pub["audio"], format="audio/wav")
        st.text(pub["lyrics"])


def add_song_ui():
    """Tambah lagu biasa (tanpa dongle). Pesan rahasia hanya bisa dibuat di mode kripto."""
    if ss.pub_msg:
        st.success(ss.pub_msg)
        ss.pub_msg = None
    n = ss.pub_n  # naik tiap sukses supaya form kosong kembali
    with st.expander("➕ Tambah lagu"):
        c1, c2 = st.columns(2)
        title = c1.text_input("Judul", key=f"pb_t{n}")
        artist = c2.text_input("Artis", key=f"pb_a{n}")
        wav = st.file_uploader("File lagu (WAV)", type=["wav"], key=f"pb_w{n}")
        cov = st.file_uploader("Cover album (PNG/JPG)", type=["png", "jpg", "jpeg"], key=f"pb_c{n}")
        lyr = st.text_area("Lirik", height=120, key=f"pb_l{n}")
        if st.button("Tambahkan", key=f"pb_b{n}", type="primary"):
            if not (title.strip() and artist.strip() and wav and cov):
                st.error("Judul, artis, file lagu, dan cover wajib diisi.")
                return
            try:
                wave.open(io.BytesIO(wav.getvalue())).close()  # pastikan WAV valid
                release.create_release(None, "publik", title.strip(), artist.strip(),
                                       wav.getvalue(), cov.getvalue(), lyr)
            except Exception as e:
                st.error(f"Gagal menambahkan lagu: {e}")
                return
            ss.pub_n += 1
            ss.pub_msg = f"Lagu \"{title.strip()}\" ditambahkan."
            st.rerun()


# ====================== Mode kripto (wajib dongle) ======================
def crypto_mode():
    c1, c2 = st.columns([5, 1])
    if c2.button("⏻ Tutup"):
        ss.crypto = False
        lock()
        st.rerun()
    dongle = auth.find_dongle()  # dicek ulang tiap interaksi: dongle dicabut = terkunci
    if dongle is None:
        lock()
        st.warning("🔌 Colok dongle untuk melanjutkan.")
        st.button("Coba lagi")
        return
    dbk = keys.slot_key(dongle, "db")  # kunci database diturunkan dari dongle
    c1.caption("🔓 Dongle terdeteksi")
    secret_ui(dbk) if ss.user else login_ui(dbk)


def login_ui(dbk):
    mode = st.radio("Mode", ["Masuk", "Daftar"], horizontal=True, label_visibility="collapsed")
    if mode == "Masuk":
        u = st.text_input("Username", key="li_u")
        p = st.text_input("Password", type="password", key="li_p")
        shot = st.camera_input("Verifikasi wajah", key="li_cam")
        if st.button("Masuk", type="primary"):
            ok, msg = auth.login(dbk, u.strip(), p, shot.getvalue() if shot else None)
            if ok:
                ss.user = u.strip()
                st.rerun()
            st.error(msg)
    else:
        u = st.text_input("Username baru", key="rg_u")
        p = st.text_input("Password baru (min. 6 karakter)", type="password", key="rg_p")
        shot = st.camera_input("Foto wajah (ambil 3 kali dengan sedikit variasi posisi)", key="rg_cam")
        if st.button("➕ Simpan foto ini") and shot:
            ss.reg_faces.append(shot.getvalue())
        st.caption(f"Foto tersimpan: {len(ss.reg_faces)}/3")
        if st.button("Daftar", type="primary"):
            ok, msg = auth.register(dbk, u.strip(), p, ss.reg_faces)
            if ok:
                ss.reg_faces = []
                st.success(msg)
            else:
                st.error(msg)


def secret_ui(dbk):
    st.success(f"Mode kripto aktif: {ss.user}")
    t_make, t_open, t_arch, t_chain = st.tabs(["🎼 Buat", "🔓 Buka", "🗄️ Arsip", "⛓️ Registri"])
    with t_make:
        make_ui(dbk)
    with t_open:
        open_ui(dbk)
    with t_arch:
        archive_ui(dbk)
    with t_chain:
        chain_ui()


def make_ui(dbk):
    st.caption("Kosongkan semua pesan rahasia untuk menambah lagu biasa.")
    c1, c2 = st.columns(2)
    title = c1.text_input("Judul lagu", key="mk_t")
    artist = c2.text_input("Artis", key="mk_a")
    wav = st.file_uploader("Lagu pembawa (WAV 16-bit)", type=["wav"], key="mk_wav")
    cov = st.file_uploader("Cover album (PNG/JPG)", type=["png", "jpg", "jpeg"], key="mk_cov")
    lyr = st.text_area("Lirik (publik)", height=140, key="mk_lyr")
    try:
        if wav:
            st.caption(f"Kapasitas audio: ±{audio_capacity(wav.getvalue()):,} byte")
        if cov:
            st.caption(f"Kapasitas cover: ±{image_capacity(cov.getvalue()):,} byte")
    except Exception as e:
        st.error(f"File tidak bisa dibaca: {e}")

    st.markdown("**Pesan rahasia** (tiap bagian opsional)")
    key = st.text_input("Kunci pesan (bagikan terpisah ke penerima)", type="password", key="mk_key")
    s_cover = st.text_input("📍 Cover: teks pendek (mis. lokasi)", key="mk_sc")
    rec = st.audio_input("🎙️ Audio: rekam pesan suara", key="mk_rec")
    up = st.file_uploader("…atau unggah pesan suara (WAV)", type=["wav"], key="mk_voice")
    s_lyr = st.text_input("🕒 Lirik: teks pendek (mis. waktu)", key="mk_sl")
    att = st.file_uploader("📎 Lampiran (file apa pun)", key="mk_att")

    if st.button("Buat lagu", type="primary"):
        if not (title and artist and wav and cov and lyr):
            st.error("Judul, artis, lagu, cover, dan lirik wajib diisi.")
        else:
            voice = rec if rec is not None else up
            try:
                ss.last = release.create_release(
                    dbk, ss.user, title, artist, wav.getvalue(), cov.getvalue(), lyr,
                    password=key or None, cover_text=s_cover or None,
                    voice=voice.getvalue() if voice is not None else None,
                    lyrics_text=s_lyr or None,
                    attach=(att.name, att.getvalue()) if att is not None else None)
            except Exception as e:
                ss.last = None
                st.error(str(e))
    if ss.last:
        st.success("Lagu dibuat dan hash-nya dicatat di blockchain.")
        st.code(f"SV-{ss.last}")
        st.download_button("⬇️ Unduh paket (.zip)", release.export_zip(ss.last), file_name=f"SV-{ss.last}.zip")


def open_ui(dbk):
    code = st.text_input("Kode berbagi (SV-xxxxxxxx)", key="op_code")
    pkg = st.file_uploader("…atau impor paket (.zip)", type=["zip"], key="op_zip")
    key = st.text_input("Kunci pesan", type="password", key="op_key")
    if st.button("Buka", type="primary"):
        try:
            rid = release.import_zip(dbk, ss.user, pkg.getvalue()) if pkg else code.strip().removeprefix("SV-")
            ss.opened = release.open_release(rid, key)
        except Exception as e:
            ss.opened = None
            st.error(f"Gagal membuka: {e}")

    o = ss.opened
    if not o:
        return
    meta, pub = o["meta"], o["pub"]
    c1, c2 = st.columns([1, 2])
    c1.image(pub["cover"], width=260)
    with c2:
        st.subheader(f'{meta["title"]} — {meta["artist"]}')
        st.audio(pub["audio"], format="audio/wav")

    found = [k for k in ("cover", "audio", "lyrics", "attach") if o[k]]
    if not found:
        st.warning("Tidak ada pesan yang terbuka: ini lagu biasa, atau kuncinya salah.")
    else:
        st.success(f"{len(found)} bagian pesan terbuka. Gabungkan semuanya untuk memahami maksudnya.")
        if o["cover"]:
            st.info(f"📍 **Cover:** {o['cover']}")
        if o["lyrics"]:
            st.info(f"🕒 **Lirik:** {o['lyrics']}")
        if o["audio"]:
            st.markdown("🎙️ **Audio:**")
            st.audio(o["audio"], format="audio/wav")
        if o["attach"]:
            name, data = o["attach"]
            st.download_button(f"📎 {name}", data, file_name=name)
        if st.button("💾 Simpan teks ke arsip"):
            db.put_message(dbk, ss.user, meta["id"],
                           {"title": meta["title"], "cover": o["cover"], "lyrics": o["lyrics"]})
            st.toast("Tersimpan di arsip terenkripsi.")

    st.markdown("**Verifikasi integritas (blockchain)**")
    for name, data in (("audio", pub["audio"]), ("cover", pub["cover"]), ("lirik", pub["lyrics"].encode("utf-8"))):
        hit = blockchain.verify_file(data)
        st.write(f"✅ {name}: terdaftar di blok #{hit['block']}" if hit
                 else f"❌ {name}: hash tidak ditemukan (file diubah / bukan dari registri ini)")


def archive_ui(dbk):
    msgs = db.list_messages(dbk, ss.user)
    if not msgs:
        st.info("Arsip kosong.")
    for m in msgs:
        p = m["payload"]
        with st.expander(f'{p["title"]}, disimpan {fmt_time(m["created"])}'):
            if p.get("cover"):
                st.write("📍", p["cover"])
            if p.get("lyrics"):
                st.write("🕒", p["lyrics"])


def chain_ui():
    ok, msg = blockchain.validate()
    (st.success if ok else st.error)(msg)
    rows = db.chain_rows()
    st.dataframe([{"#": r["idx"], "waktu": fmt_time(r["ts"]), "hash": r["hash"][:16] + "…",
                   "prev": r["prev_hash"][:16] + "…", "data": r["data"][:70]} for r in reversed(rows)])
    f = st.file_uploader("Cek file terhadap registri", key="ch_file")
    if f:
        hit = blockchain.verify_file(f.getvalue())
        st.success(f"Terdaftar di blok #{hit['block']}.") if hit else st.error("Tidak terdaftar / sudah berubah.")


# ====================== Halaman utama ======================
st.title(APP_TITLE)
if ss.crypto:
    crypto_mode()
else:
    player_mode()
    add_song_ui()