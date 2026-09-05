# Install the PowerShell profile. Mirrors `dotfiles/setup.sh` steps 1-2:
#   1. Backs up any existing profile files to ~/.windows-profile-backup/<timestamp>/
#   2. Copies (not symlinks) the hub + split files into the PowerShell 5.1
#      AND PowerShell 7 profile directories, so both shells behave the same.
# Idempotent: safe to run again after edits (plain copy overwrite).
#
# Needs no admin. Never touches another machine's files; everything stays
# under $HOME\Documents and the repo checkout.
#
# Run from the repo root:
#   powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/install-profile.ps1
#   powershell ... -File windows/scripts/install-profile.ps1 -WhatIf   (preview only)
#
# Uninstall: move a backup back over the profile directories, per shell.
#   Move-Item ~/.windows-profile-backup/<timestamp>/WindowsPowerShell/* ~/Documents/WindowsPowerShell/ -Force
#   Move-Item ~/.windows-profile-backup/<timestamp>/PowerShell/* ~/Documents/PowerShell/ -Force

[CmdletBinding(SupportsShouldProcess = $true)]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$RepoRoot = Split-Path (Split-Path $PSScriptRoot)
$Src = Join-Path $RepoRoot 'windows\powershell'
$Files = @(
    'Microsoft.PowerShell_profile.ps1',
    'profile-env.ps1',
    'profile-aliases.ps1',
    'profile-functions.ps1',
    'profile-prompt.ps1'
)
# Resolve via the shell folder, not $HOME\Documents: OneDrive redirection
# moves Documents (and $PROFILE with it) elsewhere.
$Docs = [Environment]::GetFolderPath('MyDocuments')
$Targets = @(
    (Join-Path $Docs 'WindowsPowerShell'),   # PowerShell 5.1
    (Join-Path $Docs 'PowerShell')            # PowerShell 7 (pwsh)
)
$BackupDir = "$HOME\.windows-profile-backup\$(Get-Date -Format 'yyyyMMdd-HHmmss')"

# --- 1. Back up existing files --------------------------------------------------
# Backups are namespaced per shell (WindowsPowerShell vs PowerShell) so the
# 5.1 and 7 profiles never overwrite each other in the backup dir.
$backedUp = 0
foreach ($dir in $Targets) {
    $ns = Split-Path $dir -Leaf
    foreach ($f in $Files) {
        $existing = Join-Path $dir $f
        if (Test-Path $existing) {
            if ($PSCmdlet.ShouldProcess($existing, 'Backup')) {
                New-Item -ItemType Directory -Force -Path (Join-Path $BackupDir $ns) | Out-Null
                Move-Item $existing (Join-Path (Join-Path $BackupDir $ns) $f) -Force
                $backedUp += 1
            }
        }
    }
}
if ($backedUp -gt 0) {
    Write-Host "Previous profile files backed up to: $BackupDir"
} elseif (Test-Path $BackupDir) {
    Remove-Item $BackupDir
}

# --- 2. Copy the new files ---------------------------------------------------------
foreach ($dir in $Targets) {
    foreach ($f in $Files) {
        $srcFile = Join-Path $Src $f
        if (Test-Path $srcFile) {
            if ($PSCmdlet.ShouldProcess((Join-Path $dir $f), 'Copy')) {
                New-Item -ItemType Directory -Force -Path $dir | Out-Null
                Copy-Item $srcFile (Join-Path $dir $f) -Force
                Write-Host "    installed $f -> $dir"
            }
        }
    }
}

if ($WhatIfPreference) { return }

Write-Host '============================================================'
Write-Host ' PowerShell profile installed (5.1 + 7).'
Write-Host ' Open a new shell, or run:  . $PROFILE'
Write-Host " Files installed:  $($Files -join ' ')"
Write-Host '============================================================'
