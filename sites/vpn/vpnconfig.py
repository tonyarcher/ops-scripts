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
import base64
import ipaddress
import os
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PEER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
DEFAULT_CIDR = "10.13.13.1/24"
DEFAULT_PORT = 51820
DEFAULT_TUN = "wg0"
MAX_PREFIX_HOSTS = 256


@dataclass(frozen=True)
class Settings:
    server_cidr: str
    listen_port: int
    endpoint: str
    full_tunnel: bool
    client_allowed_ips: str | None
    wan_interface: str
    peers: tuple[str, ...]
    keepalive: int
    config_dir: Path
    ssh_port: int
    client_dns: str | None
    tun_if: str
    http_port: int
    mfa: bool
    mfa_host: str
    mfa_ttl_hours: int


def env_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in TRUE_VALUES


def env_int(raw: str | None, default: int) -> int:
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip(), 10)
    except ValueError as exc:
        raise SystemExit(f"not an integer: {raw!r}") from exc
    return value


def parse_peer_names(raw: str) -> tuple[str, ...]:
    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    seen: set[str] = set()
    for name in names:
        if not PEER_NAME_RE.match(name):
            raise SystemExit(f"invalid peer name {name!r}")
        key = name.lower()
        if key in seen:
            raise SystemExit(f"duplicate peer name {name!r}")
        seen.add(key)
    return names


def server_iface(cidr: str) -> ipaddress.IPv4Interface:
    try:
        iface = ipaddress.ip_interface(cidr)
    except ValueError as exc:
        raise SystemExit(f"WG_SERVER_ADDRESS must be IPv4 CIDR: {cidr!r}") from exc
    if not isinstance(iface, ipaddress.IPv4Interface):
        raise SystemExit("WG_SERVER_ADDRESS must be IPv4 CIDR")
    if iface.network.num_addresses > MAX_PREFIX_HOSTS:
        raise SystemExit("WG_SERVER_ADDRESS prefix must be /24 or longer")
    return iface


def network_cidr(cidr: str) -> str:
    return str(server_iface(cidr).network)


def listen_addr(cidr: str) -> str:
    return str(server_iface(cidr).ip)


def peer_tunnel_address(cidr: str, index: int) -> str:
    iface = server_iface(cidr)
    usable = [host for host in iface.network.hosts() if host != iface.ip]
    if index < 0 or index >= len(usable):
        raise SystemExit(f"peer index {index} exceeds subnet {iface.network}")
    return f"{usable[index]}/32"


def allowed_ips_for_client(settings: Settings) -> str:
    if settings.client_allowed_ips:
        return settings.client_allowed_ips
    if settings.full_tunnel:
        return "0.0.0.0/0"
    return network_cidr(settings.server_cidr)


def endpoint_from(env: Mapping[str, str], port: int) -> str:
    explicit = env.get("WG_ENDPOINT", "").strip()
    if explicit:
        return explicit
    host = env.get("VPN_HOST", "").strip()
    if not host:
        return f"replace_me:{port}"
    if ":" in host:
        return host
    return f"{host}:{port}"


def load_settings(env: Mapping[str, str], config_dir: Path) -> Settings:
    cidr = env.get("WG_SERVER_ADDRESS", "").strip() or DEFAULT_CIDR
    server_iface(cidr)
    port = env_int(env.get("WG_LISTEN_PORT"), DEFAULT_PORT)
    if port < 1 or port > 65535:
        raise SystemExit("WG_LISTEN_PORT must be 1-65535")
    ssh_port = env_int(env.get("HOST_SSH_PORT"), 22)
    http_port = env_int(env.get("WG_HTTP_PORT"), 8080)
    keepalive = env_int(env.get("WG_PERSISTENT_KEEPALIVE"), 25)
    dns = env.get("WG_CLIENT_DNS", "").strip() or None
    extra_ips = env.get("WG_CLIENT_ALLOWED_IPS", "").strip() or None
    return Settings(
        server_cidr=cidr,
        listen_port=port,
        endpoint=endpoint_from(env, port),
        full_tunnel=env_bool(env.get("WG_FULL_TUNNEL"), False),
        client_allowed_ips=extra_ips,
        wan_interface=env.get("WG_WAN_INTERFACE", "").strip(),
        peers=parse_peer_names(env.get("WG_PEERS", "")),
        keepalive=keepalive,
        config_dir=config_dir,
        ssh_port=ssh_port,
        client_dns=dns,
        tun_if=env.get("WG_TUN_IF", "").strip() or DEFAULT_TUN,
        http_port=http_port,
        mfa=env_bool(env.get("WG_MFA"), False),
        mfa_host=env.get("WG_MFA_HOST", "").strip() or "vpn.ops",
        mfa_ttl_hours=max(1, env_int(env.get("WG_MFA_TTL_HOURS"), 12)),
    )


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


def gen_private_key(wg: str) -> str:
    return run_text([wg, "genkey"])


def derive_public_key(wg: str, private: str) -> str:
    return run_text([wg, "pubkey"], stdin=private + "\n")


def gen_preshared_key(wg: str) -> str:
    return run_text([wg, "genpsk"])


def write_secret(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = body if body.endswith("\n") else body + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def write_public(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = body if body.endswith("\n") else body + "\n"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o644)


def read_trimmed(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def ensure_keypair(directory: Path, wg: str) -> tuple[str, str]:
    priv_path = directory / "private.key"
    pub_path = directory / "public.key"
    if priv_path.exists():
        private = read_trimmed(priv_path)
        if pub_path.exists():
            return private, read_trimmed(pub_path)
        public = derive_public_key(wg, private)
        write_public(pub_path, public)
        return private, public
    private = gen_private_key(wg)
    public = derive_public_key(wg, private)
    write_secret(priv_path, private)
    write_public(pub_path, public)
    return private, public


def ensure_psk(path: Path, wg: str) -> str:
    if path.exists():
        return read_trimmed(path)
    secret = gen_preshared_key(wg)
    write_secret(path, secret)
    return secret


def interface_stanza(settings: Settings, private: str) -> str:
    return (
        "[Interface]\n"
        f"Address = {settings.server_cidr}\n"
        f"ListenPort = {settings.listen_port}\n"
        f"PrivateKey = {private}\n"
    )


def peer_stanza(public: str, psk: str, allowed: str) -> str:
    return (
        "\n[Peer]\n"
        f"PublicKey = {public}\n"
        f"PresharedKey = {psk}\n"
        f"AllowedIPs = {allowed}\n"
    )


def client_dns_line(settings: Settings) -> str | None:
    if settings.client_dns:
        return f"DNS = {settings.client_dns}"
    if settings.mfa:
        return f"DNS = {listen_addr(settings.server_cidr)}"
    if settings.full_tunnel:
        return "DNS = 1.1.1.1"
    return None


def client_conf(
    *,
    private: str,
    address: str,
    server_public: str,
    psk: str,
    settings: Settings,
) -> str:
    lines = ["[Interface]", f"PrivateKey = {private}", f"Address = {address}"]
    dns = client_dns_line(settings)
    if dns:
        lines.append(dns)
    lines.extend(
        [
            "",
            "[Peer]",
            f"PublicKey = {server_public}",
            f"PresharedKey = {psk}",
            f"Endpoint = {settings.endpoint}",
            f"AllowedIPs = {allowed_ips_for_client(settings)}",
            f"PersistentKeepalive = {settings.keepalive}",
            "",
        ]
    )
    return "\n".join(lines)


def server_conf(settings: Settings, private: str, peer_blocks: tuple[str, ...]) -> str:
    return interface_stanza(settings, private) + "".join(peer_blocks)


def summary_lines(settings: Settings) -> list[str]:
    return [
        f"server: {settings.server_cidr}",
        f"listen: {listen_addr(settings.server_cidr)}:{settings.listen_port}",
        f"endpoint: {settings.endpoint}",
        f"full_tunnel: {str(settings.full_tunnel).lower()}",
        f"client_allowed_ips: {allowed_ips_for_client(settings)}",
        f"peers: {', '.join(settings.peers) if settings.peers else '(none)'}",
        f"tun: {settings.tun_if}",
        f"http: {listen_addr(settings.server_cidr)}:{settings.http_port}",
        f"ssh_port: {settings.ssh_port}",
        f"wan: {settings.wan_interface or '(detect at start)'}",
        f"mfa: {'on' if settings.mfa else 'off'}",
        f"mfa_host: {settings.mfa_host}",
        f"mfa_ttl_hours: {settings.mfa_ttl_hours}",
    ]


def nat_masquerade_spec(network: str, wan: str) -> tuple[str, ...]:
    return ("POSTROUTING", "-s", network, "-o", wan, "-j", "MASQUERADE")


def forward_in_spec(tun_if: str) -> tuple[str, ...]:
    return ("FORWARD", "-i", tun_if, "-j", "ACCEPT")


def forward_out_spec(tun_if: str) -> tuple[str, ...]:
    return ("FORWARD", "-o", tun_if, "-j", "ACCEPT")


def ssh_allow_vpn_spec(network: str, port: int) -> tuple[str, ...]:
    return (
        "INPUT",
        "-p",
        "tcp",
        "--dport",
        str(port),
        "-s",
        network,
        "-j",
        "ACCEPT",
    )


def ssh_allow_established_spec(port: int) -> tuple[str, ...]:
    return (
        "INPUT",
        "-p",
        "tcp",
        "--dport",
        str(port),
        "-m",
        "conntrack",
        "--ctstate",
        "ESTABLISHED,RELATED",
        "-j",
        "ACCEPT",
    )


def ssh_drop_spec(port: int) -> tuple[str, ...]:
    return ("INPUT", "-p", "tcp", "--dport", str(port), "-j", "DROP")


def format_xtables(
    binary: str,
    table: str | None,
    action: str,
    spec: tuple[str, ...],
) -> str:
    parts = [binary]
    if table:
        parts.extend(["-t", table])
    parts.append(action)
    parts.extend(spec)
    return " ".join(parts)


def format_iptables(table: str | None, action: str, spec: tuple[str, ...]) -> str:
    return format_xtables("iptables", table, action, spec)


def ssh_lock_commands(settings: Settings) -> list[str]:
    network = network_cidr(settings.server_cidr)
    port = settings.ssh_port
    return [
        format_iptables(None, "-I", ssh_allow_established_spec(port)),
        format_iptables(None, "-I", ssh_allow_vpn_spec(network, port)),
        format_iptables(None, "-A", ssh_drop_spec(port)),
        format_xtables("ip6tables", None, "-I", ssh_allow_established_spec(port)),
        format_xtables("ip6tables", None, "-A", ssh_drop_spec(port)),
    ]


def nat_up_commands(settings: Settings) -> list[str]:
    if not settings.wan_interface:
        raise SystemExit(
            "WG_WAN_INTERFACE is empty (set it or let the entrypoint detect)"
        )
    network = network_cidr(settings.server_cidr)
    return [
        format_iptables(
            "nat", "-A", nat_masquerade_spec(network, settings.wan_interface)
        ),
        format_iptables(None, "-A", forward_in_spec(settings.tun_if)),
        format_iptables(None, "-A", forward_out_spec(settings.tun_if)),
    ]


def iptables_has(bin_path: str, table: str | None, spec: tuple[str, ...]) -> bool:
    cmd = [bin_path]
    if table:
        cmd.extend(["-t", table])
    cmd.extend(["-C", *spec])
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return proc.returncode == 0


def iptables_apply(
    bin_path: str,
    table: str | None,
    action: str,
    spec: tuple[str, ...],
) -> None:
    if iptables_has(bin_path, table, spec):
        return
    cmd = [bin_path]
    if table:
        cmd.extend(["-t", table])
    cmd.extend([action, *spec])
    run_text(cmd)


def iptables_remove(bin_path: str, table: str | None, spec: tuple[str, ...]) -> None:
    if not iptables_has(bin_path, table, spec):
        return
    cmd = [bin_path]
    if table:
        cmd.extend(["-t", table])
    cmd.extend(["-D", *spec])
    subprocess.run(cmd, check=False, capture_output=True, text=True)


def apply_nat(settings: Settings, *, up: bool) -> None:
    if not settings.wan_interface:
        raise SystemExit("WG_WAN_INTERFACE is empty")
    binary = find_iptables()
    network = network_cidr(settings.server_cidr)
    masquerade = nat_masquerade_spec(network, settings.wan_interface)
    inbound = forward_in_spec(settings.tun_if)
    outbound = forward_out_spec(settings.tun_if)
    if up:
        iptables_apply(binary, "nat", "-A", masquerade)
        iptables_apply(binary, None, "-A", inbound)
        iptables_apply(binary, None, "-A", outbound)
        return
    iptables_remove(binary, "nat", masquerade)
    iptables_remove(binary, None, inbound)
    iptables_remove(binary, None, outbound)


def apply_ssh_lock_v6(port: int) -> None:
    binary = find_ip6tables()
    iptables_apply(binary, None, "-I", ssh_allow_established_spec(port))
    iptables_apply(binary, None, "-A", ssh_drop_spec(port))


def apply_ssh_lock(settings: Settings) -> None:
    binary = find_iptables()
    network = network_cidr(settings.server_cidr)
    port = settings.ssh_port
    iptables_apply(binary, None, "-I", ssh_allow_established_spec(port))
    iptables_apply(binary, None, "-I", ssh_allow_vpn_spec(network, port))
    iptables_apply(binary, None, "-A", ssh_drop_spec(port))
    apply_ssh_lock_v6(port)


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


def totp_secret_path(settings: Settings, name: str) -> Path:
    return settings.config_dir / "mfa" / "totp" / name


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def otpauth_uri(name: str, secret: str) -> str:
    return (
        f"otpauth://totp/ops-vpn:{name}?secret={secret}"
        "&issuer=ops-vpn&algorithm=SHA1&digits=6&period=30"
    )


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


def config_dir_from(env: Mapping[str, str], override: Path | None) -> Path:
    if override is not None:
        return override
    raw = env.get("WG_CONFIG_DIR", "").strip() or "/config"
    return Path(raw)


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
