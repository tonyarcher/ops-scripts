#!/usr/bin/env python3
"""Tests for sites/vpn/mfa/store.py. No network."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("mfa_store", ROOT / "store.py")
assert _spec is not None and _spec.loader is not None
store = importlib.util.module_from_spec(_spec)
sys.modules["mfa_store"] = store
_spec.loader.exec_module(store)


class SessionsTests(unittest.TestCase):
    def test_roundtrip_and_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "sessions.json"
            now = time.time() * 1000
            store.save_sessions(
                path,
                {
                    "1.2.3.4": store.Session(exp=now + 60_000, peer="laptop"),
                    "5.6.7.8": store.Session(exp=now - 1000, peer="old"),
                },
            )
            loaded = store.load_sessions(path, now_ms=now)
            self.assertIn("1.2.3.4", loaded)
            self.assertNotIn("5.6.7.8", loaded)
            self.assertEqual(loaded["1.2.3.4"].peer, "laptop")

    def test_missing_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(store.load_sessions(Path(raw) / "nope.json"), {})

    def test_corrupt_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "sessions.json"
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(store.load_sessions(path), {})


class SecretsTests(unittest.TestCase):
    def test_totp_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "laptop").write_text("SECRET1\n", encoding="utf-8")
            got = store.load_totp_secrets(root)
            self.assertEqual(got, {"laptop": "SECRET1"})

    def test_missing_dir(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(store.load_totp_secrets(Path(raw) / "nope"), {})


class PasskeysTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            keys = [
                store.Passkey(
                    id="abc", public_key="aGk=", counter=3, transports=["usb"]
                )
            ]
            store.save_passkeys(root, "laptop", keys)
            loaded = store.load_passkeys(root, "laptop")
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].id, "abc")
            self.assertEqual(loaded[0].counter, 3)

    def test_missing_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(store.load_passkeys(Path(raw), "laptop"), [])


class PeerForAddressTests(unittest.TestCase):
    def test_finds_peer(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            peer_dir = root / "laptop"
            peer_dir.mkdir()
            (peer_dir / "client.conf").write_text(
                "[Interface]\nAddress = 10.13.13.2/32\n", encoding="utf-8"
            )
            self.assertEqual(store.peer_for_address(root, "10.13.13.2"), "laptop")
            self.assertIsNone(store.peer_for_address(root, "10.13.13.99"))

    def test_missing_dir(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertIsNone(store.peer_for_address(Path(raw) / "nope", "1.2.3.4"))


if __name__ == "__main__":
    unittest.main()
