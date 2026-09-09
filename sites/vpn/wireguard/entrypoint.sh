#!/usr/bin/env bash
# Bring up WireGuard on the host netns (compose network_mode: host).
# Keys land in /config. Do not run by hand unless you mean to change host wg0.
set -euo pipefail

: "${WG_CONFIG_DIR:=/config}"
: "${WG_TUN_IF:=wg0}"

modprobe wireguard 2>/dev/null || true
if [[ "$(cat /proc/sys/net/ipv4/ip_forward)" != "1" ]]; then
  sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
fi
if [[ "$(cat /proc/sys/net/ipv4/ip_forward)" != "1" ]]; then
  echo "error: net.ipv4.ip_forward is 0 (host netns is read-only from Docker)." >&2
  echo "  on the host: sudo sysctl -w net.ipv4.ip_forward=1" >&2
  exit 1
fi

if [[ -z "${WG_WAN_INTERFACE:-}" ]]; then
  WG_WAN_INTERFACE="$(ip -4 route show default | awk '{print $5; exit}')"
  export WG_WAN_INTERFACE
fi
if [[ -z "${WG_WAN_INTERFACE:-}" ]]; then
  echo "error: could not detect WAN interface; set WG_WAN_INTERFACE" >&2
  exit 1
fi
export WG_WAN_INTERFACE

python3 /opt/vpn/vpnconfig.py render --config-dir "$WG_CONFIG_DIR"

conf="$WG_CONFIG_DIR/${WG_TUN_IF}.conf"
if [[ ! -f "$conf" ]]; then
  echo "error: missing $conf" >&2
  exit 1
fi

cleanup() {
  python3 /opt/vpn/vpnconfig.py nat-down --config-dir "$WG_CONFIG_DIR" || true
  wg-quick down "$conf" 2>/dev/null || wg-quick down "$WG_TUN_IF" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

if ip link show "$WG_TUN_IF" >/dev/null 2>&1; then
  echo "removing stale ${WG_TUN_IF}" >&2
  wg-quick down "$WG_TUN_IF" 2>/dev/null || ip link delete "$WG_TUN_IF" || true
fi

python3 /opt/vpn/vpnconfig.py nat-up --config-dir "$WG_CONFIG_DIR"
wg-quick up "$conf"
echo "wireguard up if=${WG_TUN_IF} wan=${WG_WAN_INTERFACE}" >&2
echo "client profiles: ${WG_CONFIG_DIR}/peers/*/client.conf" >&2

while wg show "$WG_TUN_IF" >/dev/null 2>&1; do
  sleep 30
done
echo "error: ${WG_TUN_IF} disappeared" >&2
exit 1
