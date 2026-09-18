#!/usr/bin/env python3
"""Optional MFA portal for ops-vpn HTTP on the tunnel. TOTP + passkeys.

No IdP. Sessions gate tunnel IPs for WG_MFA_TTL_HOURS.

Run:  python sites/vpn/mfa/server.py
Env:  WG_CONFIG_DIR, MFA_BIND, MFA_PORT, WG_MFA_HOST, WG_MFA_TTL_HOURS
Needs: page.html next to this file. Passkeys need `webauthn` (requirements.txt).
"""

from __future__ import annotations

import argparse
import base64
import datetime
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from store import (
    Passkey,
    Session,
    load_passkeys,
    load_sessions,
    load_totp_secrets,
    peer_for_address,
    save_passkeys,
    save_sessions,
)
from totp import totp_ok

HERE = Path(__file__).resolve().parent
CHALLENGE_TTL_MS = 120_000
FAIL_WINDOW_MS = 10 * 60_000
FAIL_LIMIT = 8


@dataclass
class Challenge:
    kind: str
    challenge: str
    exp: float


@dataclass
class FailRow:
    n: int
    reset: float


@dataclass
class AppConfig:
    config_dir: str
    bind: str
    port: int
    rp_id: str
    origin_https: str
    ttl_ms: int
    page: str
    totp_dir: str
    keys_dir: str
    session_path: str
    peers_dir: str
    ca_path: str


def load_config() -> AppConfig:
    """Load portal config from the environment."""
    config_dir = os.environ.get("WG_CONFIG_DIR", "/config")
    bind = os.environ.get("MFA_BIND", "127.0.0.1")
    port = int(os.environ.get("MFA_PORT", "9090"))
    rp_id = os.environ.get("WG_MFA_HOST", "vpn.ops")
    ttl_hours = max(1, int(os.environ.get("WG_MFA_TTL_HOURS", "12")))
    page = (HERE / "page.html").read_text(encoding="utf-8")
    return AppConfig(
        config_dir=config_dir,
        bind=bind,
        port=port,
        rp_id=rp_id,
        origin_https=f"https://{rp_id}:8443",
        ttl_ms=ttl_hours * 3600_000,
        page=page,
        totp_dir=str(Path(config_dir) / "mfa" / "totp"),
        keys_dir=str(Path(config_dir) / "mfa" / "webauthn"),
        session_path=str(Path(config_dir) / "mfa" / "sessions.json"),
        peers_dir=str(Path(config_dir) / "peers"),
        ca_path=str(Path(config_dir) / "mfa" / "tls" / "ca.crt"),
    )


def b64url_encode(raw: bytes) -> str:
    """Encode bytes as unpadded base64url."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64url_decode(data: str) -> bytes:
    """Decode unpadded base64url. Raises ValueError."""
    padded = data + "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(padded)


def log_line(level: str, msg: str, **extra: object) -> None:
    """Emit one JSON log line on stdout."""
    record = {
        "ts": datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds"),
        "level": level,
        "msg": msg,
        "service": "mfa",
        **extra,
    }
    sys.stdout.write(json.dumps(record) + "\n")
    sys.stdout.flush()


class MFAApp:
    """Request logic without socket code, so tests can drive it."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.challenges: dict[str, Challenge] = {}
        self.fails: dict[str, FailRow] = {}

    def peer_of(self, ip: str) -> str | None:
        """Return the WireGuard peer name for a tunnel IP."""
        return peer_for_address(self.config.peers_dir, ip)

    def is_open(self, ip: str) -> bool:
        """Return True when the IP has a live session."""
        row = load_sessions(self.config.session_path).get(ip)
        return bool(row and row.exp > time.time() * 1000)

    def unlock(self, ip: str, peer: str) -> None:
        """Mark an IP as MFA-unlocked for the TTL."""
        rows = load_sessions(self.config.session_path)
        rows[ip] = Session(exp=time.time() * 1000 + self.config.ttl_ms, peer=peer)
        save_sessions(self.config.session_path, rows)

    def limited(self, ip: str) -> bool:
        """Rate-limit TOTP/login attempts per IP. True means reject."""
        now = time.time() * 1000
        row = self.fails.get(ip)
        if row is None or row.reset < now:
            self.fails[ip] = FailRow(n=1, reset=now + FAIL_WINDOW_MS)
            return False
        row.n += 1
        return row.n > FAIL_LIMIT

    def check_totp(self, ip: str, code: str) -> tuple[int, dict[str, object]]:
        """Verify a TOTP code for the peer behind ip."""
        if self.limited(ip):
            return 429, {"error": "too many attempts"}
        peer = self.peer_of(ip)
        if not peer:
            return 403, {"error": "unknown tunnel IP"}
        secret = load_totp_secrets(self.config.totp_dir).get(peer)
        if not secret or not totp_ok(secret, code or ""):
            return 401, {"error": "bad code"}
        self.unlock(ip, peer)
        return 200, {"ok": True}

    def registration_options(self, ip: str) -> tuple[int, dict[str, object]]:
        """Build WebAuthn registration options for the peer behind ip."""
        peer = self.peer_of(ip)
        if not peer or not self.is_open(ip):
            return 401, {"error": "unlock with TOTP first"}
        existing = load_passkeys(self.config.keys_dir, peer)
        challenge = b64url_encode(secrets.token_bytes(32))
        self.challenges[ip] = Challenge(
            kind="reg", challenge=challenge, exp=time.time() * 1000 + CHALLENGE_TTL_MS
        )
        return 200, {
            "rp": {"name": "ops-vpn", "id": self.config.rp_id},
            "user": {
                "id": b64url_encode(peer.encode()),
                "name": peer,
                "displayName": peer,
            },
            "challenge": challenge,
            "pubKeyCredParams": [{"type": "public-key", "alg": -7}],
            "excludeCredentials": [
                {"type": "public-key", "id": k.id} for k in existing
            ],
            "authenticatorSelection": {
                "residentKey": "preferred",
                "userVerification": "preferred",
            },
            "attestation": "none",
        }

    def register(
        self, ip: str, body: dict[str, object]
    ) -> tuple[int, dict[str, object]]:
        """Verify a registration response and store the new passkey."""
        peer = self.peer_of(ip)
        chal = self.challenges.get(ip)
        now = time.time() * 1000
        if (
            not peer
            or not self.is_open(ip)
            or not chal
            or chal.kind != "reg"
            or chal.exp < now
        ):
            return 401, {"error": "register session expired"}
        try:
            cred_id, public_key, counter, transports = verify_registration(
                body, chal.challenge, self.config.origin_https, self.config.rp_id
            )
        except Exception as exc:  # noqa: BLE001 - verification failures become 401
            return 401, {"error": str(exc)}
        keys = load_passkeys(self.config.keys_dir, peer)
        keys.append(
            Passkey(
                id=cred_id,
                public_key=public_key,
                counter=counter,
                transports=transports,
            )
        )
        save_passkeys(self.config.keys_dir, peer, keys)
        self.challenges.pop(ip, None)
        return 200, {"ok": True}

    def login_options(self, ip: str) -> tuple[int, dict[str, object]]:
        """Build WebAuthn authentication options for the peer behind ip."""
        peer = self.peer_of(ip)
        if not peer:
            return 403, {"error": "unknown tunnel IP"}
        keys = load_passkeys(self.config.keys_dir, peer)
        if not keys:
            return 400, {"error": "no passkey registered"}
        challenge = b64url_encode(secrets.token_bytes(32))
        self.challenges[ip] = Challenge(
            kind="login", challenge=challenge, exp=time.time() * 1000 + CHALLENGE_TTL_MS
        )
        return 200, {
            "challenge": challenge,
            "rpId": self.config.rp_id,
            "allowCredentials": [{"type": "public-key", "id": k.id} for k in keys],
            "userVerification": "preferred",
        }

    def login(self, ip: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
        """Verify an authentication response and unlock the IP."""
        if self.limited(ip):
            return 429, {"error": "too many attempts"}
        peer = self.peer_of(ip)
        chal = self.challenges.get(ip)
        now = time.time() * 1000
        if not peer or not chal or chal.kind != "login" or chal.exp < now:
            return 401, {"error": "login session expired"}
        cred_id = body.get("id")
        if not isinstance(cred_id, str):
            return 401, {"error": "unknown key"}
        stored = [
            k for k in load_passkeys(self.config.keys_dir, peer) if k.id == cred_id
        ]
        if not stored:
            return 401, {"error": "unknown key"}
        try:
            new_counter = verify_authentication(
                body,
                chal.challenge,
                self.config.origin_https,
                self.config.rp_id,
                stored[0],
            )
        except Exception as exc:  # noqa: BLE001 - verification failures become 401
            return 401, {"error": str(exc)}
        updated = [
            Passkey(
                id=k.id,
                public_key=k.public_key,
                counter=new_counter,
                transports=k.transports,
            )
            if k.id == cred_id
            else k
            for k in load_passkeys(self.config.keys_dir, peer)
        ]
        save_passkeys(self.config.keys_dir, peer, updated)
        self.challenges.pop(ip, None)
        self.unlock(ip, peer)
        return 200, {"ok": True}

    def whoami(self, ip: str) -> dict[str, object]:
        """Describe the calling tunnel IP."""
        return {"ip": ip, "peer": self.peer_of(ip), "open": self.is_open(ip)}


def verify_registration(
    body: dict[str, object], challenge: str, origin: str, rp_id: str
) -> tuple[str, str, int, list[str] | None]:
    """Verify a WebAuthn registration. Needs the `webauthn` package (v3)."""
    try:
        from webauthn import (  # type: ignore[import-not-found]
            verify_registration_response,
        )
    except ImportError as exc:
        raise RuntimeError(
            "webauthn package required for passkey registration"
        ) from exc
    verification = verify_registration_response(
        credential=body,
        expected_challenge=b64url_decode(challenge),
        expected_origin=origin,
        expected_rp_id=rp_id,
    )
    raw_transports: object = None
    response = body.get("response")
    if isinstance(response, dict):
        raw_transports = response.get("transports")
    if raw_transports is None:
        raw_transports = body.get("transports", [])
    transports: list[str] | None = None
    if isinstance(raw_transports, list):
        transports = [str(t) for t in raw_transports]
    return (
        b64url_encode(bytes(verification.credential_id)),
        base64.b64encode(bytes(verification.credential_public_key)).decode(),
        int(verification.sign_count),
        transports,
    )


def verify_authentication(
    body: dict[str, object], challenge: str, origin: str, rp_id: str, stored: Passkey
) -> int:
    """Verify a WebAuthn assertion. Returns the new sign counter."""
    try:
        from webauthn import (
            verify_authentication_response,
        )
    except ImportError as exc:
        raise RuntimeError("webauthn package required for passkey login") from exc
    verification = verify_authentication_response(
        credential=body,
        expected_challenge=b64url_decode(challenge),
        expected_origin=origin,
        expected_rp_id=rp_id,
        credential_public_key=base64.b64decode(stored.public_key),
        credential_current_sign_count=stored.counter,
    )
    return int(verification.new_sign_count)


def client_ip_from(headers: dict[str, str], remote: str) -> str:
    """Prefer X-Forwarded-For, else the socket peer address."""
    fwd = headers.get("x-forwarded-for", "")
    if fwd.strip():
        return fwd.split(",")[0].strip()
    return remote.replace("::ffff:", "")


class Handler(BaseHTTPRequestHandler):
    """HTTP routing for the MFA portal."""

    app: MFAApp

    def _send_json(self, status: int, payload: object) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _client_ip(self) -> str:
        headers = {k.lower(): v for k, v in dict(self.headers).items()}
        return client_ip_from(headers, self.client_address[0])

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def do_GET(self) -> None:
        """Route GET requests."""
        try:
            self._route_get()
        except Exception as exc:  # noqa: BLE001 - handler converts failures to 500 JSON
            log_line("error", "request failed", err=str(exc))
            try:
                self._send_json(500, {"error": "internal error"})
            except OSError:
                pass

    def _route_get(self) -> None:
        """GET routing without the 500 wrapper."""
        path = urlparse(self.path).path
        ip = self._client_ip()
        if path in ("/", "/index.html"):
            data = self.app.config.page.encode()
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/ca.crt":
            try:
                body = Path(self.app.config.ca_path).read_bytes()
            except OSError:
                self._send_json(404, {"error": "no CA yet"})
                return
            self.send_response(200)
            self.send_header("content-type", "application/x-x509-ca-cert")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/whoami":
            self._send_json(200, self.app.whoami(ip))
            return
        if path == "/auth":
            self.send_response(200 if self.app.is_open(ip) else 401)
            self.send_header("content-length", "0")
            self.end_headers()
            return
        if path == "/webauthn/register/options":
            status, payload = self.app.registration_options(ip)
            self._send_json(status, payload)
            return
        if path == "/webauthn/login/options":
            status, payload = self.app.login_options(ip)
            self._send_json(status, payload)
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        """Route POST requests."""
        try:
            self._route_post()
        except Exception as exc:  # noqa: BLE001 - handler converts failures to 500 JSON
            log_line("error", "request failed", err=str(exc))
            try:
                self._send_json(500, {"error": "internal error"})
            except OSError:
                pass

    def _route_post(self) -> None:
        """POST routing without the 500 wrapper."""
        path = urlparse(self.path).path
        ip = self._client_ip()
        if path == "/totp":
            status, payload = self.app.check_totp(
                ip, str(self._read_json().get("code", ""))
            )
            self._send_json(status, payload)
            return
        if path == "/webauthn/register":
            status, payload = self.app.register(ip, self._read_json())
            self._send_json(status, payload)
            return
        if path == "/webauthn/login":
            status, payload = self.app.login(ip, self._read_json())
            self._send_json(status, payload)
            return
        self._send_json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        """Suppress default access logs; JSON logging happens elsewhere."""


def build_parser() -> argparse.ArgumentParser:
    """Build the server CLI parser."""
    p = argparse.ArgumentParser(description="MFA portal for ops-vpn (TOTP + passkeys).")
    p.add_argument("--bind", default=None)
    p.add_argument("--port", type=int, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    """Serve the MFA portal forever."""
    args = build_parser().parse_args(argv)
    config = load_config()
    if args.bind:
        config.bind = args.bind
    if args.port:
        config.port = args.port
    app = MFAApp(config)
    Handler.app = app
    server = ThreadingHTTPServer((config.bind, config.port), Handler)
    log_line("info", "listening", service="mfa", port=config.port, rp=config.rp_id)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
