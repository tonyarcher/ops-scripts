#!/usr/bin/env bash
# Generate TLS material if missing, then serve the MFA portal.
set -euo pipefail
: "${WG_CONFIG_DIR:=/config}"
export MFA_TLS_DIR="${WG_CONFIG_DIR}/mfa/tls"
/make-certs.sh
exec node /app/server.ts
