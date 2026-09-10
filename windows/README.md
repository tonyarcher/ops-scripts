# windows/

Windows-only admin scripts. The rest of this repo is Linux/WSL or OS-agnostic.
macOS client bootstrap is `macos/`, not here.

```
windows/
├── powershell/    PowerShell profile (hub + env/aliases/functions/prompt)
└── scripts/       one-shot admin scripts (install-tools, install-profile, ...)
```

Run from PowerShell at the repo root, or right-click a `.ps1` → Run with PowerShell (it will UAC-elevate when needed).

```
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/install-tools.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/install-profile.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/set-powershell-start-home.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/restart-audio.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/deploy-ops-vpn.ps1 --remote up
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/connect-ops-vpn.ps1 -Config .\laptop.conf
```

`install-tools.ps1` takes `-DryRun` (list only) and `-Force` (reinstall all).
It also installs Go, JDK 21, rustup, ruff/mypy (via uv), and the user-wide
AGENTS.md (`%APPDATA%\agents\AGENTS.md`, OpenCode pointer at
`~\.config\opencode\AGENTS.md` — symlink, or a copy if Windows lacks symlink
privilege).
`install-profile.ps1` supports `-WhatIf`, and backs up existing profiles to
`~/.windows-profile-backup/<timestamp>/` (per shell: `WindowsPowerShell`, `PowerShell`).
`set-powershell-start-home.ps1` sets Start Menu / Desktop PowerShell shortcuts
and Windows Terminal PowerShell profiles to open in `%USERPROFILE%`. Supports
`-WhatIf`. Explorer "Open here" and IDE terminals are left alone.

