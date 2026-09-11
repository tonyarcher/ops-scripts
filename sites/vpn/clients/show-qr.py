#!/usr/bin/env python3
"""Show a WireGuard client.conf as a QR code for iPad and Android.

The official WireGuard app imports a QR or a .conf file. This prints an
ANSI QR when qrencode is on PATH. Without it, prints how to import the
file. Does not print the conf (it contains a private key).

Run:  python sites/vpn/deploy.py peer ipad > ipad.conf
      python sites/vpn/clients/show-qr.py ipad.conf
      python sites/vpn/clients/show-qr.py ipad.conf --png ipad.png
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

QRENCODE = "qrencode"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QR-encode a WireGuard client.conf for iPad/Android"
    )
    parser.add_argument("conf", type=Path, help="path to client.conf")
    parser.add_argument(
        "--png",
        type=Path,
        default=None,
        help="write a PNG instead of an ANSI QR on stdout",
    )
    return parser.parse_args(argv)


def require_conf(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"error: no such file {path}")
    return path


def qrencode_bin() -> str:
    found = shutil.which(QRENCODE)
    if found:
        return found
    print(
        "error: qrencode not on PATH. Import the .conf in the WireGuard app:\n"
        "  iPad:    App Store -> WireGuard -> + -> Create from file or archive\n"
        "  Android: Play Store -> WireGuard -> + -> Create from file or archive\n"
        "Install qrencode to show a QR instead (apt/brew: qrencode).",
        file=sys.stderr,
    )
    raise SystemExit(1)


def encode_ansi(qrencode: str, conf: Path) -> None:
    subprocess.run(
        [qrencode, "-t", "ANSIUTF8", "-r", str(conf)],
        check=True,
    )


def encode_png(qrencode: str, conf: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [qrencode, "-t", "PNG", "-o", str(dest), "-r", str(conf)],
        check=True,
    )
    print(f"wrote {dest}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    conf = require_conf(args.conf)
    print(
        "warning: QR encodes a private key; do not screenshot a chat", file=sys.stderr
    )
    qrencode = qrencode_bin()
    if args.png is not None:
        encode_png(qrencode, conf, args.png)
        return
    encode_ansi(qrencode, conf)


if __name__ == "__main__":
    main()
