"""Buat lagu WAV dan cover PNG contoh di folder demo/ untuk uji coba."""
import os
import wave

import numpy as np
from PIL import Image

os.makedirs("demo", exist_ok=True)
sr, dur = 44100, 120
rng = np.random.default_rng(1)
t = np.arange(sr * dur) / sr
chords = [(261.63, 329.63, 392.0), (220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (196.0, 246.94, 293.66)]
seg = (t // 2).astype(int) % len(chords)
sig = np.zeros_like(t)
for k, chord in enumerate(chords):
    m = seg == k
    for f in chord:
        sig[m] += np.sin(2 * np.pi * f * t[m])
sig = sig * np.exp(-4 * (t % 0.5)) / 3
left = np.clip(sig + 0.04 * rng.standard_normal(t.size), -1, 1)
right = np.clip(sig + 0.04 * rng.standard_normal(t.size), -1, 1)
pcm = (np.column_stack([left, right]) * 0.6 * 32767).astype("<i2")
with wave.open("demo/lagu_demo.wav", "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes(pcm.tobytes())

y, x = np.mgrid[0:800, 0:800]
img = np.stack([x / 800 * 255, y / 800 * 255, (x + y) / 1600 * 255], -1) + rng.normal(0, 12, (800, 800, 3))
Image.fromarray(np.clip(img, 0, 255).astype("uint8")).save("demo/cover_demo.png")
print("Selesai: demo/lagu_demo.wav dan demo/cover_demo.png")
