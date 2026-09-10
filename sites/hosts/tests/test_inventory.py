#!/usr/bin/env python3
"""Offline tests for sites/hosts/inventory.py. No SSH or network."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ops_hosts", ROOT / "inventory.py")
assert _spec is not None and _spec.loader is not None
inv = importlib.util.module_from_spec(_spec)
sys.modules["ops_hosts"] = inv
_spec.loader.exec_module(inv)

EXAMPLE = ROOT / "hosts.example.json"


def write_hosts(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps({"hosts": rows}), encoding="utf-8")
    return path


def sample(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "name": "gpu-1",
        "role": "gpu",
        "ssh_user": "deploy",
        "ssh_host": "203.0.113.20",
        "ssh_port": 22,
        "gpu": True,
        "docker": True,
    }
    row.update(overrides)
    return row


class ExampleFile(unittest.TestCase):
    def test_loads_three_roles(self) -> None:
        hosts = inv.load_inventory(EXAMPLE)
        names = [h.name for h in hosts]
        self.assertEqual(names, ["vpn-gw", "gpu-1", "cad-ws"])
        by_name = {h.name: h for h in hosts}
        self.assertEqual(by_name["vpn-gw"].role, "vpn")
        self.assertFalse(by_name["vpn-gw"].gpu)
        self.assertTrue(by_name["vpn-gw"].docker)
        self.assertTrue(by_name["gpu-1"].gpu)
        self.assertTrue(by_name["gpu-1"].docker)
        self.assertEqual(by_name["cad-ws"].role, "cad")
        self.assertTrue(by_name["cad-ws"].gpu)
        self.assertFalse(by_name["cad-ws"].docker)
        self.assertEqual(by_name["vpn-gw"].vpn_ip, "10.13.13.1")

    def test_check_example(self) -> None:
        buf = StringIO()
        with redirect_stdout(buf):
            rc = inv.main(["--file", str(EXAMPLE), "check"])
        self.assertEqual(rc, 0)
        self.assertIn("ok: 3 hosts", buf.getvalue())


class ParseHost(unittest.TestCase):
    def test_rejects_bad_name(self) -> None:
        with self.assertRaises(SystemExit):
            inv.parse_host(sample(name="../root"))

    def test_rejects_unknown_role(self) -> None:
        with self.assertRaises(SystemExit):
            inv.parse_host(sample(role="swarm"))

    def test_rejects_client_role(self) -> None:
        with self.assertRaises(SystemExit):
            inv.parse_host(sample(role="client"))

    def test_rejects_unknown_key(self) -> None:
        with self.assertRaises(SystemExit):
            inv.parse_host(sample(token="secret"))

    def test_missing_name(self) -> None:
        row = sample()
        del row["name"]
        with self.assertRaises(SystemExit) as ctx:
            inv.parse_host(row)
        self.assertIn("missing name", str(ctx.exception))
        self.assertNotIn("?", str(ctx.exception))

    def test_rejects_ssh_host_spaces(self) -> None:
        with self.assertRaises(SystemExit):
            inv.parse_host(sample(ssh_host="bad host"))

    def test_rejects_ssh_user_leading_dash(self) -> None:
        with self.assertRaises(SystemExit):
            inv.parse_host(sample(ssh_user="-oProxyCommand=x"))

    def test_rejects_ssh_user_spaces(self) -> None:
        with self.assertRaises(SystemExit):
            inv.parse_host(sample(ssh_user="bad user"))

    def test_rejects_bad_vpn_ip(self) -> None:
        with self.assertRaises(SystemExit):
            inv.parse_host(sample(vpn_ip="10.13.13"))

    def test_rejects_bool_as_port(self) -> None:
        with self.assertRaises(SystemExit):
            inv.parse_host(sample(ssh_port=True))

    def test_rejects_missing_gpu(self) -> None:
        row = sample()
        del row["gpu"]
        with self.assertRaises(SystemExit):
            inv.parse_host(row)

    def test_empty_notes_ok(self) -> None:
        host = inv.parse_host(sample())
        self.assertEqual(host.notes, "")
        self.assertIsNone(host.vpn_ip)


class InventoryFile(unittest.TestCase):
    def test_duplicate_names(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = write_hosts(
                Path(raw) / "hosts.json", [sample(), sample(name="GPU-1")]
            )
            with self.assertRaises(SystemExit):
                inv.load_inventory(path)

    def test_empty_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "hosts.json"
            path.write_text('{"hosts": []}', encoding="utf-8")
            with self.assertRaises(SystemExit):
                inv.load_inventory(path)

    def test_missing_file(self) -> None:
        with self.assertRaises(SystemExit):
            inv.load_inventory(Path("/no/such/hosts.json"))


class LookupAndSsh(unittest.TestCase):
    def test_find_is_case_insensitive(self) -> None:
        hosts = inv.load_inventory(EXAMPLE)
        self.assertEqual(inv.find_host(hosts, "GPU-1").name, "gpu-1")

    def test_find_unknown(self) -> None:
        with self.assertRaises(SystemExit):
            inv.find_host(inv.load_inventory(EXAMPLE), "nope")

    def test_ssh_argv_default(self) -> None:
        host = inv.parse_host(sample())
        self.assertEqual(inv.ssh_argv(host), ["ssh", "-p", "22", "deploy@203.0.113.20"])

    def test_ssh_argv_with_key(self) -> None:
        host = inv.parse_host(sample(ssh_key="/home/deploy/.ssh/id_ed25519"))
        self.assertEqual(
            inv.ssh_argv(host),
            [
                "ssh",
                "-i",
                "/home/deploy/.ssh/id_ed25519",
                "-p",
                "22",
                "deploy@203.0.113.20",
            ],
        )


class Cli(unittest.TestCase):
    def test_show(self) -> None:
        buf = StringIO()
        with redirect_stdout(buf):
            rc = inv.main(["--file", str(EXAMPLE), "show", "cad-ws"])
        self.assertEqual(rc, 0)
        text = buf.getvalue()
        self.assertIn("role: cad", text)
        self.assertIn("docker: no", text)
        self.assertIn("gpu: yes", text)

    def test_ssh_cmd(self) -> None:
        buf = StringIO()
        with redirect_stdout(buf):
            rc = inv.main(["--file", str(EXAMPLE), "ssh-cmd", "vpn-gw"])
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().strip(), "ssh -p 22 deploy@203.0.113.10")

    def test_list_keeps_long_names(self) -> None:
        host = inv.parse_host(sample(name="gpu-workstation-1"))
        text = inv.format_list((host,))
        self.assertIn("gpu-workstation-1", text)

    def test_file_flag_skips_example_note(self) -> None:
        err = StringIO()
        out = StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = inv.main(["--file", str(EXAMPLE), "list"])
        self.assertEqual(rc, 0)
        self.assertIn("vpn-gw", out.getvalue())
        self.assertNotIn("note:", err.getvalue())

    def test_default_path_prefers_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live = Path(raw) / "hosts.json"
            live.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
            old = inv.LIVE_FILE
            inv.LIVE_FILE = live
            try:
                self.assertEqual(inv.default_path(), live)
            finally:
                inv.LIVE_FILE = old

    def test_default_file_notes_example(self) -> None:
        err = StringIO()
        out = StringIO()
        old = inv.LIVE_FILE
        inv.LIVE_FILE = Path("/no/such/hosts.json")
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = inv.main(["list"])
        finally:
            inv.LIVE_FILE = old
        self.assertEqual(rc, 0)
        self.assertIn("hosts.example.json", err.getvalue())
        self.assertIn("vpn-gw", out.getvalue())


if __name__ == "__main__":
    unittest.main()
