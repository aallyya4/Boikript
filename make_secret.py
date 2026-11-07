"""Buat hash frasa rahasia baru: python make_secret.py
Tempel hasilnya ke SECRET_HASH di app.py, atau set env SONICVAULT_SECRET_HASH."""
import hashlib

phrase = input("Frasa rahasia baru: ")
print(hashlib.sha256(" ".join(phrase.lower().split()).encode()).hexdigest())