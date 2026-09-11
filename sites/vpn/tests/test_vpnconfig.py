#!/usr/bin/env python3
"""Offline tests for sites/vpn/vpnconfig.py. No wg, docker, or network."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("vpnconfig", ROOT / "vpnconfig.py")
assert _spec is not None and _spec.loader is not None
vpnconfig = importlib.util.module_from_spec(_spec)
sys.modules["vpnconfig"] = vpnconfig
_spec.loader.exec_module(vpnconfig)

FAKE_PRIV = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
FAKE_PUB = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="
FAKE_PSK = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC="


def settings(**overrides: object) -> vpnconfig.Settings:
    base: dict[str, object] = {
        "server_cidr": "10.13.13.1/24",
        "listen_port": 51820,
        "endpoint": "203.0.113.10:51820",
        "full_tunnel": False,
        "client_allowed_ips": None,
        "wan_interface": "eth0",
        "peers": ("laptop", "phone"),
        "keepalive": 25,
        "config_dir": Path("/config"),
        "ssh_port": 22,
        "client_dns": None,
        "tun_if": "wg0",
        "http_port": 8080,
        "mfa": False,
        "mfa_host": "vpn.ops",
        "mfa_ttl_hours": 12,
    }
    base.update(overrides)
    return vpnconfig.Settings(**base)  # type: ignore[arg-type]


class PeerNames(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(vpnconfig.parse_peer_names(""), ())

    def test_strips_and_splits(self) -> None:
        self.assertEqual(
            vpnconfig.parse_peer_names("laptop, phone"), ("laptop", "phone")
        )

    def test_rejects_path(self) -> None:
        with self.assertRaises(SystemExit):
            vpnconfig.parse_peer_names("../root")

    def test_rejects_slash(self) -> None:
        with self.assertRaises(SystemExit):
            vpnconfig.parse_peer_names("a/b")

    def test_rejects_duplicate(self) -> None:
        with self.assertRaises(SystemExit):
            vpnconfig.parse_peer_names("laptop,Laptop")


class Addressing(unittest.TestCase):
    def test_network_and_listen(self) -> None:
        self.assertEqual(vpnconfig.network_cidr("10.13.13.1/24"), "10.13.13.0/24")
        self.assertEqual(vpnconfig.listen_addr("10.13.13.1/24"), "10.13.13.1")

    def test_peer_ips_skip_server(self) -> None:
        self.assertEqual(
            vpnconfig.peer_tunnel_address("10.13.13.1/24", 0), "10.13.13.2/32"
        )
        self.assertEqual(
            vpnconfig.peer_tunnel_address("10.13.13.1/24", 1), "10.13.13.3/32"
        )

    def test_rejects_wide_prefix(self) -> None:
        with self.assertRaises(SystemExit):
            vpnconfig.server_iface("10.0.0.1/16")

    def test_peer_overflow(self) -> None:
        with self.assertRaises(SystemExit):
            vpnconfig.peer_tunnel_address("10.13.13.1/30", 5)

    def test_ipv6_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            vpnconfig.server_iface("fd00::1/64")


class AllowedIps(unittest.TestCase):
    def test_split_default(self) -> None:
        self.assertEqual(vpnconfig.allowed_ips_for_client(settings()), "10.13.13.0/24")

    def test_full_tunnel(self) -> None:
        got = vpnconfig.allowed_ips_for_client(settings(full_tunnel=True))
        self.assertEqual(got, "0.0.0.0/0")

    def test_override_wins(self) -> None:
        got = vpnconfig.allowed_ips_for_client(
            settings(full_tunnel=True, client_allowed_ips="10.1.0.0/16")
        )
        self.assertEqual(got, "10.1.0.0/16")


class Endpoint(unittest.TestCase):
    def test_explicit_wins(self) -> None:
        env = {"WG_ENDPOINT": "vpn.example:51820", "VPN_HOST": "203.0.113.10"}
        self.assertEqual(vpnconfig.endpoint_from(env, 51820), "vpn.example:51820")

    def test_host_plus_port(self) -> None:
        self.assertEqual(
            vpnconfig.endpoint_from({"VPN_HOST": "203.0.113.10"}, 51820),
            "203.0.113.10:51820",
        )

    def test_placeholder(self) -> None:
        self.assertEqual(vpnconfig.endpoint_from({}, 51820), "replace_me:51820")


class LoadSettings(unittest.TestCase):
    def test_defaults(self) -> None:
        got = vpnconfig.load_settings({}, Path("/config"))
        self.assertEqual(got.server_cidr, "10.13.13.1/24")
        self.assertEqual(got.listen_port, 51820)
        self.assertFalse(got.full_tunnel)
        self.assertEqual(got.peers, ())

    def test_peers_and_tunnel(self) -> None:
        env = {
            "WG_PEERS": "laptop,phone",
            "WG_FULL_TUNNEL": "true",
            "VPN_HOST": "203.0.113.10",
        }
        got = vpnconfig.load_settings(env, Path("/config"))
        self.assertEqual(got.peers, ("laptop", "phone"))
        self.assertTrue(got.full_tunnel)
        self.assertEqual(got.endpoint, "203.0.113.10:51820")

    def test_bad_port(self) -> None:
        with self.assertRaises(SystemExit):
            vpnconfig.load_settings({"WG_LISTEN_PORT": "99999"}, Path("/config"))


class Render(unittest.TestCase):
    def test_server_conf_has_listen_and_peer(self) -> None:
        block = vpnconfig.peer_stanza(FAKE_PUB, FAKE_PSK, "10.13.13.2/32")
        body = vpnconfig.server_conf(settings(), FAKE_PRIV, (block,))
        self.assertIn("ListenPort = 51820", body)
        self.assertIn("Address = 10.13.13.1/24", body)
        self.assertIn("AllowedIPs = 10.13.13.2/32", body)
        self.assertIn(FAKE_PRIV, body)

    def test_client_split_has_no_full_route(self) -> None:
        body = vpnconfig.client_conf(
            private=FAKE_PRIV,
            address="10.13.13.2/32",
            server_public=FAKE_PUB,
            psk=FAKE_PSK,
            settings=settings(),
        )
        self.assertIn("Endpoint = 203.0.113.10:51820", body)
        self.assertIn("AllowedIPs = 10.13.13.0/24", body)
        self.assertNotIn("0.0.0.0/0", body)
        self.assertNotIn("DNS =", body)

    def test_client_full_tunnel_dns(self) -> None:
        body = vpnconfig.client_conf(
            private=FAKE_PRIV,
            address="10.13.13.2/32",
            server_public=FAKE_PUB,
            psk=FAKE_PSK,
            settings=settings(full_tunnel=True),
        )
        self.assertIn("AllowedIPs = 0.0.0.0/0", body)
        self.assertIn("DNS = 1.1.1.1", body)

    def test_client_mfa_sets_tunnel_dns(self) -> None:
        body = vpnconfig.client_conf(
            private=FAKE_PRIV,
            address="10.13.13.2/32",
            server_public=FAKE_PUB,
            psk=FAKE_PSK,
            settings=settings(mfa=True),
        )
        self.assertIn("DNS = 10.13.13.1", body)


class MfaEnroll(unittest.TestCase):
    def test_writes_secret_once(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cfg = settings(config_dir=Path(raw))
            buf = StringIO()
            with redirect_stdout(buf):
                vpnconfig.cmd_mfa_enroll(cfg, "ipad", force=False)
            path = vpnconfig.totp_secret_path(cfg, "ipad")
            self.assertTrue(path.is_file())
            self.assertIn("otpauth://totp/", buf.getvalue())
            first = path.read_text(encoding="utf-8")
            with self.assertRaises(SystemExit):
                vpnconfig.cmd_mfa_enroll(cfg, "ipad", force=False)
            with redirect_stdout(StringIO()):
                vpnconfig.cmd_mfa_enroll(cfg, "ipad", force=True)
            self.assertNotEqual(first, path.read_text(encoding="utf-8"))


class Iptables(unittest.TestCase):
    def test_ssh_lock_covers_vpn_and_drop(self) -> None:
        lines = vpnconfig.ssh_lock_commands(settings())
        joined = "\n".join(lines)
        self.assertIn("-s 10.13.13.0/24", joined)
        self.assertIn("--dport 22", joined)
        self.assertIn("-j DROP", joined)
        self.assertIn("ESTABLISHED,RELATED", joined)
        self.assertNotIn("51820", joined)
        self.assertIn("ip6tables -A INPUT -p tcp --dport 22 -j DROP", joined)
        self.assertNotIn("ip6tables -I INPUT -p tcp --dport 22 -s", joined)

    def test_nat_has_masquerade(self) -> None:
        lines = vpnconfig.nat_up_commands(settings())
        joined = "\n".join(lines)
        self.assertIn("-t nat", joined)
        self.assertIn("MASQUERADE", joined)
        self.assertIn("-s 10.13.13.0/24", joined)
        self.assertIn("-i wg0", joined)

    def test_nat_requires_wan(self) -> None:
        with self.assertRaises(SystemExit):
            vpnconfig.nat_up_commands(settings(wan_interface=""))


class CheckOutput(unittest.TestCase):
    def test_summary_has_no_keys(self) -> None:
        text = "\n".join(vpnconfig.summary_lines(settings()))
        self.assertNotIn("PrivateKey", text)
        self.assertNotIn(FAKE_PRIV, text)
        self.assertIn("203.0.113.10:51820", text)
        self.assertIn("laptop, phone", text)


class PrintClient(unittest.TestCase):
    def test_missing_peer(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cfg = settings(config_dir=Path(raw), peers=("laptop",))
            with self.assertRaises(SystemExit):
                vpnconfig.cmd_print_client(cfg, "laptop")

    def test_rejects_bad_name(self) -> None:
        with self.assertRaises(SystemExit):
            vpnconfig.cmd_print_client(settings(), "../etc")

    def test_writes_conf_to_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            peer = root / "peers" / "laptop"
            peer.mkdir(parents=True)
            (peer / "client.conf").write_text("PrivateKey = secret\n", encoding="utf-8")
            cfg = settings(config_dir=root, peers=("laptop",))
            buf = StringIO()
            with redirect_stdout(buf):
                vpnconfig.cmd_print_client(cfg, "laptop")
            self.assertIn("PrivateKey = secret", buf.getvalue())


class WriteSecret(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "private.key"
            vpnconfig.write_secret(path, "hello")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello\n")
            if os.name != "nt":
                self.assertEqual(stat_mode(path) & 0o777, 0o600)


def stat_mode(path: Path) -> int:
    return path.stat().st_mode


class MainHelp(unittest.TestCase):
    def test_help_exits_zero(self) -> None:
        buf = StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit) as raised:
            vpnconfig.main(["--help"])
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
