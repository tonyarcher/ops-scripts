#!/usr/bin/env python3
"""Tests for sites/vpn/mfa/server.py app logic. No sockets, no webauthn needed."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


store = _load("mfa_store_srv", "store.py")
totp_mod = _load("mfa_totp_srv", "totp.py")
server = _load("mfa_server", "server.py")


def _config(tmp: str) -> object:
    root = Path(tmp)
    (root / "peers" / "laptop").mkdir(parents=True)
    (root / "peers" / "laptop" / "client.conf").write_text(
        "[Interface]\nAddress = 10.0.0.2/32\n", encoding="utf-8"
    )
    (root / "mfa" / "totp").mkdir(parents=True)
    (root / "mfa" / "totp" / "laptop").write_text("JBSWY3DPEHPK3PXP", encoding="utf-8")
    return server.AppConfig(
        config_dir=tmp,
        bind="127.0.0.1",
        port=0,
        rp_id="vpn.ops",
        origin_https="https://vpn.ops:8443",
        ttl_ms=12 * 3600_000,
        page="<html></html>",
        totp_dir=str(root / "mfa" / "totp"),
        keys_dir=str(root / "mfa" / "webauthn"),
        session_path=str(root / "mfa" / "sessions.json"),
        peers_dir=str(root / "peers"),
        ca_path=str(root / "mfa" / "tls" / "ca.crt"),
    )


class TotpFlow(unittest.TestCase):
    def test_totp_unlocks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            app = server.MFAApp(_config(raw))  # type: ignore[arg-type]
            code = totp_mod.totp_at(
                totp_mod.decode_base32("JBSWY3DPEHPK3PXP"), time.time() * 1000
            )
            status, payload = app.check_totp("10.0.0.2", code)
            self.assertEqual(status, 200)
            self.assertTrue(app.is_open("10.0.0.2"))
            self.assertEqual(payload, {"ok": True})

    def test_bad_code(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            app = server.MFAApp(_config(raw))  # type: ignore[arg-type]
            status, _ = app.check_totp("10.0.0.2", "000000")
            self.assertEqual(status, 401)
            self.assertFalse(app.is_open("10.0.0.2"))

    def test_unknown_ip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            app = server.MFAApp(_config(raw))  # type: ignore[arg-type]
            status, payload = app.check_totp("9.9.9.9", "123456")
            self.assertEqual(status, 403)
            self.assertIn("error", payload)

    def test_rate_limited(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            app = server.MFAApp(_config(raw))  # type: ignore[arg-type]
            for _ in range(9):
                app.check_totp("10.0.0.2", "000000")
            status, payload = app.check_totp("10.0.0.2", "000000")
            self.assertEqual(status, 429)
            self.assertIn("error", payload)


class RegistrationGating(unittest.TestCase):
    def test_requires_totp(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            app = server.MFAApp(_config(raw))  # type: ignore[arg-type]
            status, _ = app.registration_options("10.0.0.2")
            self.assertEqual(status, 401)

    def test_options_after_unlock(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            app = server.MFAApp(_config(raw))  # type: ignore[arg-type]
            code = totp_mod.totp_at(
                totp_mod.decode_base32("JBSWY3DPEHPK3PXP"), time.time() * 1000
            )
            app.check_totp("10.0.0.2", code)
            status, payload = app.registration_options("10.0.0.2")
            self.assertEqual(status, 200)
            self.assertIn("challenge", payload)

    def test_register_expired_without_challenge(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            app = server.MFAApp(_config(raw))  # type: ignore[arg-type]
            code = totp_mod.totp_at(
                totp_mod.decode_base32("JBSWY3DPEHPK3PXP"), time.time() * 1000
            )
            app.check_totp("10.0.0.2", code)
            status, _ = app.register("10.0.0.2", {"id": "x"})
            self.assertEqual(status, 401)


class LoginGating(unittest.TestCase):
    def test_no_keys_registered(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            app = server.MFAApp(_config(raw))  # type: ignore[arg-type]
            status, payload = app.login_options("10.0.0.2")
            self.assertEqual(status, 400)
            self.assertIn("error", payload)

    def test_login_options_with_key(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cfg = _config(raw)
            app = server.MFAApp(cfg)  # type: ignore[arg-type]
            store.save_passkeys(
                cfg.keys_dir,  # type: ignore[attr-defined]
                "laptop",
                [store.Passkey(id="cred1", public_key="aGk=", counter=0)],
            )
            status, payload = app.login_options("10.0.0.2")
            self.assertEqual(status, 200)
            self.assertIn("challenge", payload)

    def test_whoami(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            app = server.MFAApp(_config(raw))  # type: ignore[arg-type]
            info = app.whoami("10.0.0.2")
            self.assertEqual(info["peer"], "laptop")
            self.assertFalse(info["open"])

    def test_client_ip_prefers_forwarded(self) -> None:
        self.assertEqual(
            server.client_ip_from({"x-forwarded-for": "1.2.3.4, 5.6.7.8"}, "9.9.9.9"),
            "1.2.3.4",
        )
        self.assertEqual(server.client_ip_from({}, "::ffff:10.0.0.2"), "10.0.0.2")


class VerifyRegistration(unittest.TestCase):
    def test_stores_base64url_id_and_response_transports(self) -> None:
        import base64
        import types

        fake = types.ModuleType("webauthn")

        class _Verified:
            credential_id = b"\x1f\x8b\x01"
            credential_public_key = b"\x02\x03"
            sign_count = 7

        def _verify(**kwargs: object) -> _Verified:
            self.assertIsInstance(kwargs.get("credential"), dict)
            return _Verified()

        fake.verify_registration_response = _verify  # type: ignore[attr-defined]
        with tempfile.TemporaryDirectory() as raw:
            app = server.MFAApp(_config(raw))  # type: ignore[arg-type]
            code = totp_mod.totp_at(
                totp_mod.decode_base32("JBSWY3DPEHPK3PXP"), time.time() * 1000
            )
            app.check_totp("10.0.0.2", code)
            _, options = app.registration_options("10.0.0.2")
            challenge = str(options["challenge"])
            body = {
                "id": "cred-id",
                "response": {"transports": ["usb", "nfc"]},
            }
            with patch.dict(sys.modules, {"webauthn": fake}):
                cred_id, pub, counter, transports = server.verify_registration(
                    body, challenge, "https://vpn.ops:8443", "vpn.ops"
                )
            self.assertNotIn("b'", cred_id)
            self.assertEqual(
                cred_id,
                base64.urlsafe_b64encode(b"\x1f\x8b\x01").decode().rstrip("="),
            )
            self.assertEqual(counter, 7)
            self.assertEqual(transports, ["usb", "nfc"])
            self.assertEqual(pub, base64.b64encode(b"\x02\x03").decode())

    def test_register_maps_verification_error_to_401(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            app = server.MFAApp(_config(raw))  # type: ignore[arg-type]
            code = totp_mod.totp_at(
                totp_mod.decode_base32("JBSWY3DPEHPK3PXP"), time.time() * 1000
            )
            app.check_totp("10.0.0.2", code)
            app.registration_options("10.0.0.2")
            with patch.object(
                server, "verify_registration", side_effect=ValueError("tampered")
            ):
                status, payload = app.register("10.0.0.2", {"id": "x"})
            self.assertEqual(status, 401)
            self.assertIn("error", payload)


class VerifyLogin(unittest.TestCase):
    def test_login_maps_verification_error_to_401(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cfg = _config(raw)
            app = server.MFAApp(cfg)  # type: ignore[arg-type]
            store.save_passkeys(
                cfg.keys_dir,  # type: ignore[attr-defined]
                "laptop",
                [store.Passkey(id="cred1", public_key="aGk=", counter=0)],
            )
            _, options = app.login_options("10.0.0.2")
            self.assertIn("challenge", options)
            with patch.object(
                server, "verify_authentication", side_effect=ValueError("stale")
            ):
                status, payload = app.login("10.0.0.2", {"id": "cred1"})
            self.assertEqual(status, 401)
            self.assertIn("error", payload)

    def test_successful_login_clears_challenge_without_keyerror(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cfg = _config(raw)
            app = server.MFAApp(cfg)  # type: ignore[arg-type]
            store.save_passkeys(
                cfg.keys_dir,  # type: ignore[attr-defined]
                "laptop",
                [store.Passkey(id="cred1", public_key="aGk=", counter=0)],
            )
            app.login_options("10.0.0.2")
            with patch.object(server, "verify_authentication", return_value=5):
                status, _ = app.login("10.0.0.2", {"id": "cred1"})
            self.assertEqual(status, 200)
            self.assertNotIn("10.0.0.2", app.challenges)
            self.assertTrue(app.is_open("10.0.0.2"))


if __name__ == "__main__":
    unittest.main()
