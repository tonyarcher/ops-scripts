#!/usr/bin/env python3
"""Tests for sites/vpn/mfa/totp.py. No network."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("mfa_totp", ROOT / "totp.py")
assert _spec is not None and _spec.loader is not None
totp = importlib.util.module_from_spec(_spec)
sys.modules["mfa_totp"] = totp
_spec.loader.exec_module(totp)


class TotpTests(unittest.TestCase):
    def test_known_secret_roundtrip(self) -> None:
        secret = totp.decode_base32("JBSWY3DPEHPK3PXP")
        code = totp.totp_at(secret, 0)
        self.assertEqual(len(code), 6)
        self.assertTrue(totp.totp_ok("JBSWY3DPEHPK3PXP", code, 0))
        self.assertFalse(totp.totp_ok("JBSWY3DPEHPK3PXP", "000000", 0))

    def test_invalid_base32(self) -> None:
        with self.assertRaises(ValueError):
            totp.decode_base32("!!!!")

    def test_bad_code_format(self) -> None:
        self.assertFalse(totp.totp_ok("JBSWY3DPEHPK3PXP", "abc123", 0))
        self.assertFalse(totp.totp_ok("JBSWY3DPEHPK3PXP", "12345", 0))


if __name__ == "__main__":
    unittest.main()
