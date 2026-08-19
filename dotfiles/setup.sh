#!/usr/bin/env bash
# =============================================================================
#  setup.sh  --  install the dotfiles on Ubuntu / WSL
#
#  Run:   bash setup.sh [--install-tools]
#
#  What it does:
#    1. Backs up any existing ~/.bashrc, ~/.bash_aliases, ... to
#       ~/.dotfiles-backup/<timestamp>/
#    2. Copies (not symlinks -- safer for WSL + Windows checkouts) the new
#       files into your home directory.
#    3. With --install-tools: also apt-installs the recommended optional tools
#       (ripgrep, eza, fzf, zoxide, htop, jq, tree, unzip, 7zip, bat, fd-find).
#  Idempotent: safe to run again after edits.
# =============================================================================
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$DOTFILES_DIR/bash"
BACKUP_DIR="$HOME/.dotfiles-backup/$(date +%Y%m%d-%H%M%S)"

FILES=(.bashrc .bash_aliases .bash_functions .bash_env .bash_prompt .inputrc)

# --- 1. Back up existing files -------------------------------------------------
mkdir -p "$BACKUP_DIR"
for f in "${FILES[@]}"; do
    if [ -e "$HOME/$f" ]; then
        mv -v "$HOME/$f" "$BACKUP_DIR/$f" || true
    fi
done
[ "$(ls -A "$BACKUP_DIR")" ] && echo "Previous files backed up to: $BACKUP_DIR" || rmdir "$BACKUP_DIR"

# --- 2. Copy the new files -------------------------------------------------------
for f in "${FILES[@]}"; do
    if [ -f "$SRC/$f" ]; then
        cp -v "$SRC/$f" "$HOME/$f"
    fi
done

# --- 3. Optional tools -------------------------------------------------------------
INSTALL_TOOLS="${1:-}"
if [ "$INSTALL_TOOLS" = "--install-tools" ]; then
    echo
    echo "Installing recommended optional tools..."
    TOOLS=(ripgrep eza fzf zoxide htop jq tree unzip p7zip-full bat fd-find)
    sudo apt update
    sudo apt install -y "${TOOLS[@]}"
    echo
    echo "Done. Note: 'bat' and 'fd-find' are installed as 'batcat' and 'fdfind' on"
    echo "Ubuntu -- run: sudo ln -s /usr/bin/batcat /usr/bin/bat ; sudo ln -s /usr/bin/fdfind /usr/bin/fd"
fi

# --- 4. Locale fix (avoids the "locale not supported" warning) --------------------
if [ -z "${LANG:-}" ] && command -v locale-gen >/dev/null 2>&1; then
    export LANG=C.UTF-8
fi

echo
echo "============================================================"
echo " dotfiles installed."
echo " Open a new terminal, or run:  source ~/.bashrc"
echo " Files installed:  $(IFS=' '; echo "${FILES[*]}")"
echo "============================================================"
