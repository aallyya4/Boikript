"""SonicVault: pemutar musik yang menyimpan platform pesan rahasia. Jalankan: streamlit run app.py"""
import time

import streamlit as st

from core import auth, blockchain, db, keys, release
from core.stego_audio import audio_capacity
from core.stego_image import image_capacity

st.set_page_config(page_title="SonicVault", page_icon="🎵", layout="wide")

# ====================== Gerbang 1: dongle ======================
dongle = auth.find_dongle()
if dongle is None:
    st.title("🎵 SonicVault")
    st.error("🔌 Dongle tidak ditemukan. Colok flashdisk dongle, lalu coba lagi.")
    st.button("Coba lagi")
    st.stop()

DB_KEY = keys.slot_key(dongle, "db")  # kunci database diturunkan dari dongle
db.init()
blockchain.ensure_genesis()

ss = st.session_state
ss.setdefault("user", None)
ss.setdefault("opened", None)
ss.setdefault("last", None)
ss.setdefault("reg_faces", [])


def fmt_time(ts: float) -> str:
    return time.strftime("%d %b %Y %H:%M", time.localtime(ts))


# ====================== Pemutar (tampilan luar) ======================
def player_ui():
    tracks = db.list_tracks(DB_KEY)
    if not tracks:
        st.info("Belum ada lagu di perpustakaan.")
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


# ====================== Login / daftar ======================
def login_ui():
    mode = st.radio("Mode", ["Masuk", "Daftar"], horizontal=True, label_visibility="collapsed")
    if mode == "Masuk":
        u = st.text_input("Username", key="li_u")
        p = st.text_input("Password", type="password", key="li_p")
        shot = st.camera_input("Verifikasi wajah", key="li_cam")
        if st.button("Masuk", type="primary"):
            ok, msg = auth.login(DB_KEY, u.strip(), p, shot.getvalue() if shot else None)
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
            ok, msg = auth.register(DB_KEY, u.strip(), p, ss.reg_faces)
            if ok:
                ss.reg_faces = []
                st.success(msg)
            else:
                st.error(msg)


# ====================== Buat lagu / pesan ======================
def make_ui():
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
                    DB_KEY, ss.user, title, artist, wav.getvalue(), cov.getvalue(), lyr,
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


# ====================== Buka pesan ======================
def open_ui():
    code = st.text_input("Kode berbagi (SV-xxxxxxxx)", key="op_code")
    pkg = st.file_uploader("…atau impor paket (.zip)", type=["zip"], key="op_zip")
    key = st.text_input("Kunci pesan", type="password", key="op_key")
    if st.button("Buka", type="primary"):
        try:
            rid = release.import_zip(DB_KEY, ss.user, pkg.getvalue()) if pkg else code.strip().removeprefix("SV-")
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
            db.put_message(DB_KEY, ss.user, meta["id"],
                           {"title": meta["title"], "cover": o["cover"], "lyrics": o["lyrics"]})
            st.toast("Tersimpan di arsip terenkripsi.")

    st.markdown("**Verifikasi integritas (blockchain)**")
    for name, data in (("audio", pub["audio"]), ("cover", pub["cover"]), ("lirik", pub["lyrics"].encode("utf-8"))):
        hit = blockchain.verify_file(data)
        st.write(f"✅ {name}: terdaftar di blok #{hit['block']}" if hit
                 else f"❌ {name}: hash tidak ditemukan (file diubah / bukan dari registri ini)")


# ====================== Arsip & registri ======================
def archive_ui():
    msgs = db.list_messages(DB_KEY, ss.user)
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


def secret_ui():
    c1, c2 = st.columns([5, 1])
    c1.success(f"Mode rahasia aktif: {ss.user}")
    if c2.button("Keluar"):
        ss.user, ss.opened, ss.last = None, None, None
        st.rerun()
    t_make, t_open, t_arch, t_chain = st.tabs(["🎼 Buat", "🔓 Buka", "🗄️ Arsip", "⛓️ Registri"])
    with t_make:
        make_ui()
    with t_open:
        open_ui()
    with t_arch:
        archive_ui()
    with t_chain:
        chain_ui()


# ====================== Halaman utama ======================
st.title("🎵 SonicVault")
tab_play, tab_acc = st.tabs(["🎧 Pemutar", "⚙️ Akun"])
with tab_play:
    player_ui()
with tab_acc:
    secret_ui() if ss.user else login_ui()
