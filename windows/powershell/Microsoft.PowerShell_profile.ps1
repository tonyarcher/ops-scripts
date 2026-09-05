# =============================================================================
#  Microsoft.PowerShell_profile.ps1  --  interactive PowerShell config (the "hub")
#
#  Installed by windows/scripts/install-profile.ps1 into the PowerShell 5.1
#  and PowerShell 7 profile directories. Intentionally tiny; it delegates to
#  focused files living next to it, mirroring dotfiles/bash/.bashrc:
#
#    profile-env.ps1        -> PATH + environment variables (JAVA_HOME, ...)
#    profile-aliases.ps1    -> command shortcuts (ll, gs, dc, ...)
#    profile-functions.ps1  -> reusable functions (mkcd, up, extract, ...)
#    profile-prompt.ps1     -> git-aware prompt with exit-code marker
#
#  Rule of thumb: a *variable* or *PATH* entry goes in profile-env.ps1.
#  A *shortcut* goes in profile-aliases.ps1. Never edit this hub.
# =============================================================================

Set-StrictMode -Version Latest

# Directory history for `back` (see profile-aliases.ps1); tracked in prompt
# because Set-Location - only exists on PowerShell 6.2+.
$global:__lastDir = $null
$global:__prevDir = $null

# --- Environment variables & PATH -------------------------------------------
$EnvFile = Join-Path $PSScriptRoot 'profile-env.ps1'
if (Test-Path $EnvFile) { . $EnvFile }

# --- Aliases ------------------------------------------------------------------
$AliasFile = Join-Path $PSScriptRoot 'profile-aliases.ps1'
if (Test-Path $AliasFile) { . $AliasFile }

# --- Functions ------------------------------------------------------------------
$FuncFile = Join-Path $PSScriptRoot 'profile-functions.ps1'
if (Test-Path $FuncFile) { . $FuncFile }

# --- Prompt ---------------------------------------------------------------------
$PromptFile = Join-Path $PSScriptRoot 'profile-prompt.ps1'
if (Test-Path $PromptFile) { . $PromptFile }

# --- History ----------------------------------------------------------------------
if (Get-Module -ListAvailable -Name PSReadLine) {
    Import-Module PSReadLine -ErrorAction SilentlyContinue
    # Emacs-style editing (mirrors dotfiles .inputrc); no beep on errors.
    Set-PSReadLineOption -EditMode Emacs -BellStyle None -ErrorAction SilentlyContinue
    Set-PSReadLineOption -MaximumHistoryCount 10000 -ErrorAction SilentlyContinue
    Set-PSReadLineOption -HistoryNoDuplicates -ErrorAction SilentlyContinue
}

# --- Tool hooks (enabled only if the tool is installed) ---------------------------
# zoxide -- smart "cd", use `z <fragment>` to jump.  winget: ajeetdsouza.zoxide
if (Get-Command zoxide -ErrorAction SilentlyContinue) {
    Invoke-Expression (& { (zoxide init powershell | Out-String) })
}

# --- Misc defaults ------------------------------------------------------------------
if (-not $env:EDITOR) { $env:EDITOR = 'notepad' }
if (-not $env:PAGER) { $env:PAGER = 'more' }

$PROFILE_HUB_LOADED = 'yes'
