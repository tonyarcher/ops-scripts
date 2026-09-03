# windows/

Windows-only admin scripts. The rest of this repo is Linux/WSL or OS-agnostic.

Run from PowerShell at the repo root, or right-click a `.ps1` → Run with PowerShell (it will UAC-elevate when needed).

```
powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/restart-audio.ps1
```
