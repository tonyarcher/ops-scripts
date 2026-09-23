"""Settings model, env parsing, and addressing rules for sites/vpn."""

from __future__ import annotations

import ipaddress
import re
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


def config_dir_from(env: Mapping[str, str], override: Path | None) -> Path:
    if override is not None:
        return override
    raw = env.get("WG_CONFIG_DIR", "").strip() or "/config"
    return Path(raw)
