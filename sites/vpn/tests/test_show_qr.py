#!/usr/bin/env python3
"""Offline tests for sites/vpn/clients/show-qr.py. No qrencode required."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "show_qr", ROOT / "clients" / "show-qr.py"
)
assert _spec is not None and _spec.loader is not None
show_qr = importlib.util.module_from_spec(_spec)
sys.modules["show_qr"] = show_qr
_spec.loader.exec_module(show_qr)

SECRET = "PrivateKey = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n"


class RequireConf(unittest.TestCase):
    def test_missing_file(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            show_qr.require_conf(Path("no-such-peer.conf"))
        self.assertIn("no such file", str(ctx.exception))

    def test_ok(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "ipad.conf"
            path.write_text(SECRET, encoding="utf-8")
            self.assertEqual(show_qr.require_conf(path), path)


class QrencodeBin(unittest.TestCase):
    def test_missing_does_not_print_key(self) -> None:
        with (
            patch.object(show_qr.shutil, "which", return_value=None),
            self.assertRaises(SystemExit) as ctx,
        ):
            show_qr.qrencode_bin()
        self.assertEqual(ctx.exception.code, 1)

    def test_found(self) -> None:
        with patch.object(show_qr.shutil, "which", return_value="/usr/bin/qrencode"):
            self.assertEqual(show_qr.qrencode_bin(), "/usr/bin/qrencode")


class Encode(unittest.TestCase):
    def test_ansi_argv(self) -> None:
        conf = Path("ipad.conf")
        with patch.object(show_qr.subprocess, "run") as run:
            show_qr.encode_ansi("/usr/bin/qrencode", conf)
        run.assert_called_once_with(
            ["/usr/bin/qrencode", "-t", "ANSIUTF8", "-r", "ipad.conf"],
            check=True,
        )

    def test_png_argv(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw) / "out" / "ipad.png"
            with patch.object(show_qr.subprocess, "run") as run:
                show_qr.encode_png("/usr/bin/qrencode", Path("ipad.conf"), dest)
            self.assertTrue(dest.parent.is_dir())
        run.assert_called_once_with(
            [
                "/usr/bin/qrencode",
                "-t",
                "PNG",
                "-o",
                str(dest),
                "-r",
                "ipad.conf",
            ],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
