#!/usr/bin/env bash
# One-time private CA + host cert for MFA HTTPS (security keys).
# No public CA, no Google. Writes /config/mfa/tls/.
set -euo pipefail
DIR="${MFA_TLS_DIR:-/config/mfa/tls}"
HOST="${WG_MFA_HOST:-vpn.ops}"
mkdir -p "$DIR"
if [[ -f "$DIR/host.crt" && -f "$DIR/host.key" && -f "$DIR/ca.crt" ]]; then
  exit 0
fi
openssl genrsa -out "$DIR/ca.key" 4096
openssl req -x509 -new -key "$DIR/ca.key" -sha256 -days 3650 \
  -out "$DIR/ca.crt" -subj "/CN=ops-vpn MFA CA"
openssl genrsa -out "$DIR/host.key" 2048
openssl req -new -key "$DIR/host.key" -out "$DIR/host.csr" -subj "/CN=${HOST}"
printf 'subjectAltName=DNS:%s\n' "$HOST" > "$DIR/ext.cnf"
openssl x509 -req -in "$DIR/host.csr" -CA "$DIR/ca.crt" -CAkey "$DIR/ca.key" \
  -CAcreateserial -out "$DIR/host.crt" -days 825 -sha256 -extfile "$DIR/ext.cnf"
chmod 600 "$DIR/ca.key" "$DIR/host.key"
chmod 644 "$DIR/ca.crt" "$DIR/host.crt"
rm -f "$DIR/host.csr" "$DIR/ext.cnf"
