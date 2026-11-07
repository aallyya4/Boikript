# SonicVault

Pemutar musik yang menyimpan platform pesan rahasia. Pesan dipecah ke **cover (lokasi)**, **audio (kegiatan)**, **lirik (waktu)**, dan **lampiran** (opsional). Tiap bagian boleh kosong, dan penerima harus membuka semuanya untuk paham maksudnya.

## Instalasi

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |  Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
python make_demo_assets.py          # membuat demo/lagu_demo.wav dan demo/cover_demo.png
python make_dongle.py E:\           # E: = flashdisk dongle (key file SONICVAULT.key dibuat di sana)
streamlit run app.py
```

Tanpa flashdisk (untuk uji): `python make_dongle.py demo_dongle`, lalu set
`SONICVAULT_DONGLE_DIR=demo_dongle` (PowerShell: `$env:SONICVAULT_DONGLE_DIR="demo_dongle"`).
Kalau kamera bermasalah saat uji: `SONICVAULT_SKIP_FACE=1` melewati verifikasi wajah (jangan dipakai saat demo).
Verifikasi wajah terlalu ketat/longgar? Ubah `SONICVAULT_FACE_THRESHOLD` (default 80, makin kecil makin ketat).

Lagu MP3 harus diubah ke WAV 16-bit: `ffmpeg -i lagu.mp3 -ar 44100 -ac 2 -sample_fmt s16 lagu.wav`

## Pemetaan ke kriteria dosen

| Kriteria | File |
|---|---|
| Login biometrik + hanya hidup dengan dongle | `core/auth.py` (wajah OpenCV LBPH, key file flashdisk), gerbang di `app.py` |
| Login memakai algoritma kriptografi | `core/auth.py` (bcrypt + salt) |
| Pesan teks: super enkripsi | `core/crypto_text.py` (Vigenère lalu AES-256-GCM) |
| File dienkripsi dengan algoritma beda | `core/crypto_file.py` (ChaCha20-Poly1305) |
| Pesan penting dienkripsi di basisdata | `core/db.py` (metadata lagu, data wajah, arsip: AES-GCM, kunci dari dongle) |
| Pesan gambar: steganografi | `core/stego_image.py` (LSB PNG); tambahan: `stego_audio.py`, `stego_text.py` |
| Aset penting: blockchain sederhana | `core/blockchain.py` (hash SHA-256 audio, cover, lirik, lampiran) |

## Alur demo

1. Jalankan tanpa dongle → aplikasi menolak. Colok dongle → pemutar musik muncul.
2. Tab **Akun** → Daftar (3 foto wajah) → Masuk (password + wajah).
3. **Buat**: pilih `lagu_demo.wav` dan `cover_demo.png`, isi lirik. Isi kunci pesan, lalu cover = lokasi, rekam suara = kegiatan, lirik = waktu.
4. Salin kode `SV-xxxxxxxx` (atau unduh zip) dan bagikan kuncinya terpisah.
5. **Buka**: tanpa kunci / kunci salah → tampak lagu biasa. Dengan kunci benar → tiap bagian muncul.
6. Simpan teks ke **Arsip** (tersimpan terenkripsi di database).
7. Ubah 1 byte file di `storage/<id>/audio.wav`, buka lagi → verifikasi blockchain ❌.

## Catatan dan batasan (bahan laporan)

- LSB tidak tahan kompresi (MP3/JPG/kompresi WhatsApp). Selalu bagikan WAV/PNG sebagai file.
- Posisi bit diacak memakai kunci, jadi tanpa kunci header pesan tidak bisa ditemukan.
- Kapasitas: ±1 bit per sampel/kanal. WAV stereo 44,1 kHz 1 menit ≈ 650 KB. App menampilkan kapasitas sebelum menyisipkan.
- Lirik menyembunyikan ciphertext dengan karakter zero-width; aplikasi yang membersihkan karakter itu akan menghilangkan pesannya.
- File `attach.enc` terlihat ada di paket (isinya tetap terenkripsi).
- Dongle diverifikasi lewat key file di flashdisk (tanpa serial hardware); kunci database diturunkan darinya.
- "Link" disimulasikan sebagai kode `SV-…` atau paket zip; registri blockchain bersifat lokal per instalasi.
- Kunci pesan dibagikan manual di luar aplikasi. Pengembangan lanjut: pertukaran kunci dengan kriptografi kunci publik.
