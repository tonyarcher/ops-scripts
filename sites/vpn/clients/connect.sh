#!/usr/bin/env bash
# Bring up a WireGuard client profile from the VPN server.
#
# What: wg-quick up on Linux or macOS. Needs wireguard-tools and usually sudo.
# Run:  ./clients/connect.sh /path/to/laptop.conf
#       ./clients/connect.sh /path/to/laptop.conf down
#
# Get the profile (contains a private key):
#   ./deploy.sh peer laptop > laptop.conf
# iPad/Android: python sites/vpn/clients/show-qr.py laptop.conf
# Windows: powershell -File windows/scripts/connect-ops-vpn.ps1 -Config laptop.conf
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 /path/to/client.conf [up|down]" >&2
  exit 1
fi

CONF="$1"
ACTION="${2:-up}"
if [[ ! -f "$CONF" ]]; then
  echo "error: no such file $CONF" >&2
  exit 1
fi
if ! command -v wg-quick >/dev/null 2>&1; then
  echo "error: wg-quick not found. Install wireguard-tools, or import $CONF" >&2
  echo "  Linux:  apt/dnf install wireguard-tools" >&2
  echo "  macOS:  brew install wireguard-tools  (or the WireGuard app)" >&2
  exit 1
fi

abs="$(cd -- "$(dirname -- "$CONF")" && pwd)/$(basename -- "$CONF")"
case "$ACTION" in
  up) exec sudo wg-quick up "$abs" ;;
  down) exec sudo wg-quick down "$abs" ;;
  *) echo "usage: $0 /path/to/client.conf [up|down]" >&2; exit 1 ;;
esac
