"""Steganografi audio: LSB pada sampel WAV 16-bit PCM."""
import io
import wave

import numpy as np

from .stego_common import capacity, embed_bits, extract_bits


def _read(wav: bytes):
    with wave.open(io.BytesIO(wav), "rb") as w:
        params = w.getparams()
        if params.sampwidth != 2:
            raise ValueError("WAV harus 16-bit PCM (convert dulu dengan ffmpeg/Audacity).")
        frames = w.readframes(params.nframes)
    return params, np.frombuffer(frames, dtype="<i2").astype(np.int16)


def audio_capacity(wav: bytes) -> int:
    _, samples = _read(wav)
    return capacity(samples.size)


def embed_audio(wav: bytes, payload: bytes, seed: bytes) -> bytes:
    params, samples = _read(wav)
    samples = embed_bits(samples, payload, seed)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(2)
        w.setframerate(params.framerate)
        w.writeframes(samples.astype("<i2").tobytes())
    return out.getvalue()


def extract_audio(wav: bytes, seed: bytes) -> bytes:
    _, samples = _read(wav)
    return extract_bits(samples, seed)
