# ops-scripts

A growing collection of admin scripts for the sites and tools the owner relies on — data manipulation tools, cron jobs, and importers for sites that don't ship the admin tools we need. It started with a Mastodon hashtag importer.

## Layout

```
bin/          optional PATH wrappers / one-liners
lib/          shared helpers reused by more than one script
cron/         jobs meant to run on a schedule
importers/    pull or push data into external sites
data/         one-off transforms, reports, cleanup
sites/        ad-hoc admin tools grouped by product
config/       example configs only — never real secrets
docs/         longer notes when a README section is not enough
dotfiles/     shell dotfiles + installer (bash/, setup.sh) for Ubuntu/WSL
windows/      Windows-only admin scripts (PowerShell). Keep out of the Linux trees.
macos/        macOS client bootstrap (Homebrew). Not a CUDA/CAD host.
```

## Conventions

These are meant to scale to ~100 scripts:

- Group by job type first (`cron` / `importers` / `data` / `sites`), then by product (`mastodon`, …), then by script name.
- One directory per script when it has extras (sample input, notes). A lone file is fine for a true one-liner.
- kebab-case names for directories; Python modules use `snake_case` so they import.
- Each script should be runnable on its own; put shared code in `lib/`.
- Website / API / importer / server work: Python 3 (`python path/to/script.py`, stdlib `urllib` / `http.server` / `sqlite3`).
- Local files, reports, SSH, and shell glue: Python 3 (`python path/to/script.py`).
- Windows services / PnP / audio: PowerShell under `windows/` (`powershell -File windows/scripts/…`).
- macOS client tools: Homebrew under `macos/` (`bash macos/install-tools.sh`).
- Secrets via environment variables or an untracked `.env` — never committed.
- Prefer a short comment block at the top of a script over a separate README unless usage is non-obvious.

## Adding a script

1. Pick the directory that fits the job type (see Layout).
2. Create `product/script-name/` if it needs extras, or just a single kebab-case file.
3. Keep it self-contained; move any reused logic into `lib/`.
4. Read config from env vars or `.env`, never hardcode secrets.
5. Add a short header comment describing what it does and how to run it.
6. If it needs a config example, add it under `config/examples/`.

## Running scripts

```
python path/to/script.py
```

New site, API, importer, and server work is Python. TypeScript is only for browser view manipulation.

Agents: see `AGENTS.md`.

## Contents

- `importers/mastodon/follow-hashtags/` — bulk-follow Mastodon hashtags from a file, another account's followed_tags, and/or trending tags. Python, dry-run by default.
- `sites/opencode/config-generator/` — interactive wizard that generates a project or global opencode.json: model picker fed by `opencode models`, agent editor, validation via `opencode debug config`, backup before replace. Python.
- `sites/opencode/config-generator/opencode.json.example` — seed for `~/.config/opencode/opencode.json`. The wizard merges this file. Not named `opencode.json`, so OpenCode does not load it as project config. Ships disabled `jev-mcp` (TypeSafe Jev judgments); needs `TYPESAFE_API_KEY`, then flip `disabled` to `false`.
- `dotfiles/` — the shell dotfiles and installer (merged from the `dotfiles` repo). See `dotfiles/README.md`; run `bash dotfiles/setup.sh` from the repo to install. Always installs user-wide `AGENTS.md` (`~/.config/agents/AGENTS.md`, OpenCode pointer at `~/.config/opencode/AGENTS.md` — symlink, copy fallback) and user-wide skills (`dotfiles/agents/skills/` → `~/.config/opencode/skills/`, same way).
- `windows/` — Windows setup + admin scripts. See `windows/README.md`; run `windows/scripts/install-tools.ps1` then `windows/scripts/install-profile.ps1` from the repo root.
- `windows/scripts/set-powershell-start-home.ps1` — make PowerShell / pwsh open in the user home directory (shortcuts + Windows Terminal). Profile fallback cds out of System32.
- `windows/scripts/restart-audio.ps1` — recycle the ROG Cirrus speaker amp, Realtek codec, and Windows Audio when speakers die and a tinny motherboard device takes over. PowerShell, self-elevates.
- `sites/android-tv/` — ADB debloat for the Magicubic HY300 / Skyworth stick. Disable-user only, dry-run default, protected-package guards. Python.
- `sites/vpn/` — WireGuard VPN + nginx tunnel-IP gateway (Compose) for a Linux instance. SSH over `10.13.13.1`. Clients: Windows / Linux / macOS / iPad / Android (`clients/show-qr.py`).
- `sites/hosts/` — named SSH/Docker inventory (`vpn-gw`, `gpu-1`, `cad-ws`). Copy `hosts.example.json` to `hosts.json`. Python.
- `macos/` — Mac client bootstrap (Homebrew Brewfile + AGENTS.md). Not a CUDA host. See `macos/README.md`; run `bash macos/install-tools.sh`.

Repo: https://github.com/tonyarcher/ops-scripts
