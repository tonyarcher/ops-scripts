"""External tool lookup (wg, iptables) and subprocess glue for sites/vpn."""

from __future__ import annotations

import shutil
import subprocess


def find_wg() -> str:
    found = shutil.which("wg")
    if found:
        return found
    raise SystemExit("wg not found on PATH (install wireguard-tools)")


def find_iptables() -> str:
    found = shutil.which("iptables")
    if found:
        return found
    raise SystemExit("iptables not found on PATH")


def find_ip6tables() -> str:
    found = shutil.which("ip6tables")
    if found:
        return found
    raise SystemExit("ip6tables not found on PATH")


def run_text(cmd: list[str], stdin: str | None = None) -> str:
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        input=stdin,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise SystemExit(f"command failed ({proc.returncode}): {cmd[0]}\n{err}")
    return proc.stdout.strip()
