"""Buat dongle: python make_dongle.py E:\\   (E: = flashdisk)  atau  python make_dongle.py demo_dongle"""
import os
import sys

from core import auth

if len(sys.argv) < 2:
    sys.exit("Pemakaian: python make_dongle.py <drive atau folder flashdisk>")
target = sys.argv[1]
os.makedirs(target, exist_ok=True)
try:
    print("Dongle dibuat:", auth.make_dongle(target, force="--force" in sys.argv))
except FileExistsError as e:
    sys.exit(str(e) + " Tambahkan --force jika memang ingin menimpa.")
