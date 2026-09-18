#!/usr/bin/env python3
"""RFC 6238 TOTP (SHA-1, 6 digits, 30s). Works with any local authenticator app.

No network. No Google account.

Run:  python sites/vpn/mfa/server.py
Test: python sites/vpn/mfa/tests/test_totp.py
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def decode_base32(secret: str) -> bytes:
    """Decode a base32 TOTP secret. Raises ValueError on bad input."""
    clean = (
        secret.upper()
        .replace("=", "")
        .replace(" ", "")
        .replace("\t", "")
        .replace("\n", "")
    )
    clean = clean.replace("\r", "")
    if not clean:
        raise ValueError("invalid base32")
    for ch in clean:
        if ch not in ALPHABET:
            raise ValueError("invalid base32")
    padded = clean + "=" * ((8 - len(clean) % 8) % 8)
    try:
        return base64.b32decode(padded, casefold=True)
    except Exception as exc:
        raise ValueError("invalid base32") from exc


def totp_at(secret: bytes, at_ms: float, period_sec: int = 30) -> str:
    """Return the 6-digit code for secret at at_ms (epoch millis)."""
    counter = int(at_ms // 1000 // period_sec)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(secret, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (
        ((digest[offset] & 0x7F) << 24)
        | (digest[offset + 1] << 16)
        | (digest[offset + 2] << 8)
        | digest[offset + 3]
    )
    return str(code % 1_000_000).zfill(6)


def totp_ok(secret_b32: str, code: str, at_ms: float | None = None) -> bool:
    """Check code against a +-1 step window. Constant-time compare."""
    try:
        secret = decode_base32(secret_b32)
    except ValueError:
        return False
    guess = code.replace(" ", "").replace("\t", "").replace("\n", "")
    if len(guess) != 6 or not guess.isdigit():
        return False
    now_ms = float(at_ms) if at_ms is not None else time.time() * 1000
    for window in (0, -1, 1):
        shifted = now_ms + window * 30_000
        if shifted < 0:
            continue
        candidate = totp_at(secret, shifted)
        if hmac.compare_digest(candidate, guess):
            return True
    return False
