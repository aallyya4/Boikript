"""Blockchain sederhana untuk mencatat hash aset (audio, cover, lirik, lampiran)."""
import hashlib
import json
import time

from . import db

GENESIS = "0" * 64


def _hash(idx: int, ts: float, data: str, prev: str) -> str:
    return hashlib.sha256(json.dumps([idx, ts, data, prev]).encode()).hexdigest()


def ensure_genesis():
    if not db.chain_rows():
        add_block({"note": "genesis"})


def add_block(data: dict) -> int:
    rows = db.chain_rows()
    idx = len(rows)
    prev = rows[-1]["hash"] if rows else GENESIS
    ts = time.time()
    payload = json.dumps(data, sort_keys=True)
    db.chain_insert(idx, ts, payload, prev, _hash(idx, ts, payload, prev))
    return idx


def validate():
    prev = GENESIS
    for r in db.chain_rows():
        if r["prev_hash"] != prev:
            return False, f"Blok #{r['idx']}: prev_hash tidak cocok (rantai putus)."
        if _hash(r["idx"], r["ts"], r["data"], r["prev_hash"]) != r["hash"]:
            return False, f"Blok #{r['idx']}: isi blok telah diubah."
        prev = r["hash"]
    return True, "Rantai utuh, semua blok valid."


def verify_file(data: bytes):
    """Cari hash file di chain. Return info blok, atau None jika tidak terdaftar/berubah."""
    h = hashlib.sha256(data).hexdigest()
    for r in db.chain_rows():
        d = json.loads(r["data"])
        if h in d.get("files", {}).values():
            return {"block": r["idx"], "release": d.get("release")}
    return None
