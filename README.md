# BoiKript

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

## Kunci terpisah per bagian

Cover, audio, lirik, dan lampiran masing-masing punya **kunci sendiri**. Satu kunci hanya membuka bagiannya; bagian lain tetap terkunci sampai kuncinya juga diisi.
Bagikan tiap kunci lewat jalur atau orang yang berbeda, jadi satu kebocoran tidak membuka seluruh pesan. Boleh juga mengisi kunci yang sama untuk beberapa bagian.
Saat membuka, bagian yang kunci-nya belum diisi dan yang kuncinya salah tampil sama ("terkunci/kosong"), jadi orang luar tidak bisa tahu bagian mana yang benar-benar berisi pesan.

## Dua jenis akun

| | Akun pemutar (pengguna biasa) | Akun mode kripto |
|---|---|---|
| Daftar/masuk | Sidebar **👤 Masuk / Daftar** | Setelah frasa rahasia dan dongle |
| Syarat | Username + password | Username + password (terpisah dari akun pemutar) + sidik jari + dongle |
| Hak | Upload lagu, edit/hapus lagu **miliknya sendiri** | Buat lagu berpesan, buka pesan, kelola lagu miliknya, arsip, registri |

**Login akun wajib di awal**, sebelum masuk aplikasi (daftar dengan username, password, dan ulangi password). Login hilang jika halaman browser dimuat ulang.
Mode kripto bisa dimasuki dari akun pemutar mana pun lewat frasa rahasia; setelah itu ia meminta login sendiri (akun kripto, sidik jari, dongle).
Daftar akun pemutar disimpan di tabel `members` (hash bcrypt), terpisah dari tabel `users` milik mode kripto, jadi nama yang sama di kedua sisi tidak saling terkait.

## Kelola lagu (CRUD) dan kepemilikan

- **Create:** ➕ Tambah lagu (akun pemutar) atau tab Buat (mode kripto).
- **Read:** pemutar, halaman lagu, dan tab Buka.
- **Update:** edit judul, artis, dan lirik. Pesan yang tersembunyi di lirik tetap aman karena karakter tak terlihatnya dipindahkan ke lirik baru. Cover dan audio tidak bisa diganti (akan menghapus pesan yang tertanam); hapus dan buat ulang.
- **Delete:** hapus permanen dengan konfirmasi. Riwayatnya tetap ada di blockchain (rantai hanya bisa ditambah).
- **Hanya pemilik** yang bisa mengedit dan menghapus. Pemilik dibaca dari blok pembuatan di blockchain: `m:<username>` untuk akun pemutar, `k:<username>` untuk akun mode kripto. Lagu lama atau hasil impor tanpa pemilik bisa dikelola akun mode kripto mana pun.
- Di tab **🗂 Kelola** (mode kripto) tiap lagu menampilkan kode berbagi `SV-...` dan tombol unduh paket `.zip`.
- Setiap perubahan lirik dicatat sebagai blok baru, jadi verifikasi integritas lirik tetap lolos setelah diedit.

## Arsip

Setelah pesan terbuka, tombol **Simpan teks ke arsip** menyimpan teks yang sudah terbaca ke database, terenkripsi AES-GCM dengan kunci dari dongle. Arsip hanya bisa dibaca dengan dongle terpasang dan login. Ini yang memenuhi kriteria "pesan penting dienkripsi pada basisdata".

## Pemutar

Klik **▶ Putar** membuka halaman lagu (cover, judul, lirik besar) dan bar pemutar di bawah. **← Beranda** (atau tombol Beranda di sidebar) kembali ke daftar lagu tanpa menghentikan lagu yang sedang diputar. Mencari lagu juga kembali ke beranda.

## Tampilan proses kripto

Setelah **Buat lagu** muncul panel **🔬 Proses enkripsi, tahap demi tahap**, dan setelah **Buka** muncul **🔬 Proses dekripsi**. Tiap bagian (Kunci, Cover, Audio, Lirik, Dokumen) punya tab sendiri berisi alur dan langkah bernomor:
- Teks asli → tabel byte (karakter, desimal, hex, biner).
- Vigenère: tabel per byte (byte masuk + byte kunci mod 256). Nilai kunci disembunyikan, bisa ditampilkan dengan sakelar "untuk belajar".
- AES-256-GCM / ChaCha20-Poly1305: nonce, isi terenkripsi, dan tag, dalam hex. Ini ciphertext acaknya.
- Ciphertext menjadi deretan bit (header panjang + isi).
- Penyembunyian: tabel lokasi acak, nilai sebelum dan sesudah, bit pesan. Untuk gambar: cover sebelum, sesudah, dan peta perubahan. Untuk audio: jumlah sampel yang berubah. Untuk lirik: karakter tak terlihat dibuat tampak sebagai 0/1.
- Dekripsi menampilkan urutan terbalik: lokasi dihitung dari kunci, bit dibaca, tag dicek, Vigenère dibalik, teks asli kembali.

## Dokumen lagu (umum)

Selain dokumen pendukung rahasia, setiap lagu boleh punya **Dokumen lagu** yang terlihat oleh semua pengguna, misalnya chord buatan sendiri, booklet, atau credits (maks. 20 MB).
- Diunggah lewat **➕ Tambah lagu** (opsional) atau di langkah Data lagu pada mode kripto.
- Tampil di halaman lagu sebagai kartu **📄 Dokumen lagu** (gambar dan TXT dipratinjau, semua jenis bisa diunduh).
- Pemilik bisa menambah, mengganti, atau menghapusnya lewat **⚙️ Edit / hapus lagu**. Setiap perubahan dicatat di blockchain.
- Ini fitur umum yang bisa dimiliki lagu apa pun, jadi keberadaannya bukan penanda pesan rahasia. Dokumen rahasia tetap terpisah, terenkripsi, dan tidak pernah tampil di pemutar.

## Bentuk pesan

| Jenis | Bagian | Contoh isi | Enkripsi | Disembunyikan di |
|---|---|---|---|---|
| Pesan teks | Cover | Lokasi: "Belakang gedung A" | Vigenère + AES-256-GCM | Gambar cover (LSB) |
| Pesan teks | Lirik | Waktu: "Jumat 19.30" | Vigenère + AES-256-GCM | Lirik (karakter tak terlihat) |
| Pesan file | Audio | Rekaman suara: kegiatan | ChaCha20-Poly1305 | Bunyi lagu (LSB) |
| Pesan file | Dokumen pendukung | Peta/denah (PNG/JPG), catatan (TXT), PDF | ChaCha20-Poly1305 | Disimpan terenkripsi (attach.enc) |

Dokumen yang terbuka ditampilkan sesuai jenisnya (gambar sebagai gambar, TXT sebagai teks) dan bisa diunduh.

## Alur demo

1. Tunjukkan pemutar biasa: tambah satu lagu lewat **Tambah lagu**, cari, dan putar. Ketik frasa rahasia tanpa dongle → hanya muncul "Colok dongle".
2. Colok dongle → Daftar (password + sidik jari) → Masuk (password + sidik jari).
3. **Buat**: pilih lagu dan cover, isi lirik. Isi tiap bagian beserta kuncinya sendiri: cover = lokasi, rekam suara = kegiatan, lirik = waktu.
4. Salin kode `SV-xxxxxxxx` (atau unduh zip) dan bagikan kuncinya terpisah.
5. **Buka**: isi satu kunci saja → hanya bagian itu yang terbuka; isi semuanya → pesan utuh.
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