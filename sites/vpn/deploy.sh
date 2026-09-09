#!/usr/bin/env bash
# Thin wrapper. The real driver is deploy.py (Windows + Linux).
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
    exec python3 "$SCRIPT_DIR/deploy.py" "$@"
fi
exec python "$SCRIPT_DIR/deploy.py" "$@"
