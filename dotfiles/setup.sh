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
#    3. Installs user-wide AGENTS.md and points OpenCode at it
#       (~/.config/agents/AGENTS.md <- repo; ~/.config/opencode/AGENTS.md
#       symlink, or a copy if the OS refuses the link).
#    4. With --install-tools: apt-installs optional tools (ripgrep, eza, fzf,
#       zoxide, htop, jq, tree, unzip, 7zip, bat, fd-find, curl, golang-go,
#       openjdk-21, shellcheck, shfmt) plus bun, prettier, uv (ruff, mypy,
#       sqlfluff, yamllint), Gradle 9.4, rustup, and the hadolint / ktlint
#       release binaries and taplo (cargo).
#  Idempotent: safe to run again after edits.
# =============================================================================
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$DOTFILES_DIR/bash"
BACKUP_DIR="$HOME/.dotfiles-backup/$(date +%Y%m%d-%H%M%S)"

FILES=(.bashrc .bash_aliases .bash_functions .bash_env .bash_prompt .inputrc)

install_agents_md() {
    local py=""
    if command -v python3 >/dev/null 2>&1; then
        py=python3
    elif command -v python >/dev/null 2>&1; then
        py=python
    else
        echo "python3 not found; skip AGENTS.md (apt install python3)"
        return 0
    fi
    echo "Installing user-wide AGENTS.md..."
    "$py" "$DOTFILES_DIR/install-agents.py"
}

# --- 1. Back up existing files -------------------------------------------------
mkdir -p "$BACKUP_DIR"
for f in "${FILES[@]}"; do
    if [ -e "$HOME/$f" ]; then
        mv -v "$HOME/$f" "$BACKUP_DIR/$f" || true
    fi
done
if [ "$(ls -A "$BACKUP_DIR")" ]; then
    echo "Previous files backed up to: $BACKUP_DIR"
else
    rmdir "$BACKUP_DIR"
fi

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
    TOOLS=(curl ripgrep eza fzf zoxide htop jq tree unzip p7zip-full bat fd-find python3 golang-go openjdk-21-jdk-headless shellcheck shfmt)
    sudo apt update
    sudo apt install -y "${TOOLS[@]}"
    echo
    echo "Done. Note: 'bat' and 'fd-find' are installed as 'batcat' and 'fdfind' on"
    echo "Ubuntu -- run: sudo ln -s /usr/bin/batcat /usr/bin/bat ; sudo ln -s /usr/bin/fdfind /usr/bin/fd"

    echo
    echo "Installing bun (TypeScript runner)..."
    if command -v bun >/dev/null 2>&1; then
        echo "bun already on PATH: $(command -v bun) ($(bun --version))"
    elif [ -x "$HOME/.bun/bin/bun" ]; then
        echo "bun already at $HOME/.bun/bin/bun"
    else
        export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
        mkdir -p "$BUN_INSTALL/bin"
        # Prepend so the installer sees bun on PATH and does not edit ~/.bashrc
        export PATH="$BUN_INSTALL/bin:$PATH"
        curl -fsSL https://bun.sh/install | bash
        if [ -x "$BUN_INSTALL/bin/bun" ] && [ ! -e "$BUN_INSTALL/bin/bunx" ]; then
            ln -sf bun "$BUN_INSTALL/bin/bunx"
        fi
        bun --version
    fi

    echo
    echo "Installing prettier (npm global)..."
    if command -v prettier >/dev/null 2>&1; then
        echo "prettier already on PATH: $(command -v prettier)"
    elif command -v npm >/dev/null 2>&1; then
        npm install -g prettier
    else
        echo "npm not found; skip prettier (apt install npm)"
    fi

    echo
    echo "Installing uv (Python tools)..."
    if command -v uv >/dev/null 2>&1 || [ -x "$HOME/.local/bin/uv" ]; then
        echo "uv already installed"
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    export PATH="$HOME/.local/bin:$PATH"
    if command -v uv >/dev/null 2>&1; then
        uv tool install ruff
        uv tool install mypy
        uv tool install sqlfluff
        uv tool install yamllint
    fi

    echo
    echo
    echo "Installing Gradle..."
    if command -v gradle >/dev/null 2>&1; then
        echo "gradle already on PATH: $(command -v gradle)"
    else
        gradle_ver="9.4.0"
        gradle_dest="$HOME/.local/opt/gradle-${gradle_ver}"
        if [ -x "$gradle_dest/bin/gradle" ]; then
            echo "gradle already at $gradle_dest"
        else
            gradle_zip="/tmp/gradle-${gradle_ver}-bin.zip"
            mkdir -p "$HOME/.local/opt"
            curl -fsSL "https://services.gradle.org/distributions/gradle-${gradle_ver}-bin.zip" -o "$gradle_zip"
            unzip -q -o "$gradle_zip" -d "$HOME/.local/opt"
            rm -f "$gradle_zip"
            echo "installed gradle ${gradle_ver} at $gradle_dest"
        fi
    fi

    echo "Installing rustup..."
    if command -v rustup >/dev/null 2>&1 || [ -x "$HOME/.cargo/bin/rustup" ]; then
        echo "rustup already installed"
    else
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    fi
    export PATH="$HOME/go/bin:$HOME/.cargo/bin:$PATH"
    echo "Installing review tools (gitleaks, osv-scanner, git-delta, ast-grep, taplo)..."
    if command -v go >/dev/null 2>&1; then
        command -v gitleaks >/dev/null 2>&1 || go install github.com/zricethezav/gitleaks/v8@latest
        command -v osv-scanner >/dev/null 2>&1 || go install github.com/google/osv-scanner/v2/cmd/osv-scanner@latest
    fi
    if command -v cargo >/dev/null 2>&1; then
        command -v delta >/dev/null 2>&1 || cargo install git-delta --locked
        command -v sg >/dev/null 2>&1 || cargo install ast-grep --locked
        command -v taplo >/dev/null 2>&1 || cargo install taplo-cli --locked
    fi

    echo
    echo "Installing release-binary linters (hadolint, ktlint)..."
    mkdir -p "$HOME/.local/bin"
    # hadolint v2.12.0 -- bump the version here when updating.
    if command -v hadolint >/dev/null 2>&1; then
        echo "hadolint already on PATH: $(command -v hadolint)"
    else
        curl -fsSL "https://github.com/hadolint/hadolint/releases/download/v2.12.0/hadolint-Linux-x86_64" -o "$HOME/.local/bin/hadolint"
        chmod +x "$HOME/.local/bin/hadolint"
    fi
    # ktlint 1.8.0 -- the artifact is self-executing on Linux; chmod +x is enough.
    if command -v ktlint >/dev/null 2>&1; then
        echo "ktlint already on PATH: $(command -v ktlint)"
    else
        curl -fsSL "https://github.com/ktlint/ktlint/releases/download/1.8.0/ktlint" -o "$HOME/.local/bin/ktlint"
        chmod +x "$HOME/.local/bin/ktlint"
    fi
fi

# --- 3b. User-wide AGENTS.md (always; OpenCode reads ~/.config/opencode/AGENTS.md)
install_agents_md

# --- 4. Locale fix (avoids the "locale not supported" warning) --------------------
if [ -z "${LANG:-}" ] && command -v locale-gen >/dev/null 2>&1; then
    export LANG=C.UTF-8
fi

echo
echo "============================================================"
echo " dotfiles installed."
echo " Open a new terminal, or run:  source ~/.bashrc"
echo " Files installed:  $(
    IFS=' '
    echo "${FILES[*]}"
)"
echo "============================================================"
