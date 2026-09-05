# windows/

Windows-only admin scripts. The rest of this repo is Linux/WSL or OS-agnostic.

```
windows/
├── powershell/    PowerShell profile (hub + env/aliases/functions/prompt)
└── scripts/       one-shot admin scripts (install-tools, install-profile, ...)
```

Run from PowerShell at the repo root, or right-click a `.ps1` → Run with PowerShell (it will UAC-elevate when needed).

```
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/install-tools.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/install-profile.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/restart-audio.ps1
```

`install-tools.ps1` takes `-DryRun` (list only) and `-Force` (reinstall all).
`install-profile.ps1` supports `-WhatIf`, and backs up existing profiles to
`~/.windows-profile-backup/<timestamp>/` (per shell: `WindowsPowerShell`, `PowerShell`).

