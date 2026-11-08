"""Ubah audio apa pun (MP3, M4A/AAC, FLAC, OGG, WAV 24-bit, dll.) menjadi WAV 16-bit PCM,
format yang dibutuhkan stego LSB.

Urutan: (1) sudah WAV 16-bit -> dipakai apa adanya, (2) soundfile, (3) ffmpeg bawaan paket imageio-ffmpeg
(atau ffmpeg di PATH) untuk format yang tidak dikenali soundfile.
"""
import io
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import soundfile as sf


def _ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _via_ffmpeg(data: bytes) -> bytes:
    exe = _ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg tidak tersedia (pasang dengan: pip install imageio-ffmpeg)")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp, "in.bin"), Path(tmp, "out.wav")
        src.write_bytes(data)
        r = subprocess.run([exe, "-loglevel", "error", "-y", "-i", str(src), "-vn",
                            "-acodec", "pcm_s16le", str(dst)], capture_output=True)
        if r.returncode != 0 or not dst.exists():
            raise RuntimeError(r.stderr.decode(errors="ignore").strip()[-200:] or "ffmpeg gagal")
        return dst.read_bytes()


def to_wav16(data: bytes) -> bytes:
    # 1. sudah WAV 16-bit PCM: pakai apa adanya
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            if w.getsampwidth() == 2:
                return data
    except (wave.Error, EOFError):
        pass
    # 2. soundfile (cepat)
    try:
        audio, rate = sf.read(io.BytesIO(data), dtype="int16", always_2d=True)
        out = io.BytesIO()
        sf.write(out, audio, rate, format="WAV", subtype="PCM_16")
        return out.getvalue()
    except Exception:
        pass
    # 3. ffmpeg (bisa membaca hampir semua format)
    try:
        return _via_ffmpeg(data)
    except Exception as e:
        raise ValueError(
            "Format audio tidak dikenali. Pastikan file benar-benar MP3/WAV/FLAC/OGG, atau ubah dulu ke WAV "
            f"dengan Audacity. (detail: {e})")