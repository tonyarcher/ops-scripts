#!/usr/bin/env python3
"""Offline tests for sites/vpn/deploy.py. No docker or ssh."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("vpn_deploy", ROOT / "deploy.py")
assert _spec is not None and _spec.loader is not None
deploy = importlib.util.module_from_spec(_spec)
sys.modules["vpn_deploy"] = deploy
_spec.loader.exec_module(deploy)


class LoadDotenv(unittest.TestCase):
    def test_skips_comments_and_blanks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / ".env"
            path.write_text(
                "# hi\n\nVPN_HOST=203.0.113.10\nVPN_DEPLOY_USER=deploy\n",
                encoding="utf-8",
            )
            got = deploy.load_dotenv(path)
        self.assertEqual(got["VPN_HOST"], "203.0.113.10")
        self.assertEqual(got["VPN_DEPLOY_USER"], "deploy")

    def test_missing_file(self) -> None:
        self.assertEqual(deploy.load_dotenv(Path("/no/such/.env")), {})


class ParseArgs(unittest.TestCase):
    def test_defaults_to_up(self) -> None:
        args = deploy.parse_args([])
        self.assertEqual(args.command, "up")
        self.assertFalse(args.remote)

    def test_peer_name(self) -> None:
        args = deploy.parse_args(["peer", "laptop"])
        self.assertEqual(args.command, "peer")
        self.assertEqual(args.rest, ["laptop"])

    def test_mfa_enroll_args(self) -> None:
        args = deploy.parse_args(["mfa-enroll", "ipad"])
        self.assertEqual(args.command, "mfa-enroll")
        self.assertEqual(args.rest, ["ipad"])


class MfaToggle(unittest.TestCase):
    def test_profile_off_by_default(self) -> None:
        self.assertFalse(deploy.mfa_on({}))
        self.assertFalse(deploy.mfa_on({"WG_MFA": "false"}))
        self.assertTrue(deploy.mfa_on({"WG_MFA": "true"}))


class PlaceholderHost(unittest.TestCase):
    def test_docs_ip_is_placeholder(self) -> None:
        self.assertIn("203.0.113.10", deploy.PLACEHOLDER_HOSTS)


if __name__ == "__main__":
    unittest.main()
