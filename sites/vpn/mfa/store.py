#!/usr/bin/env python3
"""Filesystem stores for the MFA portal: sessions, TOTP secrets, passkeys.

Sessions live in one JSON file. TOTP secrets are one file per peer.
Passkeys are one JSON file per peer. Peer lookup scans client.conf files.

Run:  python sites/vpn/mfa/server.py
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

_ADDRESS_RE = re.compile(r"^Address\s*=\s*([0-9.]+)/", re.MULTILINE)


@dataclass
class Session:
    exp: float
    peer: str


@dataclass
class Passkey:
    id: str
    public_key: str
    counter: int
    transports: list[str] | None = None


def read_text(path: str | Path) -> str | None:
    """Return trimmed file text, or None when unreadable."""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def write_json(path: str | Path, value: object) -> None:
    """Write JSON with 0700 dirs and 0600 files."""
    target = Path(path)
    if target.parent != Path(".") and str(target.parent):
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(target.parent, 0o700)
        except OSError:
            pass
    target.write_text(json.dumps(value), encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass


def load_sessions(path: str | Path, now_ms: float | None = None) -> dict[str, Session]:
    """Load non-expired sessions. Returns {} when missing or corrupt."""
    import time

    now = now_ms if now_ms is not None else time.time() * 1000
    raw = read_text(path)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    live: dict[str, Session] = {}
    for ip, row in parsed.items():
        if not isinstance(row, dict):
            continue
        exp = row.get("exp")
        peer = row.get("peer")
        if isinstance(exp, (int, float)) and isinstance(peer, str) and exp > now:
            live[str(ip)] = Session(exp=float(exp), peer=peer)
    return live


def save_sessions(path: str | Path, rows: dict[str, Session]) -> None:
    """Persist sessions to path."""
    write_json(path, {ip: {"exp": s.exp, "peer": s.peer} for ip, s in rows.items()})


def load_totp_secrets(directory: str | Path) -> dict[str, str]:
    """Map peer name to TOTP secret from files in directory."""
    out: dict[str, str] = {}
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return out
    for name in names:
        secret = read_text(Path(directory) / name)
        if secret:
            out[name] = secret
    return out


def load_passkeys(directory: str | Path, peer: str) -> list[Passkey]:
    """Load passkeys for peer. Returns [] when missing or corrupt."""
    raw = read_text(Path(directory) / f"{peer}.json")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(parsed, list):
        return []
    keys: list[Passkey] = []
    for row in parsed:
        if not isinstance(row, dict):
            continue
        cred_id = row.get("id")
        pub = row.get("publicKey", row.get("public_key", ""))
        counter = row.get("counter", 0)
        if (
            isinstance(cred_id, str)
            and isinstance(pub, str)
            and isinstance(counter, int)
        ):
            transports = row.get("transports")
            keys.append(
                Passkey(
                    id=cred_id,
                    public_key=pub,
                    counter=counter,
                    transports=list(transports)
                    if isinstance(transports, list)
                    else None,
                )
            )
    return keys


def save_passkeys(directory: str | Path, peer: str, keys: list[Passkey]) -> None:
    """Persist passkeys for peer."""
    payload = [
        {
            "id": k.id,
            "publicKey": k.public_key,
            "counter": k.counter,
            "transports": k.transports,
        }
        for k in keys
    ]
    write_json(Path(directory) / f"{peer}.json", payload)


def peer_for_address(peers_dir: str | Path, ip: str) -> str | None:
    """Find the peer whose client.conf contains Address = <ip>/."""
    try:
        names = sorted(os.listdir(peers_dir))
    except OSError:
        return None
    for name in names:
        conf = read_text(Path(peers_dir) / name / "client.conf")
        if not conf:
            continue
        match = _ADDRESS_RE.search(conf)
        if match and match.group(1) == ip:
            return name
    return None
