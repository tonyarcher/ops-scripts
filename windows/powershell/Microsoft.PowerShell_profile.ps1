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
#  A *shortcut* goes in profile-aliases.ps1. Keep this hub tiny; the Misc
#  defaults section may hold session rules (editor, start directory).
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

# Start in $HOME when the host dumped us in System32 / SysWOW64 / the Start
# Menu folder (empty shortcut "Start in", or Run as administrator). Skip on
# profile reload and when the session already has a real CWD (Explorer
# "Open here", Windows Terminal startingDirectory, IDE terminals).
# Launcher-side default: windows/scripts/set-powershell-start-home.ps1
if (-not (Get-Variable PROFILE_HUB_LOADED -ValueOnly -ErrorAction SilentlyContinue)) {
    $here = (Get-Location).Path
    $sys32 = [Environment]::SystemDirectory
    $syswow = Join-Path $env:SystemRoot 'SysWOW64'
    if ($here -eq $sys32 -or $here -eq $syswow -or $here -like '*\Start Menu\Programs*') {
        Set-Location $HOME
    }
}

$PROFILE_HUB_LOADED = 'yes'
