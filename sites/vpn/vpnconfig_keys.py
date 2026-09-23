"""Key and secret generation and storage (wg keys, PSK, TOTP) for sites/vpn."""

from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from vpnconfig_exec import run_text
from vpnconfig_settings import Settings


def gen_private_key(wg: str) -> str:
    return run_text([wg, "genkey"])


def derive_public_key(wg: str, private: str) -> str:
    return run_text([wg, "pubkey"], stdin=private + "\n")


def gen_preshared_key(wg: str) -> str:
    return run_text([wg, "genpsk"])


def write_secret(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = body if body.endswith("\n") else body + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def write_public(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = body if body.endswith("\n") else body + "\n"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o644)


def read_trimmed(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def ensure_keypair(directory: Path, wg: str) -> tuple[str, str]:
    priv_path = directory / "private.key"
    pub_path = directory / "public.key"
    if priv_path.exists():
        private = read_trimmed(priv_path)
        if pub_path.exists():
            return private, read_trimmed(pub_path)
        public = derive_public_key(wg, private)
        write_public(pub_path, public)
        return private, public
    private = gen_private_key(wg)
    public = derive_public_key(wg, private)
    write_secret(priv_path, private)
    write_public(pub_path, public)
    return private, public


def ensure_psk(path: Path, wg: str) -> str:
    if path.exists():
        return read_trimmed(path)
    secret = gen_preshared_key(wg)
    write_secret(path, secret)
    return secret


def totp_secret_path(settings: Settings, name: str) -> Path:
    return settings.config_dir / "mfa" / "totp" / name


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def otpauth_uri(name: str, secret: str) -> str:
    return (
        f"otpauth://totp/ops-vpn:{name}?secret={secret}"
        "&issuer=ops-vpn&algorithm=SHA1&digits=6&period=30"
    )
