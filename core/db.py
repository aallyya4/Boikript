"""SQLite dengan data penting terenkripsi (AES-256-GCM, kunci turunan dongle)."""
import json
import os
import sqlite3
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DB_PATH = os.environ.get("SONICVAULT_DB", "sonicvault.db")


def enc_field(key: bytes, data: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, data, aad)


def dec_field(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


def _q(sql: str, args=()):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        with con:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def init():
    con = sqlite3.connect(DB_PATH)
    with con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            username TEXT PRIMARY KEY, pw_hash BLOB NOT NULL, face BLOB, created REAL, fp BLOB);
        CREATE TABLE IF NOT EXISTS members(
            username TEXT PRIMARY KEY, pw_hash BLOB NOT NULL, created REAL);
        CREATE TABLE IF NOT EXISTS tracks(
            id TEXT PRIMARY KEY, owner TEXT, meta BLOB NOT NULL, created REAL);
        CREATE TABLE IF NOT EXISTS inbox(
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT, rid TEXT, body BLOB NOT NULL, created REAL);
        CREATE TABLE IF NOT EXISTS chain(
            idx INTEGER PRIMARY KEY, ts REAL, data TEXT, prev_hash TEXT, hash TEXT);
        """)
        if "fp" not in [r[1] for r in con.execute("PRAGMA table_info(users)")]:  # migrasi DB lama
            con.execute("ALTER TABLE users ADD COLUMN fp BLOB")
    con.close()


# ---- users ----
def add_user(username: str, pw_hash: bytes, face_blob, fp_blob=None):
    _q("INSERT INTO users(username, pw_hash, face, created, fp) VALUES (?,?,?,?,?)",
       (username, pw_hash, face_blob, time.time(), fp_blob))


def set_fp(username: str, fp_blob: bytes):
    _q("UPDATE users SET fp=? WHERE username=?", (fp_blob, username))


def get_user(username: str):
    rows = _q("SELECT * FROM users WHERE username=?", (username,))
    return rows[0] if rows else None


# ---- member (akun pengguna biasa di pemutar) ----
def add_member(username: str, pw_hash: bytes):
    _q("INSERT INTO members(username, pw_hash, created) VALUES (?,?,?)", (username, pw_hash, time.time()))


def get_member(username: str):
    rows = _q("SELECT * FROM members WHERE username=?", (username,))
    return rows[0] if rows else None


# ---- tracks (metadata terenkripsi) ----
def put_track(key: bytes, owner: str, rid: str, meta: dict):
    blob = enc_field(key, json.dumps(meta).encode(), rid.encode())
    _q("INSERT OR REPLACE INTO tracks VALUES (?,?,?,?)", (rid, owner, blob, time.time()))


def has_track(rid: str) -> bool:
    return bool(_q("SELECT 1 FROM tracks WHERE id=?", (rid,)))


def delete_track(rid: str):
    _q("DELETE FROM tracks WHERE id=?", (rid,))


def list_tracks(key: bytes):
    out = []
    for r in _q("SELECT * FROM tracks ORDER BY created DESC"):
        try:
            out.append(json.loads(dec_field(key, r["meta"], r["id"].encode())))
        except InvalidTag:
            continue
    return out


# ---- arsip pesan penting (terenkripsi) ----
def put_message(key: bytes, owner: str, rid: str, payload: dict):
    blob = enc_field(key, json.dumps(payload).encode(), owner.encode())
    _q("INSERT INTO inbox(owner, rid, body, created) VALUES (?,?,?,?)", (owner, rid, blob, time.time()))


def list_messages(key: bytes, owner: str):
    out = []
    for r in _q("SELECT * FROM inbox WHERE owner=? ORDER BY created DESC", (owner,)):
        try:
            out.append({"rid": r["rid"], "created": r["created"],
                        "payload": json.loads(dec_field(key, r["body"], owner.encode()))})
        except InvalidTag:
            continue
    return out


# ---- blockchain ----
def chain_rows():
    return _q("SELECT * FROM chain ORDER BY idx")


def chain_insert(idx: int, ts: float, data: str, prev_hash: str, h: str):
    _q("INSERT INTO chain VALUES (?,?,?,?,?)", (idx, ts, data, prev_hash, h))