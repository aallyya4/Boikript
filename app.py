"""BoiKript: pemutar musik biasa dengan mode kripto tersembunyi.
Masuk mode kripto: ketik frasa rahasia di kotak cari + Enter, lalu colok dongle.
Jalankan: streamlit run app.py"""
import hashlib
import hmac
import html
import io
import os
import secrets
import time
import wave

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core import auth, blockchain, db, fingerprint, keys, release
from core.audio_convert import to_wav16
from core.stego_audio import audio_capacity
from core.stego_image import image_capacity

APP_TITLE = "🎵 BoiKript"
# Hash frasa rahasia (bawaan: "sonic vault"). Ganti dengan: python make_secret.py
SECRET_HASH = os.environ.get("SONICVAULT_SECRET_HASH", "7be2da100494715da8af7b461c7aacbc7a184a093cfd3a3c1f02c23eaaceba1f")

st.set_page_config(page_title="BoiKript", page_icon="🎵", layout="wide", initial_sidebar_state="expanded")
db.init()
blockchain.ensure_genesis()

ss = st.session_state
for _k, _v in {"crypto": False, "user": None, "opened": None, "last": None,
               "pub_n": 0, "pub_msg": None, "now": None,
               "view": "home", "member": None, "confirm_del": None, "flash": None, "zip_rid": None, "fp_ok": None, "doc_ver": {}, "last_trace": None, "reg_fp": None, "fp_err": None, "wa_reg": None, "wa_auth": None}.items():
    ss.setdefault(_k, _v)


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;600;800&display=swap');
html, body, .stApp, button, input, textarea { font-family: 'Figtree', system-ui, sans-serif !important; }
footer, #MainMenu, [data-testid="stDecoration"], [data-testid="stAppDeployButton"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2rem; padding-bottom: 7.5rem; max-width: 1400px; }
[data-testid="stSidebar"] { background: #000; border-right: none; }

.sp-brand { font-size: 1.35rem; font-weight: 800; letter-spacing: -.02em; margin: 4px 0 18px; }
.sp-h1 { font-size: 2rem; font-weight: 800; letter-spacing: -.02em; margin: 22px 0 4px; }
.sp-h2 { font-size: 1.4rem; font-weight: 800; letter-spacing: -.01em; margin: 30px 0 12px; }
.sp-kicker { font-size: .8rem; font-weight: 600; }
.sp-hero-title { font-size: clamp(2rem, 5vw, 4.5rem); font-weight: 800; line-height: 1.05; letter-spacing: -.03em; margin: 6px 0; }
.sp-hero-artist { font-size: 1rem; font-weight: 600; color: #e5e5e5; }
.sp-title { font-weight: 700; font-size: 1rem; margin-top: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sp-artist { color: #b3b3b3; font-size: .875rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 6px; }
.sp-lyrics { font-size: 1.3rem; font-weight: 800; line-height: 1.7; padding: 28px 32px; border-radius: 12px; margin-top: 16px; }

.st-key-search [data-baseweb="input"], .st-key-search [data-baseweb="base-input"] {
  background: #242424 !important; border-radius: 500px !important; border: 2px solid transparent !important; }
.st-key-search [data-baseweb="input"]:focus-within { border-color: #fff !important; }
.st-key-search input { padding: 12px 18px !important; }

[class*="st-key-card_"] { background: #181818; border-radius: 8px; padding: 14px; transition: background .25s; }
[class*="st-key-card_"]:hover { background: #282828; }
[class*="st-key-card_"] img { border-radius: 6px; aspect-ratio: 1 / 1; object-fit: cover; width: 100%; box-shadow: 0 8px 24px rgba(0,0,0,.5); }
[class*="st-key-card_"] button { width: 100%; }

[data-testid="stBaseButton-primary"], button[kind="primary"] {
  background: #1db954 !important; color: #000 !important; font-weight: 700 !important; border: none !important; border-radius: 500px !important; }
[data-testid="stBaseButton-primary"]:hover, button[kind="primary"]:hover { background: #1ed760 !important; transform: scale(1.03); }

.st-key-hero { border-radius: 10px; padding: 24px; margin-top: 8px; }
.st-key-hero img { border-radius: 6px; box-shadow: 0 8px 32px rgba(0,0,0,.55); }

.st-key-np_bar { position: fixed; bottom: 0; left: 0; right: 0; z-index: 1000; background: #181818;
  border-top: 1px solid #282828; padding: 10px 24px; }
.stApp:has([data-testid="stSidebar"][aria-expanded="true"]) .st-key-np_bar { left: 21rem; }
.st-key-np_bar img { border-radius: 4px; }
.st-key-np_bar audio { width: 100%; }

.sp-num { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; border-radius:50%;
  background:#1db954; color:#000; font-weight:800; font-size:.8rem; margin-right:10px; }
.sp-chip { display:inline-block; padding:2px 10px; border-radius:500px; border:1px solid #1db954; color:#1db954;
  font-size:.72rem; font-weight:700; margin-left:8px; }
.sp-chip.ok { background:rgba(29,185,84,.15); }
.sp-chip2 { display:inline-block; padding:3px 12px; border-radius:500px; background:#2a2a2a; color:#e5e5e5;
  font-size:.75rem; font-weight:600; margin:2px 0; }
.sp-arrow { color:#1db954; margin:0 6px; font-weight:800; }
.sp-muted { color:#b3b3b3; font-size:.85rem; margin-left:8px; }
.sp-slot { margin-bottom:6px; }
.sp-slot-i { font-size:1.3rem; margin-right:8px; }
.sp-msg { font-size:1.15rem; font-weight:700; padding:8px 0 2px; }
.sp-user { font-weight:700; margin:2px 0 8px; }
.sp-gate-brand { font-size:2.6rem; font-weight:800; letter-spacing:-.03em; text-align:center; margin-top:8vh; }
.sp-gate-sub { color:#b3b3b3; text-align:center; margin:6px 0 22px; }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 10px; }
</style>
"""


AUDIO_TYPES = ["wav", "mp3", "flac", "ogg"]


@st.cache_data(show_spinner="Mengubah ke WAV 16-bit…")
def wav_from_upload(raw: bytes) -> bytes:
    return to_wav16(raw)


def esc(text: str) -> str:
    return html.escape(str(text), quote=True).replace("\r", "").replace("\n", "<br>")


@st.cache_data(show_spinner=False)
def thumb(rid: str, size: int) -> bytes:
    return release.cover_thumb(rid, size)


@st.cache_data(show_spinner=False)
def accent(rid: str):
    return release.cover_color(rid)


def is_secret(text: str) -> bool:
    norm = " ".join(text.lower().split())
    return hmac.compare_digest(hashlib.sha256(norm.encode()).hexdigest(), SECRET_HASH)


def on_search():
    if is_secret(ss.search):
        ss.crypto = True
        ss.search = ""  # kotak cari kembali kosong, tidak meninggalkan jejak
    elif ss.search.strip():
        ss.view = "home"  # mencari lagu selalu menampilkan hasil di beranda


def fmt_time(ts: float) -> str:
    return time.strftime("%d %b %Y %H:%M", time.localtime(ts))


def render_step(n: int, stp: dict, show_keys: bool):
    with st.container(border=True):
        chip = f'<span class="sp-chip">{esc(stp["algo"])}</span>' if stp.get("algo") else ""
        st.markdown(f'<span class="sp-num">{n}</span><b>{esc(stp["title"])}</b>{chip}', unsafe_allow_html=True)
        if stp.get("note"):
            st.caption(stp["note"])
        kind, v = stp["kind"], stp["value"]
        if kind in ("text", "hex"):
            st.code(v, language=None, wrap_lines=True)
        elif kind == "parts":
            for label, hx in v:
                st.caption(label)
                st.code(hx, language=None, wrap_lines=True)
        elif kind == "table":
            secret = set(v.get("secret", []))
            data = {c: [("••" if (j in secret and not show_keys) else str(r[j])) for r in v["rows"]]
                    for j, c in enumerate(v["cols"])}
            st.dataframe(pd.DataFrame(data), hide_index=True)
        elif kind == "images":
            for col, (cap, img) in zip(st.columns(len(v)), v):
                col.image(img, caption=cap)


def show_trace(trace: list, title: str, kid: str):
    """Tampilkan tiap tahap enkripsi/dekripsi: dari teks asli, ciphertext acak, sampai yang tersembunyi di file."""
    if not trace:
        return
    with st.expander(title, expanded=True):
        show_keys = st.toggle("Tampilkan nilai kunci Vigenère di tabel (untuk belajar)", key=f"sk_{kid}")
        for tab, sec in zip(st.tabs([t["label"] for t in trace]), trace):
            with tab:
                if sec.get("flow"):
                    st.markdown(' <span class="sp-arrow">→</span> '.join(f'<span class="sp-chip2">{esc(x)}</span>' for x in sec["flow"]),
                                unsafe_allow_html=True)
                for n, stp in enumerate(sec["steps"], 1):
                    render_step(n, stp, show_keys)


def lock():
    ss.user = ss.opened = ss.last = ss.last_trace = ss.fp_ok = None


# ====================== Mode biasa: pemutar musik (tanpa dongle) ======================
def greeting() -> str:
    h = time.localtime().tm_hour
    return "Selamat pagi" if h < 11 else "Selamat siang" if h < 15 else "Selamat sore" if h < 18 else "Selamat malam"


def show_flash():
    if ss.flash:
        st.success(ss.flash)
        ss.flash = None


def manage_panel(rid: str, who: str, dbk=None):
    """Edit judul/artis/lirik dan hapus lagu. Dipakai di pemutar (who='m:<username>') dan tab Kelola (who='k:<username>')."""
    meta = release.read_meta(rid)
    t = st.text_input("Judul", value=meta["title"], key=f"ed_t_{rid}")
    a = st.text_input("Artis", value=meta["artist"], key=f"ed_a_{rid}")
    lyr = st.text_area("Lirik", value=release.visible_lyrics(rid), height=180, key=f"ed_l_{rid}")
    cur = release.read_doc(rid)
    ver = ss.doc_ver.get(rid, 0)
    st.caption("Dokumen lagu: " + (f"{cur[0]} ({len(cur[1]):,} byte)" if cur else "belum ada"))
    newdoc = st.file_uploader("Tambah atau ganti dokumen lagu", key=f"ed_d_{rid}_{ver}")
    if cur and st.button("Hapus dokumen lagu", key=f"rmdoc_{rid}"):
        release.remove_doc(rid, who)
        ss.flash = "Dokumen lagu dihapus."
        st.rerun()
    if st.button("Simpan perubahan", key=f"ed_s_{rid}", type="primary"):
        try:
            release.update_song(rid, who, dbk, title=t, artist=a, lyrics=lyr)
            if newdoc is not None:
                release.set_doc(rid, who, newdoc.name, newdoc.getvalue())
                ss.doc_ver[rid] = ver + 1
            ss.flash = "Perubahan disimpan."
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    st.divider()
    label = "Lagu ini akan dihapus permanen. Lanjutkan?"
    if ss.confirm_del == rid:
        st.warning(label)
        c1, c2 = st.columns(2)
        if c1.button("Ya, hapus", key=f"del_y_{rid}", type="primary"):
            try:
                release.delete_song(rid, who)
                if ss.now == rid:
                    ss.now, ss.view = None, "home"
                ss.confirm_del, ss.flash = None, "Lagu dihapus."
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        if c2.button("Batal", key=f"del_n_{rid}"):
            ss.confirm_del = None
            st.rerun()
    elif st.button("🗑 Hapus lagu", key=f"del_{rid}"):
        ss.confirm_del = rid
        st.rerun()


def go(view: str, rid=None):
    ss.view = view
    if rid:
        ss.now = rid
    st.rerun()


def hero(t: dict):
    r, g, b = accent(t["id"])
    st.markdown(f"<style>.st-key-hero{{background:linear-gradient(180deg,rgba({r},{g},{b},.8) 0%,#121212 100%);}}</style>",
                unsafe_allow_html=True)
    with st.container(key="hero"):
        c1, c2 = st.columns([1, 3], vertical_alignment="bottom")
        c1.image(thumb(t["id"], 400))
        c2.markdown(f'<div class="sp-kicker">Sedang diputar</div><div class="sp-hero-title">{esc(t["title"])}</div>'
                    f'<div class="sp-hero-artist">{esc(t["artist"])}</div>', unsafe_allow_html=True)
    lyrics = release.read_lyrics(t["id"]).strip()
    if lyrics:
        st.markdown(f'<div class="sp-lyrics" style="background:rgb({r},{g},{b})">{esc(lyrics)}</div>',
                    unsafe_allow_html=True)


def now_bar(t: dict):
    """Bar pemutar. Harus dibuat di posisi yang sama pada semua tampilan supaya lagu tidak terputus."""
    with st.container(key="np_bar"):
        c1, c2, c3 = st.columns([0.7, 2.6, 5], vertical_alignment="center")
        c1.image(thumb(t["id"], 120), width=56)
        c2.markdown(f'<div class="sp-title" style="margin-top:0">{esc(t["title"])}</div>'
                    f'<div class="sp-artist" style="margin-bottom:0">{esc(t["artist"])}</div>', unsafe_allow_html=True)
        c3.audio(release.read_audio(t["id"]), format="audio/wav", autoplay=True)


def home_view(all_tracks: dict):
    q = ss.search.strip().lower()
    tracks = [t for t in all_tracks.values() if q in f'{t["title"]} {t["artist"]}'.lower()]
    st.markdown(f'<div class="sp-h1">{greeting()}</div>', unsafe_allow_html=True)
    st.markdown('<div class="sp-h2">Lagu kamu</div>', unsafe_allow_html=True)
    if not tracks:
        st.info("Lagu tidak ditemukan." if q else "Belum ada lagu. Tambahkan lewat menu di samping.")
    per_row = 5
    for i in range(0, len(tracks), per_row):
        for col, t in zip(st.columns(per_row), tracks[i:i + per_row]):
            with col, st.container(key=f"card_{t['id']}"):
                st.image(thumb(t["id"], 300))
                st.markdown(f'<div class="sp-title">{esc(t["title"])}</div><div class="sp-artist">{esc(t["artist"])}</div>',
                            unsafe_allow_html=True)
                playing = ss.now == t["id"]
                if st.button("♪ Diputar" if playing else "▶ Putar", key=f"play_{t['id']}", type="primary"):
                    go("song", t["id"])


def song_view(now: dict):
    if st.button("← Beranda", key="back_home"):
        go("home")  # lagu tetap terputar: bar pemutar tidak ikut diganti
    hero(now)
    doc = release.read_doc(now["id"])
    if doc:
        st.markdown('<div class="sp-h2">📄 Dokumen lagu</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.caption(f"{doc[0]} · {len(doc[1]):,} byte")
            show_attachment(doc[0], doc[1], key=f"dl_doc_{now['id']}")
    if ss.member and release.can_manage(now["id"], f"m:{ss.member}"):
        with st.expander("⚙️ Edit / hapus lagu"):
            manage_panel(now["id"], f"m:{ss.member}")


def player_mode():
    all_tracks = {t["id"]: t for t in release.list_public()}
    now = all_tracks.get(ss.now)
    if now:
        now_bar(now)  # selalu elemen pertama setelah CSS, jadi tidak di-remount saat pindah tampilan
    st.text_input("Cari", key="search", on_change=on_search, placeholder="Mau dengerin apa?",
                  label_visibility="collapsed")
    show_flash()
    if now and ss.view == "song":
        song_view(now)
    else:
        home_view(all_tracks)


def gate_ui():
    """Halaman awal: wajib masuk dengan akun sebelum memakai aplikasi."""
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.markdown(f'<div class="sp-gate-brand">{APP_TITLE}</div>'
                    '<div class="sp-gate-sub">Dengarkan musikmu dan bagikan dengan aman. Masuk untuk melanjutkan.</div>',
                    unsafe_allow_html=True)
        with st.container(border=True, key="gate_card"):
            mode = st.radio("Mode", ["Masuk", "Daftar"], horizontal=True, key="g_mode", label_visibility="collapsed")
            u = st.text_input("Username", key=f"g_u_{mode}").strip()
            p = st.text_input("Password", type="password", key=f"g_p_{mode}")
            p2 = st.text_input("Ulangi password", type="password", key="g_p2") if mode == "Daftar" else None
            if st.button(mode, key="g_go", type="primary"):
                if mode == "Masuk":
                    ok, msg = auth.login_member(u, p)
                    if ok:
                        ss.member = u
                        st.rerun()
                    st.error(msg)
                elif p != p2:
                    st.error("Password dan ulangi password tidak sama.")
                else:
                    ok, msg = auth.register_member(u, p)
                    (st.success if ok else st.error)(msg)


def logout():
    ss.member = None
    ss.crypto, ss.now, ss.view, ss.confirm_del = False, None, "home", None
    lock()


def add_song_ui():
    """Tambah lagu biasa (tanpa dongle). Pesan rahasia hanya bisa dibuat di mode kripto."""
    if ss.pub_msg:
        st.success(ss.pub_msg)
        ss.pub_msg = None
    n = ss.pub_n  # naik tiap sukses supaya form kosong kembali
    with st.expander("➕ Tambah lagu"):
        title = st.text_input("Judul", key=f"pb_t{n}")
        artist = st.text_input("Artis", key=f"pb_a{n}")
        wav = st.file_uploader("File lagu (MP3/WAV/FLAC/OGG)", type=AUDIO_TYPES, key=f"pb_w{n}")
        cov = st.file_uploader("Cover album (PNG/JPG)", type=["png", "jpg", "jpeg"], key=f"pb_c{n}")
        lyr = st.text_area("Lirik", height=120, key=f"pb_l{n}")
        doc = st.file_uploader("Dokumen lagu (opsional): chord, booklet, atau credits", key=f"pb_d{n}")
        if st.button("Tambahkan", key=f"pb_b{n}", type="primary"):
            if not (title.strip() and artist.strip() and wav and cov):
                st.error("Judul, artis, file lagu, dan cover wajib diisi.")
                return
            try:
                release.create_release(None, f"m:{ss.member}", title.strip(), artist.strip(),
                                       wav_from_upload(wav.getvalue()), cov.getvalue(), lyr,
                                       doc=(doc.name, doc.getvalue()) if doc is not None else None)
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
    c1.markdown('<span class="sp-chip ok" style="margin-left:0">🔓 Dongle terdeteksi</span>', unsafe_allow_html=True)
    if ss.user:
        secret_ui(dbk)
    else:
        login_ui(dbk)


# Komponen browser untuk WebAuthn (sidik jari Windows Hello / Touch ID)
_webauthn = components.declare_component(
    "sv_webauthn", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "webauthn"))


def rp_info():
    """rp_id dan origin diambil dari alamat yang dipakai membuka aplikasi (harus 'localhost')."""
    try:
        host = st.context.headers.get("Host") or "localhost:8501"
        proto = st.context.headers.get("X-Forwarded-Proto", "http")
    except Exception:
        host, proto = "localhost:8501", "http"
    return (os.environ.get("SONICVAULT_RP_ID") or host.split(":")[0],
            os.environ.get("SONICVAULT_ORIGIN") or f"{proto}://{host}")


def fp_widget(kind: str, username: str, dbk=None):
    """Tombol sidik jari. kind='reg' untuk mendaftar, 'auth' untuk verifikasi saat login."""
    rp_id, origin = rp_info()
    if ss.fp_err:
        st.error(ss.fp_err)
        ss.fp_err = None
    ch = ss[f"wa_{kind}"]
    if ch is None or ch["user"] != username:  # tantangan baru untuk tiap percobaan/username
        if kind == "reg":
            begin = fingerprint.begin_register(rp_id, username)
        else:
            rec = auth.get_fp_record(dbk, username)
            if rec is None:
                st.info("Akun ini belum mendaftarkan sidik jari.")
                return
            begin = fingerprint.begin_auth(rp_id, rec)
        ch = ss[f"wa_{kind}"] = {**begin, "user": username, "nonce": secrets.token_hex(8)}
    res = _webauthn(mode="create" if kind == "reg" else "get", options=ch["options"], nonce=ch["nonce"],
                    label="🖐 Daftarkan sidik jari" if kind == "reg" else "🖐 Verifikasi sidik jari",
                    key=f"wac_{kind}", default=None)
    if not res or res.get("nonce") != ch["nonce"]:
        return
    if not res.get("ok"):
        st.error(f"Gagal: {res.get('error')}")
        return
    try:
        if kind == "reg":
            ss.reg_fp = {"user": username, **fingerprint.finish_register(res["credential"], ch["challenge"], rp_id, origin)}
        else:
            rec = auth.get_fp_record(dbk, username)
            auth.save_fp_record(dbk, username, fingerprint.finish_auth(res["credential"], ch["challenge"], rp_id, origin, rec))
            ss.fp_ok = username
    except Exception as e:
        ss.fp_err = f"Verifikasi sidik jari ditolak: {e}"
    ss[f"wa_{kind}"] = None
    st.rerun()


def login_ui(dbk):
    mode = st.radio("Mode", ["Masuk", "Daftar"], horizontal=True, label_visibility="collapsed")
    u = st.text_input("Username" if mode == "Masuk" else "Username baru", key=f"u_{mode}").strip()
    p = st.text_input("Password" if mode == "Masuk" else "Password baru (min. 6 karakter)",
                      type="password", key=f"p_{mode}")
    if mode == "Masuk":
        if not u:
            st.caption("Isi username dulu, lalu verifikasi sidik jari.")
        elif ss.fp_ok == u:
            st.success("Sidik jari terverifikasi.")
        else:
            fp_widget("auth", u, dbk)
        if st.button("Masuk", type="primary"):
            ok, msg = auth.login(dbk, u, p, fp_verified=(ss.fp_ok == u))
            if ok:
                ss.user, ss.fp_ok = u, None
                st.rerun()
            st.error(msg)
    else:
        if ss.reg_fp and ss.reg_fp["user"] == u:
            st.success("Sidik jari terdaftar.")
        elif u:
            fp_widget("reg", u)
        else:
            st.caption("Isi username dulu, lalu daftarkan sidik jari.")
        if st.button("Daftar", type="primary"):
            fp = {k: ss.reg_fp[k] for k in ("id", "pk", "count")} if ss.reg_fp and ss.reg_fp["user"] == u else None
            ok, msg = auth.register(dbk, u, p, fp)
            if ok:
                ss.reg_fp = None
                st.success(msg)
            else:
                st.error(msg)


def manage_ui(dbk):
    show_flash()
    who = f"k:{ss.user}"
    songs = [t for t in release.list_public() if release.can_manage(t["id"], who)]
    if not songs:
        st.info("Belum ada lagu yang bisa dikelola. Lagu yang kamu buat di mode kripto muncul di sini.")
    st.caption("Cover dan audio tidak bisa diganti karena akan menghapus pesan yang tertanam di dalamnya. "
               "Untuk mengganti keduanya, hapus lagu lalu buat ulang. Pesan tersembunyi di lirik tetap aman saat lirik diedit.")
    for t in songs:
        with st.expander(f'{t["title"]} — {t["artist"]}'):
            st.caption("Kode berbagi")
            st.code(f"SV-{t['id']}")
            if st.button("📦 Siapkan paket (.zip)", key=f"zp_{t['id']}"):
                ss.zip_rid = t["id"]
            if ss.zip_rid == t["id"]:
                st.download_button("⬇️ Unduh paket (.zip)", release.export_zip(t["id"]),
                                   file_name=f"SV-{t['id']}.zip", key=f"dl_{t['id']}")
            st.divider()
            manage_panel(t["id"], who, dbk)


def secret_ui(dbk):
    st.markdown(f'<span class="sp-chip ok" style="margin-left:0">🔒 Mode kripto aktif</span>'
                f'<span class="sp-muted">akun: {esc(ss.user)}</span>', unsafe_allow_html=True)
    t_make, t_open, t_manage, t_arch, t_chain = st.tabs(["🎼 Buat", "🔓 Buka", "🗂 Kelola", "🗄️ Arsip", "⛓️ Registri"])
    with t_make:
        make_ui(dbk)
    with t_open:
        open_ui(dbk)
    with t_manage:
        manage_ui(dbk)
    with t_arch:
        archive_ui(dbk)
    with t_chain:
        chain_ui()


def slot_head(icon: str, title: str, kind: str, algo: str, hide: str):
    st.markdown(f'<div class="sp-slot"><span class="sp-slot-i">{icon}</span><b>{title}</b>'
                f'<span class="sp-chip">{kind}</span><span class="sp-chip">{algo}</span></div>'
                f'<span class="sp-chip2">{hide}</span>', unsafe_allow_html=True)


def show_attachment(name: str, data: bytes, key: str = "dl_att"):
    """Tampilkan dokumen sesuai jenisnya, plus tombol unduh."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in ("png", "jpg", "jpeg", "gif", "webp"):
        st.image(data, caption=name)
    elif ext in ("txt", "md", "csv", "json", "log"):
        st.code(data.decode("utf-8", "replace")[:3000], language=None, wrap_lines=True)
    st.download_button(f"⬇️ Unduh {name}", data, file_name=name, key=key)


def make_ui(dbk):
    st.caption("Kosongkan semua pesan rahasia untuk menambah lagu biasa.")
    with st.container(border=True):
        st.markdown("**1. Data lagu**")
        c1, c2 = st.columns(2)
        title = c1.text_input("Judul lagu", key="mk_t")
        artist = c2.text_input("Artis", key="mk_a")
        wav = st.file_uploader("Lagu pembawa (MP3/WAV/FLAC/OGG, otomatis diubah ke WAV 16-bit)", type=AUDIO_TYPES, key="mk_wav")
        cov = st.file_uploader("Cover album (PNG/JPG)", type=["png", "jpg", "jpeg"], key="mk_cov")
        lyr = st.text_area("Lirik (publik)", height=140, key="mk_lyr")
        doc = st.file_uploader("Dokumen lagu (opsional, tampil untuk semua pengguna): chord, booklet, atau credits", key="mk_doc")
        try:
            if wav:
                st.caption(f"Kapasitas audio: ±{audio_capacity(wav_from_upload(wav.getvalue())):,} byte")
            if cov:
                st.caption(f"Kapasitas cover: ±{image_capacity(cov.getvalue()):,} byte")
        except Exception as e:
            st.error(f"File tidak bisa dibaca: {e}")

    with st.container(border=True):
        st.markdown("**2. Pesan rahasia** (tiap bagian opsional)")
        st.caption("Tiap bagian punya kunci sendiri. Bagikan kuncinya lewat jalur atau orang yang berbeda, sehingga "
                   "satu kunci yang bocor tidak membuka bagian lain. Boleh mengisi kunci yang sama jika mau.")
        with st.container(border=True):
            slot_head("📍", "Pesan teks → Cover album", "Teks", "Vigenère + AES-256-GCM", "disembunyikan di gambar cover")
            c1, c2 = st.columns([3, 2])
            s_cover = c1.text_input("Isi pesan (mis. lokasi)", key="mk_sc")
            k_cover = c2.text_input("Kunci cover", type="password", key="mk_kc")
        with st.container(border=True):
            slot_head("🎙️", "Pesan suara → Audio lagu", "File", "ChaCha20-Poly1305", "disembunyikan di bunyi lagu")
            c1, c2 = st.columns([3, 2])
            with c1:
                rec = st.audio_input("Rekam pesan suara (mis. kegiatan)", key="mk_rec")
                up = st.file_uploader("…atau unggah pesan suara (WAV/MP3/FLAC/OGG)", type=AUDIO_TYPES, key="mk_voice")
            k_audio = c2.text_input("Kunci audio", type="password", key="mk_ka")
        with st.container(border=True):
            slot_head("🕒", "Pesan teks → Lirik", "Teks", "Vigenère + AES-256-GCM", "disembunyikan di lirik")
            c1, c2 = st.columns([3, 2])
            s_lyr = c1.text_input("Isi pesan (mis. waktu)", key="mk_sl")
            k_lyr = c2.text_input("Kunci lirik", type="password", key="mk_kl")
        with st.container(border=True):
            slot_head("📎", "Dokumen pendukung", "File", "ChaCha20-Poly1305", "disimpan terenkripsi di paket lagu")
            c1, c2 = st.columns([3, 2])
            att = c1.file_uploader("Peta atau denah (PNG/JPG), catatan (TXT), atau PDF", key="mk_att")
            k_att = c2.text_input("Kunci dokumen", type="password", key="mk_kt")

    if st.button("Buat lagu", type="primary"):
        if not (title and artist and wav and cov and lyr):
            st.error("Judul, artis, lagu, cover, dan lirik wajib diisi.")
        else:
            voice = rec if rec is not None else up
            trace = []
            try:
                ss.last = release.create_release(
                    dbk, f"k:{ss.user}", title, artist, wav_from_upload(wav.getvalue()), cov.getvalue(), lyr,
                    slot_keys={"cover": k_cover, "audio": k_audio, "lyrics": k_lyr, "attach": k_att},
                    cover_text=s_cover or None,
                    voice=wav_from_upload(voice.getvalue()) if voice is not None else None,
                    lyrics_text=s_lyr or None,
                    attach=(att.name, att.getvalue()) if att is not None else None, trace=trace,
                    doc=(doc.name, doc.getvalue()) if doc is not None else None)
                ss.last_trace = trace
            except Exception as e:
                ss.last = ss.last_trace = None
                st.error(str(e))
    if ss.last:
        st.success("Lagu dibuat dan hash-nya dicatat di blockchain.")
        st.code(f"SV-{ss.last}")
        st.caption("Kode ini juga bisa dilihat lagi di tab Kelola. Pesan, audio, dan dokumen muncul di tab Buka "
                   "setelah kamu memasukkan kode dan kunci tiap bagian.")
        st.download_button("⬇️ Unduh paket (.zip)", release.export_zip(ss.last), file_name=f"SV-{ss.last}.zip")
        if ss.last_trace:
            show_trace(ss.last_trace, "🔬 Proses enkripsi, tahap demi tahap", "make")


def open_ui(dbk):
    code = st.text_input("Kode berbagi (SV-xxxxxxxx)", key="op_code")
    pkg = st.file_uploader("…atau impor paket (.zip)", type=["zip"], key="op_zip")
    st.caption("Isi kunci yang kamu punya. Bagian yang kuncinya belum diisi tetap terkunci.")
    c1, c2, c3, c4 = st.columns(4)
    sk = {"cover": c1.text_input("Kunci cover", type="password", key="op_kc"),
          "audio": c2.text_input("Kunci audio", type="password", key="op_ka"),
          "lyrics": c3.text_input("Kunci lirik", type="password", key="op_kl"),
          "attach": c4.text_input("Kunci dokumen", type="password", key="op_kt")}
    if st.button("Buka", type="primary"):
        try:
            rid = release.import_zip(dbk, ss.user, pkg.getvalue()) if pkg else code.strip().removeprefix("SV-")
            ss.opened = release.open_release(rid, slot_keys=sk)
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

    slots = [("cover", "📍", "Cover (pesan teks)"), ("audio", "🎙️", "Audio (pesan suara)"), ("lyrics", "🕒", "Lirik (pesan teks)")]
    if pub["attach"]:
        slots.append(("attach", "📎", "Dokumen pendukung"))
    n_open = sum(bool(o[k]) for k, _, _ in slots)
    if n_open:
        st.success(f"{n_open} bagian pesan terbuka. Gabungkan semuanya untuk memahami maksudnya.")
    else:
        st.warning("Belum ada bagian pesan yang terbuka: ini lagu biasa, atau kuncinya belum diisi / salah.")
    for k, icon, name in slots:
        with st.container(border=True):
            if o[k]:
                st.markdown(f'{icon} **{name}** <span class="sp-chip ok">✅ Terbuka</span>', unsafe_allow_html=True)
                if k in ("cover", "lyrics"):
                    st.markdown(f'<div class="sp-msg">{esc(o[k])}</div>', unsafe_allow_html=True)
                elif k == "audio":
                    st.audio(o[k], format="audio/wav")
                else:
                    show_attachment(*o[k])
            else:  # kunci belum diisi dan kunci salah sengaja tidak dibedakan dari "memang kosong"
                why = "kunci belum diisi" if k in o["skipped"] else "kosong atau kunci salah"
                st.markdown(f'{icon} **{name}** <span class="sp-chip">🔒 Terkunci</span><span class="sp-muted">{why}</span>',
                            unsafe_allow_html=True)
    if o["cover"] or o["lyrics"]:
        if st.button("💾 Simpan teks ke arsip"):
            db.put_message(dbk, ss.user, meta["id"], {"title": meta["title"], "cover": o["cover"], "lyrics": o["lyrics"]})
            st.toast("Tersimpan di arsip terenkripsi.")

    if o.get("trace"):
        show_trace(o["trace"], "🔬 Proses dekripsi, tahap demi tahap", "open")

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
        if hit:
            st.success(f"Terdaftar di blok #{hit['block']}. File ini asli dan belum diubah.")
        else:
            st.error("Tidak terdaftar atau sudah berubah. File ini bukan salinan asli dari registri.")


# ====================== Halaman utama ======================
st.markdown(CSS, unsafe_allow_html=True)
if not ss.member:  # wajib login akun di awal, sebelum masuk aplikasi
    gate_ui()
    st.stop()
with st.sidebar:
    st.markdown(f'<div class="sp-brand">{APP_TITLE}</div><div class="sp-user">👤 {esc(ss.member)}</div>', unsafe_allow_html=True)
    if st.button("Keluar", key="m_logout"):
        logout()
        st.rerun()
    if not ss.crypto:
        if st.button("🏠 Beranda", key="nav_home"):
            go("home")
        if ss.now and st.button("♪ Sedang diputar", key="nav_song"):
            go("song")
        add_song_ui()
if ss.crypto:
    crypto_mode()
else:
    player_mode()