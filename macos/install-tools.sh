#!/usr/bin/env bash
# macOS client bootstrap. Homebrew CLI tools + user-wide AGENTS.md.
#
# What: brew bundle the sibling Brewfile, uv ruff/mypy, install-agents.py.
# Run:  bash macos/install-tools.sh
#       bash macos/install-tools.sh --dry-run
#       bash macos/install-tools.sh --force
#
# Needs Homebrew. Does not edit zsh/bash profiles. Does not install Rancher
# Desktop or the WireGuard app (see macos/README.md). Mac is not a CUDA host.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BREWFILE="$SCRIPT_DIR/Brewfile"
AGENTS_PY="$REPO_ROOT/dotfiles/install-agents.py"

DRY_RUN=0
FORCE=0

usage() {
  sed -n '2,10p' "$0" | sed 's/^# //;s/^#//'
}

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) DRY_RUN=1 ;;
      --force) FORCE=1 ;;
      -h|--help) usage; exit 0 ;;
      *) echo "error: unknown arg $1" >&2; usage >&2; exit 1 ;;
    esac
    shift
  done
}

need_darwin() {
  if [ "$(uname -s)" != "Darwin" ]; then
    echo "error: macOS only (uname is $(uname -s))" >&2
    exit 1
  fi
}

find_brew() {
  if command -v brew >/dev/null 2>&1; then
    return 0
  fi
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    return 0
  fi
  if [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
    return 0
  fi
  echo "error: Homebrew not found. Install from https://brew.sh" >&2
  exit 1
}

install_formulae() {
  echo "==> brew bundle ($BREWFILE)"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "    would brew bundle install --file $BREWFILE"
    grep '^brew ' "$BREWFILE" | sed 's/^/    /'
    return 0
  fi
  local args
  args=(--file "$BREWFILE")
  if [ "$FORCE" -eq 1 ]; then
    args+=(--force)
  fi
  brew bundle install "${args[@]}"
}

install_uv_tools() {
  echo "==> python tools (ruff, mypy) via uv"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "    would uv tool install ruff mypy"
    return 0
  fi
  if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv not on PATH after brew bundle" >&2
    exit 1
  fi
  uv tool install ruff
  uv tool install mypy
}

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    echo python
    return 0
  fi
  echo "error: python3 not on PATH after brew bundle" >&2
  exit 1
}

install_agents() {
  echo "==> user-wide AGENTS.md (OpenCode pointer)"
  local py args
  py="$(find_python)"
  args=("$AGENTS_PY")
  if [ "$DRY_RUN" -eq 1 ]; then
    args+=(--dry-run)
  fi
  if [ "$FORCE" -eq 1 ]; then
    args+=(--force)
  fi
  "$py" "${args[@]}"
}

print_next() {
  echo
  echo "Done. Open a new terminal so PATH picks up brew, uv, and rustup."
  echo "Java (keg-only):  export PATH=\"\$(brew --prefix openjdk@21)/bin:\$PATH\""
  echo "python alias:     export PATH=\"\$(brew --prefix python)/libexec/bin:\$PATH\""
  echo "WireGuard app:    brew install --cask wireguard   (or the App Store)"
  echo "  then import a peer conf from: python sites/vpn/deploy.py peer laptop"
  echo "  or: bash sites/vpn/clients/connect.sh laptop.conf"
  echo "Docker engine:    brew install --cask rancher     (not Docker Desktop)"
  echo "This Mac is a client. CUDA CAD/LLM stays on gpu-1 / cad-ws (sites/hosts)."
}

parse_args "$@"
need_darwin
find_brew
install_formulae
install_uv_tools
install_agents
print_next
