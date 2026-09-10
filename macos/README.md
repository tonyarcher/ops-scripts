# macos/

macOS **client** bootstrap. VPN + CLI tools. Not a CUDA/CAD host (no NVIDIA).

```
macos/
├── Brewfile           Homebrew formulae (git, node, python, opencode, …)
├── install-tools.sh   brew bundle + uv ruff/mypy + AGENTS.md
└── tests/             Brewfile contents (runs on any OS)
```

Does not port `dotfiles/bash/` (Mac default shell is zsh). Does not install
Rancher Desktop or the WireGuard GUI. Those are one-liners below.

```bash
# from the repo root, on a Mac
bash macos/install-tools.sh
bash macos/install-tools.sh --dry-run
bash macos/install-tools.sh --force
```

Needs [Homebrew](https://brew.sh). Idempotent. `--dry-run` prints the Brewfile
formulae and does not run `brew bundle install` or write AGENTS.md. Does not
edit `~/.zshrc`.

`openjdk@21` is keg-only. After install, put this in `~/.zprofile` if you want
`java` / unversioned `python` on PATH:

```bash
eval "$(/opt/homebrew/bin/brew shellenv)"   # Apple Silicon; Intel: /usr/local
export PATH="$(brew --prefix openjdk@21)/bin:$PATH"
export PATH="$(brew --prefix python)/libexec/bin:$PATH"
```

## WireGuard

Same peer conf as Windows/Linux:

```bash
python sites/vpn/deploy.py peer laptop > laptop.conf
brew install --cask wireguard    # or the App Store app
# import laptop.conf in the app
# or: bash sites/vpn/clients/connect.sh laptop.conf
```

`wireguard-tools` is in the Brewfile so `wg-quick` exists for `connect.sh`.

## Docker

GUI Mac uses **Rancher Desktop**, same rule as Windows / Linux GUI. Not Docker
Desktop.

```bash
brew install --cask rancher
```

Then `bash sites/opencode/docker-image/deploy.sh` works as documented.

## GPU / CAD

This machine is a laptop client on `10.13.13.0/24`. CUDA CAD batch jobs and
LLMs run on `gpu-1`. Interactive CAD stays on `cad-ws`. See `sites/hosts/`.

## Verification

```bash
python macos/tests/test_brewfile.py
bash macos/install-tools.sh --help
# on a Mac:
bash macos/install-tools.sh --dry-run
```
