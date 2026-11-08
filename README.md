# SonicVault (tampil sebagai "Sonic Player")

Pemutar musik biasa yang menyimpan platform pesan rahasia. Orang yang membuka aplikasi hanya melihat pemutar musik; **mode kripto tersembunyi** dan baru terbuka lewat frasa rahasia + dongle. Pesan dipecah ke **cover (lokasi)**, **audio (kegiatan)**, **lirik (waktu)**, dan **lampiran** (opsional). Tiap bagian boleh kosong, dan penerima harus membuka semuanya untuk paham maksudnya.

## Tampilan

Tampilan meniru aplikasi musik: tema gelap dengan aksen hijau, kartu lagu berisi cover, header gradasi dari warna cover, lirik besar, dan bar pemutar di bawah.
Temanya diatur di `.streamlit/config.toml` (folder ini harus ikut dipindah ke proyekmu, sejajar `app.py`).
CSS tambahan ada di konstanta `CSS` di `app.py`.

## Sidik jari (Windows Hello)

Biometrik memakai **sidik jari yang sudah tersimpan di laptop** (Windows Hello / Touch ID) lewat WebAuthn.
- Siapkan dulu sidik jari di Windows: Settings → Accounts → Sign-in options → Fingerprint recognition.
- **Buka aplikasi lewat `http://localhost:8501`** (bukan 127.0.0.1 atau IP jaringan), karena WebAuthn butuh domain `localhost`.
- Gunakan Chrome atau Edge terbaru.
- Daftar: isi username → klik **🖐 Daftarkan sidik jari** → sentuh sensor. Login: pilih **Sidik jari** → **🖐 Verifikasi sidik jari** → sentuh sensor → **Masuk**.
- Login = password + sidik jari (keduanya wajib). Template sidik jari tidak pernah keluar dari laptop; server hanya menyimpan kunci publik (terenkripsi dengan kunci dongle).
- Windows bisa menawarkan PIN sebagai pengganti sidik jari. Itu aturan Windows Hello, aplikasi tidak bisa memaksa sensor saja.
- Kode: `core/fingerprint.py` (verifikasi di server), `components/webauthn/index.html` (sisi browser), `fp_widget` di `app.py`.

## Instalasi

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |  Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
python make_demo_assets.py          # membuat demo/lagu_demo.wav dan demo/cover_demo.png
python make_dongle.py E:\           # E: = flashdisk dongle (key file SONICVAULT.key dibuat di sana)
                                    # dongle TIDAK perlu dicolok saat app dibuka, hanya saat masuk mode kripto
streamlit run app.py
```

Tanpa flashdisk (untuk uji): `python make_dongle.py demo_dongle`, lalu set
`SONICVAULT_DONGLE_DIR=demo_dongle` (PowerShell: `$env:SONICVAULT_DONGLE_DIR="demo_dongle"`).
Kalau sensor sidik jari bermasalah saat uji: `SONICVAULT_SKIP_BIOMETRIC=1` melewati verifikasi biometrik (jangan dipakai saat demo).

Lagu boleh MP3/FLAC/OGG/WAV: aplikasi otomatis mengubahnya ke WAV 16-bit saat diunggah (`core/audio_convert.py`, memakai paket `soundfile`).
Yang tidak boleh adalah mengubah *hasil stego* kembali ke MP3, karena pesannya hilang.

## Pemetaan ke kriteria dosen

| Kriteria | File |
|---|---|
| Login biometrik + hanya hidup dengan dongle | `core/auth.py` (sidik jari WebAuthn, key file flashdisk), gerbang mode kripto di `app.py`; semua fungsi kripto dan kunci database mati tanpa dongle |
| Login memakai algoritma kriptografi | `core/auth.py` (bcrypt + salt) |
| Pesan teks: super enkripsi | `core/crypto_text.py` (Vigenère lalu AES-256-GCM) |
| File dienkripsi dengan algoritma beda | `core/crypto_file.py` (ChaCha20-Poly1305) |
| Pesan penting dienkripsi di basisdata | `core/db.py` (metadata lagu, kredensial sidik jari, arsip: AES-GCM, kunci dari dongle) |
| Pesan gambar: steganografi | `core/stego_image.py` (LSB PNG); tambahan: `stego_audio.py`, `stego_text.py` |
| Aset penting: blockchain sederhana | `core/blockchain.py` (hash SHA-256 audio, cover, lirik, lampiran) |

## Cara masuk mode kripto

1. Buka aplikasi: tampil pemutar musik biasa (daftar lagu, cari, putar), tanpa dongle.
   Siapa pun bisa menambah lagu biasa lewat **➕ Tambah lagu** (WAV + cover + lirik). Lagu publik ini ikut tercatat
   di blockchain dengan format yang sama seperti lagu berpesan, jadi lagu berpesan tidak menonjol.
2. Ketik **frasa rahasia** di kotak "Cari lagu" lalu tekan **Enter**. Bawaan: `sonic vault`.
   Ganti frasa: `python make_secret.py`, lalu tempel hash-nya ke `SECRET_HASH` di `app.py`
   (atau set env `SONICVAULT_SECRET_HASH`).
3. Colok dongle → daftar/masuk (password + sidik jari) → mode kripto terbuka.
4. Dongle dicabut → mode kripto terkunci pada interaksi berikutnya. Tombol **Tutup** kembali ke pemutar.

## Tampilan proses kripto

Di mode kripto, setelah **Buat lagu** muncul panel **🔬 Proses enkripsi**: teks asli → hasil Vigenère (hex) → ciphertext AES-GCM/ChaCha20 (hex acak) → disisipkan ke gambar/audio/lirik.
Setelah **Buka** muncul panel **🔬 Proses dekripsi** dengan urutan sebaliknya (dan "tidak ada pesan" untuk bagian yang kosong atau kunci yang salah). Gunakan ini saat demo untuk menunjukkan hasil enkripsi yang acak.

## Alur demo

1. Tunjukkan pemutar biasa: tambah satu lagu lewat **Tambah lagu**, cari, dan putar. Ketik frasa rahasia tanpa dongle → hanya muncul "Colok dongle".
2. Colok dongle → Daftar (password + sidik jari) → Masuk (password + sidik jari).
3. **Buat**: pilih `lagu_demo.wav` dan `cover_demo.png`, isi lirik. Isi kunci pesan, lalu cover = lokasi, rekam suara = kegiatan, lirik = waktu.
4. Salin kode `SV-xxxxxxxx` (atau unduh zip) dan bagikan kuncinya terpisah.
5. **Buka**: tanpa kunci / kunci salah → tampak lagu biasa. Dengan kunci benar → tiap bagian muncul.
6. Simpan teks ke **Arsip** (tersimpan terenkripsi di database).
7. Ubah 1 byte file di `storage/<id>/audio.wav`, buka lagi → verifikasi blockchain ❌.
8. Cabut dongle → mode kripto terkunci.

## Catatan dan batasan (bahan laporan)

- LSB tidak tahan kompresi (MP3/JPG/kompresi WhatsApp). Selalu bagikan WAV/PNG sebagai file.
- Posisi bit diacak memakai kunci, jadi tanpa kunci header pesan tidak bisa ditemukan.
- Kapasitas: ±1 bit per sampel/kanal. WAV stereo 44,1 kHz 1 menit ≈ 650 KB. App menampilkan kapasitas sebelum menyisipkan.
- Lirik menyembunyikan ciphertext dengan karakter zero-width; aplikasi yang membersihkan karakter itu akan menghilangkan pesannya.
- File `attach.enc` terlihat ada di paket (isinya tetap terenkripsi).
- Dongle diverifikasi lewat key file di flashdisk (tanpa serial hardware); kunci database diturunkan darinya.
- Frasa rahasia hanya pemicu tampilan (disimpan sebagai hash SHA-256), bukan batas keamanan. Keamanan sebenarnya ada pada dongle, sidik jari, password, dan kunci pesan.
- Judul/artis lagu di pemutar bersifat publik dan dibaca tanpa dongle; kredensial sidik jari dan arsip pesan tetap terenkripsi.
- "Link" disimulasikan sebagai kode `SV-…` atau paket zip; registri blockchain bersifat lokal per instalasi.
- Kunci pesan dibagikan manual di luar aplikasi. Pengembangan lanjut: pertukaran kunci dengan kriptografi kunci publik.