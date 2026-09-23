"""WireGuard config and summary text rendering for sites/vpn."""

from __future__ import annotations

from vpnconfig_settings import Settings, allowed_ips_for_client, listen_addr


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
