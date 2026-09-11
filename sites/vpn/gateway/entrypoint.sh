#!/usr/bin/env bash
# Wait for the WireGuard address, then run nginx in the foreground.
set -euo pipefail

: "${WG_SERVER_ADDRESS:=10.13.13.1/24}"
: "${WG_HTTP_PORT:=8080}"
: "${WG_MFA:=false}"
: "${WG_MFA_HOST:=vpn.ops}"
LISTEN_ADDR="${WG_LISTEN_ADDR:-}"
if [[ -z "$LISTEN_ADDR" ]]; then
  LISTEN_ADDR="${WG_SERVER_ADDRESS%%/*}"
fi
export LISTEN_ADDR WG_HTTP_PORT WG_MFA_HOST

echo "waiting for ${LISTEN_ADDR} ..."
ok=0
for _ in $(seq 1 60); do
  if ip -4 addr show | grep -q "inet ${LISTEN_ADDR}/"; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "error: ${LISTEN_ADDR} not on any interface (is wireguard up?)" >&2
  exit 1
fi

mkdir -p /etc/nginx/http.d
mfa_on=0
case "${WG_MFA,,}" in
  1|true|yes|on) mfa_on=1 ;;
esac
if [[ "$mfa_on" -eq 1 ]]; then
  envsubst '${LISTEN_ADDR} ${WG_HTTP_PORT}' \
    < /etc/nginx/templates/healthz-mfa.conf.template \
    > /etc/nginx/http.d/00-healthz.conf
  if [[ -f /config/mfa/tls/host.crt && -f /config/mfa/tls/host.key ]]; then
    envsubst '${LISTEN_ADDR} ${WG_MFA_HOST}' \
      < /etc/nginx/templates/https-mfa.conf.template \
      > /etc/nginx/http.d/01-https-mfa.conf
  fi
  cp /etc/nginx/templates/mfa-protect.inc /etc/nginx/mfa-protect.inc
  dnsmasq --listen-address="${LISTEN_ADDR}" --bind-interfaces \
    --address="/${WG_MFA_HOST}/${LISTEN_ADDR}" --server=1.1.1.1 \
    --no-resolv --port=53 --pid-file=/run/dnsmasq.pid \
    || echo "warning: dnsmasq failed (is :53 already bound on ${LISTEN_ADDR}?)" >&2
else
  envsubst '${LISTEN_ADDR} ${WG_HTTP_PORT}' \
    < /etc/nginx/templates/healthz.conf.template \
    > /etc/nginx/http.d/00-healthz.conf
fi

nginx -t
exec nginx -g "daemon off;"
