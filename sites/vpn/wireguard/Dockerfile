# syntax=docker/dockerfile:1.7
# WireGuard server image. Build on the engine that will run it (no registry).
#
# What: wireguard-tools + vpnconfig.py. Keys are created at runtime in /config.
# Base: ubuntu:24.04
# Run:  docker compose up --build   or   ./deploy.sh up
#
# Needs host network, NET_ADMIN, /dev/net/tun. Do not bake keys.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    WG_CONFIG_DIR=/config

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    iproute2 \
    iptables \
    kmod \
    python3 \
    wireguard-tools \
    && rm -rf /var/lib/apt/lists/*

COPY vpnconfig.py /opt/vpn/vpnconfig.py
COPY wireguard/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh && chmod 0644 /opt/vpn/vpnconfig.py

VOLUME /config
EXPOSE 51820/udp

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wg show wg0 >/dev/null || exit 1

ENTRYPOINT ["/entrypoint.sh"]
