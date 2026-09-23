#!/usr/bin/env python3
"""WireGuard configs, NAT, and SSH-lock rules for sites/vpn.

Renders wg0 + client .conf files. Keys are created with `wg` inside the
container and never printed. lock-ssh is dry-run unless --yes (can cut
public SSH; keep a console session).

Run:  python sites/vpn/vpnconfig.py check
      python sites/vpn/vpnconfig.py render --config-dir /config
      python sites/vpn/vpnconfig.py print-client --name laptop
      python sites/vpn/vpnconfig.py mfa-enroll --name ipad
      python sites/vpn/vpnconfig.py lock-ssh
      python sites/vpn/vpnconfig.py lock-ssh --yes  # also drops IPv6 SSH

Env: VPN_HOST, WG_SERVER_ADDRESS, WG_LISTEN_PORT, WG_PEERS, WG_FULL_TUNNEL,
     WG_ENDPOINT, WG_WAN_INTERFACE, WG_CLIENT_ALLOWED_IPS, WG_CLIENT_DNS,
     HOST_SSH_PORT, WG_MFA, WG_MFA_HOST. See .env.example.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vpnconfig_exec import find_ip6tables, find_iptables, find_wg, run_text
from vpnconfig_firewall import (
    apply_nat,
    apply_ssh_lock,
    apply_ssh_lock_v6,
    format_iptables,
    format_xtables,
    forward_in_spec,
    forward_out_spec,
    iptables_apply,
    iptables_has,
    iptables_remove,
    nat_masquerade_spec,
    nat_up_commands,
    ssh_allow_established_spec,
    ssh_allow_vpn_spec,
    ssh_drop_spec,
    ssh_lock_commands,
)
from vpnconfig_keys import (
    derive_public_key,
    ensure_keypair,
    ensure_psk,
    gen_preshared_key,
    gen_private_key,
    new_totp_secret,
    otpauth_uri,
    read_trimmed,
    totp_secret_path,
    write_public,
    write_secret,
)
from vpnconfig_render import (
    client_conf,
    client_dns_line,
    interface_stanza,
    peer_stanza,
    server_conf,
    summary_lines,
)
from vpnconfig_settings import (
    DEFAULT_CIDR,
    DEFAULT_PORT,
    DEFAULT_TUN,
    MAX_PREFIX_HOSTS,
    PEER_NAME_RE,
    TRUE_VALUES,
    Settings,
    allowed_ips_for_client,
    config_dir_from,
    endpoint_from,
    env_bool,
    env_int,
    listen_addr,
    load_settings,
    network_cidr,
    parse_peer_names,
    peer_tunnel_address,
    server_iface,
)

__all__ = [
    "DEFAULT_CIDR",
    "DEFAULT_PORT",
    "DEFAULT_TUN",
    "MAX_PREFIX_HOSTS",
    "PEER_NAME_RE",
    "TRUE_VALUES",
    "Settings",
    "allowed_ips_for_client",
    "apply_nat",
    "apply_ssh_lock",
    "apply_ssh_lock_v6",
    "build_parser",
    "client_conf",
    "client_dns_line",
    "cmd_check",
    "cmd_lock_ssh",
    "cmd_mfa_enroll",
    "cmd_nat",
    "cmd_peers",
    "cmd_print_client",
    "cmd_render",
    "config_dir_from",
    "derive_public_key",
    "dispatch",
    "endpoint_from",
    "ensure_keypair",
    "ensure_psk",
    "env_bool",
    "env_int",
    "find_ip6tables",
    "find_iptables",
    "find_wg",
    "format_iptables",
    "format_xtables",
    "forward_in_spec",
    "forward_out_spec",
    "gen_preshared_key",
    "gen_private_key",
    "interface_stanza",
    "iptables_apply",
    "iptables_has",
    "iptables_remove",
    "listen_addr",
    "load_settings",
    "main",
    "nat_masquerade_spec",
    "nat_up_commands",
    "network_cidr",
    "new_totp_secret",
    "otpauth_uri",
    "parse_peer_names",
    "peer_stanza",
    "peer_tunnel_address",
    "read_trimmed",
    "run_text",
    "server_conf",
    "server_iface",
    "ssh_allow_established_spec",
    "ssh_allow_vpn_spec",
    "ssh_drop_spec",
    "ssh_lock_commands",
    "summary_lines",
    "totp_secret_path",
    "write_peer_files",
    "write_public",
    "write_secret",
]


def write_peer_files(
    settings: Settings,
    wg: str,
    name: str,
    index: int,
    server_public: str,
) -> str:
    peer_dir = settings.config_dir / "peers" / name
    _private, public = ensure_keypair(peer_dir, wg)
    psk = ensure_psk(peer_dir / "preshared.key", wg)
    address = peer_tunnel_address(settings.server_cidr, index)
    body = client_conf(
        private=_private,
        address=address,
        server_public=server_public,
        psk=psk,
        settings=settings,
    )
    write_secret(peer_dir / "client.conf", body)
    return peer_stanza(public, psk, address)


def cmd_render(settings: Settings) -> None:
    wg = find_wg()
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    server_dir = settings.config_dir / "server"
    private, public = ensure_keypair(server_dir, wg)
    blocks: list[str] = []
    for index, name in enumerate(settings.peers):
        blocks.append(write_peer_files(settings, wg, name, index, public))
    body = server_conf(settings, private, tuple(blocks))
    write_secret(settings.config_dir / f"{settings.tun_if}.conf", body)
    print(f"wrote {settings.tun_if}.conf and {len(settings.peers)} client profile(s)")


def cmd_check(settings: Settings) -> None:
    for line in summary_lines(settings):
        print(line)


def cmd_peers(settings: Settings) -> None:
    if not settings.peers:
        print("(none)")
        return
    for index, name in enumerate(settings.peers):
        print(f"{name} {peer_tunnel_address(settings.server_cidr, index)}")


def cmd_mfa_enroll(settings: Settings, name: str, force: bool) -> None:
    if not PEER_NAME_RE.match(name):
        raise SystemExit(f"invalid peer name {name!r}")
    path = totp_secret_path(settings, name)
    if path.is_file() and not force:
        raise SystemExit(f"already enrolled {name} (pass --force to rotate)")
    secret = new_totp_secret()
    write_secret(path, secret)
    print(
        "warning: this URI is a second factor secret; do not commit it", file=sys.stderr
    )
    print(otpauth_uri(name, secret))


def cmd_print_client(settings: Settings, name: str) -> None:
    if not PEER_NAME_RE.match(name):
        raise SystemExit(f"invalid peer name {name!r}")
    path = settings.config_dir / "peers" / name / "client.conf"
    if not path.is_file():
        raise SystemExit(f"no client conf for {name} at {path}")
    print("warning: client.conf contains a private key", file=sys.stderr)
    sys.stdout.write(path.read_text(encoding="utf-8"))


def cmd_lock_ssh(settings: Settings, apply: bool) -> None:
    for line in ssh_lock_commands(settings):
        print(line)
    if not apply:
        print("dry-run: pass --yes to apply (can cut public SSH)", file=sys.stderr)
        return
    apply_ssh_lock(settings)
    print("applied SSH lock (existing sessions stay up until they reconnect)")


def cmd_nat(settings: Settings, up: bool) -> None:
    apply_nat(settings, up=up)
    print("nat-up" if up else "nat-down")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="WireGuard config helper for sites/vpn"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    render = sub.add_parser("render", help="write server + client confs (needs wg)")
    render.add_argument("--config-dir", type=Path, default=None)
    check = sub.add_parser("check", help="print non-secret settings")
    check.add_argument("--config-dir", type=Path, default=None)
    peers = sub.add_parser("peers", help="list peer names and tunnel IPs")
    peers.add_argument("--config-dir", type=Path, default=None)
    show = sub.add_parser("print-client", help="write one client.conf to stdout")
    show.add_argument("--name", required=True)
    show.add_argument("--config-dir", type=Path, default=None)
    lock = sub.add_parser("lock-ssh", help="restrict host SSH to the VPN subnet")
    lock.add_argument("--yes", action="store_true")
    lock.add_argument("--config-dir", type=Path, default=None)
    nat_up = sub.add_parser("nat-up", help="install MASQUERADE/FORWARD rules")
    nat_up.add_argument("--config-dir", type=Path, default=None)
    nat_down = sub.add_parser("nat-down", help="remove MASQUERADE/FORWARD rules")
    nat_down.add_argument("--config-dir", type=Path, default=None)
    enroll = sub.add_parser("mfa-enroll", help="create a TOTP secret for one peer")
    enroll.add_argument("--name", required=True)
    enroll.add_argument("--force", action="store_true")
    enroll.add_argument("--config-dir", type=Path, default=None)
    return parser


def dispatch(args: argparse.Namespace, settings: Settings) -> None:
    if args.cmd == "render":
        cmd_render(settings)
        return
    if args.cmd == "check":
        cmd_check(settings)
        return
    if args.cmd == "peers":
        cmd_peers(settings)
        return
    if args.cmd == "print-client":
        cmd_print_client(settings, args.name)
        return
    if args.cmd == "lock-ssh":
        cmd_lock_ssh(settings, apply=args.yes)
        return
    if args.cmd == "nat-up":
        cmd_nat(settings, up=True)
        return
    if args.cmd == "nat-down":
        cmd_nat(settings, up=False)
        return
    if args.cmd == "mfa-enroll":
        cmd_mfa_enroll(settings, args.name, force=args.force)
        return
    raise SystemExit(f"unknown command {args.cmd}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    directory = config_dir_from(os.environ, getattr(args, "config_dir", None))
    settings = load_settings(os.environ, directory)
    dispatch(args, settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
