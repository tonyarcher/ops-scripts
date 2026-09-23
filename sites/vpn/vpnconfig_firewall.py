"""iptables rule specs and SSH-lock / NAT apply for sites/vpn."""

from __future__ import annotations

import subprocess

from vpnconfig_exec import find_ip6tables, find_iptables, run_text
from vpnconfig_settings import Settings, network_cidr


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
