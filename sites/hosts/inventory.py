#!/usr/bin/env python3
"""Named SSH/Docker hosts for this ops toolbox.

VPN and Compose stay the runtimes. This list is the missing layer (vpn-gw,
gpu-1, cad-ws). Copy hosts.example.json to hosts.json and edit. Never commit
hosts.json. Documentation IPs only in the example (203.0.113.0/24).

Run:  python sites/hosts/inventory.py list
      python sites/hosts/inventory.py show gpu-1
      python sites/hosts/inventory.py ssh-cmd gpu-1
      python sites/hosts/inventory.py check

A Mac is a VPN/dev client (macos/), not a CUDA host. Do not add one here.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shlex
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE_FILE = HERE / "hosts.example.json"
LIVE_FILE = HERE / "hosts.json"
NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
ROLES = frozenset({"vpn", "gpu", "llm", "cad"})
KNOWN_KEYS = frozenset(
    {
        "name",
        "role",
        "ssh_user",
        "ssh_host",
        "ssh_port",
        "ssh_key",
        "vpn_ip",
        "gpu",
        "docker",
        "notes",
    }
)


@dataclass(frozen=True)
class Host:
    name: str
    role: str
    ssh_user: str
    ssh_host: str
    ssh_port: int
    ssh_key: str | None
    vpn_ip: str | None
    gpu: bool
    docker: bool
    notes: str


def default_path() -> Path:
    if LIVE_FILE.is_file():
        return LIVE_FILE
    return EXAMPLE_FILE


def require_str(row: Mapping[str, object], key: str, *, label: str) -> str:
    val = row.get(key)
    if not isinstance(val, str) or not val.strip():
        raise SystemExit(f"error: host {label} missing {key}")
    return val.strip()


def optional_str(row: Mapping[str, object], key: str) -> str | None:
    val = row.get(key)
    if val is None:
        return None
    if not isinstance(val, str):
        raise SystemExit(f"error: {key} must be a string")
    stripped = val.strip()
    return stripped or None


def require_bool(row: Mapping[str, object], key: str, *, label: str) -> bool:
    val = row.get(key)
    if not isinstance(val, bool):
        raise SystemExit(f"error: host {label} {key} must be true or false")
    return val


def parse_port(row: Mapping[str, object], *, label: str) -> int:
    val = row.get("ssh_port", 22)
    if isinstance(val, bool) or not isinstance(val, int):
        raise SystemExit(f"error: host {label} ssh_port must be an integer")
    if val < 1 or val > 65535:
        raise SystemExit(f"error: host {label} ssh_port out of range")
    return val


def parse_vpn_ip(raw: str | None, *, label: str) -> str | None:
    if raw is None:
        return None
    try:
        return str(ipaddress.IPv4Address(raw))
    except ValueError as exc:
        raise SystemExit(f"error: host {label} vpn_ip is not an IPv4 address") from exc


def parse_name(raw: str) -> str:
    if not NAME_RE.match(raw):
        raise SystemExit(f"error: invalid host name {raw!r}")
    return raw


def parse_role(raw: str, *, label: str) -> str:
    if raw not in ROLES:
        known = ", ".join(sorted(ROLES))
        raise SystemExit(f"error: host {label} role {raw!r} not in {known}")
    return raw


def parse_ssh_token(raw: str, *, field: str, label: str) -> str:
    if any(ch.isspace() for ch in raw) or raw.startswith("-"):
        raise SystemExit(f"error: host {label} {field} is not a valid ssh token")
    return raw


def parse_host_name(data: Mapping[str, object]) -> str:
    raw = optional_str(data, "name")
    if raw is None:
        raise SystemExit("error: host missing name")
    return parse_name(raw)


def parse_host(row: object) -> Host:
    if not isinstance(row, dict):
        raise SystemExit("error: each host must be a JSON object")
    data: dict[str, object] = row
    extra = set(data) - KNOWN_KEYS
    if extra:
        raise SystemExit(f"error: unknown host keys: {', '.join(sorted(extra))}")
    name = parse_host_name(data)
    role = parse_role(require_str(data, "role", label=name), label=name)
    ssh_user = parse_ssh_token(
        require_str(data, "ssh_user", label=name), field="ssh_user", label=name
    )
    ssh_host = parse_ssh_token(
        require_str(data, "ssh_host", label=name), field="ssh_host", label=name
    )
    return Host(
        name=name,
        role=role,
        ssh_user=ssh_user,
        ssh_host=ssh_host,
        ssh_port=parse_port(data, label=name),
        ssh_key=optional_str(data, "ssh_key"),
        vpn_ip=parse_vpn_ip(optional_str(data, "vpn_ip"), label=name),
        gpu=require_bool(data, "gpu", label=name),
        docker=require_bool(data, "docker", label=name),
        notes=optional_str(data, "notes") or "",
    )


def load_rows(path: Path) -> list[object]:
    if not path.is_file():
        raise SystemExit(f"error: no inventory file {path}")
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: {path} is not JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SystemExit(f"error: {path} must be a JSON object")
    rows = raw.get("hosts")
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"error: {path} needs a non-empty hosts array")
    return rows


def load_inventory(path: Path) -> tuple[Host, ...]:
    hosts = tuple(parse_host(row) for row in load_rows(path))
    seen: set[str] = set()
    for host in hosts:
        key = host.name.lower()
        if key in seen:
            raise SystemExit(f"error: duplicate host name {host.name!r}")
        seen.add(key)
    return hosts


def find_host(hosts: Sequence[Host], name: str) -> Host:
    for host in hosts:
        if host.name.lower() == name.lower():
            return host
    known = ", ".join(h.name for h in hosts)
    raise SystemExit(f"error: unknown host {name!r}. known: {known}")


def ssh_argv(host: Host) -> list[str]:
    cmd = ["ssh"]
    if host.ssh_key:
        cmd.extend(["-i", host.ssh_key])
    cmd.extend(["-p", str(host.ssh_port), f"{host.ssh_user}@{host.ssh_host}"])
    return cmd


def _width(header: str, values: Sequence[str]) -> int:
    return max(len(header), max((len(v) for v in values), default=0))


def format_list(hosts: Sequence[Host]) -> str:
    names = [h.name for h in hosts]
    roles = [h.role for h in hosts]
    sshs = [f"{h.ssh_user}@{h.ssh_host}:{h.ssh_port}" for h in hosts]
    vpns = [h.vpn_ip or "-" for h in hosts]
    nw = _width("NAME", names)
    rw = _width("ROLE", roles)
    sw = _width("SSH", sshs)
    vw = _width("VPN_IP", vpns)
    header = f"{'NAME':<{nw}} {'ROLE':<{rw}} {'SSH':<{sw}} {'VPN_IP':<{vw}} GPU  DOCKER"
    lines = [header]
    for i, host in enumerate(hosts):
        gpu = "yes" if host.gpu else "no"
        docker = "yes" if host.docker else "no"
        lines.append(
            f"{names[i]:<{nw}} {roles[i]:<{rw}} {sshs[i]:<{sw}} {vpns[i]:<{vw}} "
            f"{gpu:<3}  {docker}"
        )
    return "\n".join(lines)


def format_show(host: Host) -> str:
    lines = [
        f"name: {host.name}",
        f"role: {host.role}",
        f"ssh: {host.ssh_user}@{host.ssh_host}:{host.ssh_port}",
        f"vpn_ip: {host.vpn_ip or '-'}",
        f"gpu: {'yes' if host.gpu else 'no'}",
        f"docker: {'yes' if host.docker else 'no'}",
    ]
    if host.ssh_key:
        lines.append(f"ssh_key: {host.ssh_key}")
    if host.notes:
        lines.append(f"notes: {host.notes}")
    return "\n".join(lines)


def cmd_list(path: Path) -> int:
    print(format_list(load_inventory(path)))
    return 0


def cmd_show(path: Path, name: str) -> int:
    print(format_show(find_host(load_inventory(path), name)))
    return 0


def cmd_ssh_cmd(path: Path, name: str) -> int:
    print(shlex.join(ssh_argv(find_host(load_inventory(path), name))))
    return 0


def cmd_check(path: Path) -> int:
    hosts = load_inventory(path)
    print(f"ok: {len(hosts)} hosts ({path})")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="inventory JSON (default: hosts.json if present, else example)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="table of hosts")
    sub.add_parser("check", help="validate the file")
    show = sub.add_parser("show", help="one host")
    show.add_argument("name")
    ssh = sub.add_parser("ssh-cmd", help="print an ssh argv line")
    ssh.add_argument("name")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = args.file if args.file is not None else default_path()
    if args.file is None and path == EXAMPLE_FILE:
        print(f"note: using {path} — copy to {LIVE_FILE} and edit", file=sys.stderr)
    if args.command == "list":
        return cmd_list(path)
    if args.command == "show":
        return cmd_show(path, args.name)
    if args.command == "ssh-cmd":
        return cmd_ssh_cmd(path, args.name)
    return cmd_check(path)


if __name__ == "__main__":
    raise SystemExit(main())
