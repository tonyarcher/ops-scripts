#!/usr/bin/env bash
# Wait for the WireGuard address, then run nginx in the foreground.
set -euo pipefail

: "${WG_SERVER_ADDRESS:=10.13.13.1/24}"
: "${WG_HTTP_PORT:=8080}"
LISTEN_ADDR="${WG_LISTEN_ADDR:-}"
if [[ -z "$LISTEN_ADDR" ]]; then
  LISTEN_ADDR="${WG_SERVER_ADDRESS%%/*}"
fi
export LISTEN_ADDR WG_HTTP_PORT

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
envsubst '${LISTEN_ADDR} ${WG_HTTP_PORT}' \
  < /etc/nginx/templates/healthz.conf.template \
  > /etc/nginx/http.d/00-healthz.conf

nginx -t
exec nginx -g "daemon off;"
