# =============================================================================
#  profile-prompt.ps1  --  the prompt
#
#  Dot-sourced by Microsoft.PowerShell_profile.ps1 (the hub). Shows:
#  user@host : C:\current\dir (branch) >   Mirrors dotfiles/bash/.bash_prompt:
#  - green branch  = clean working tree
#  - red branch    = uncommitted changes
#  - red X(exit) replaces the > when the last command failed
# =============================================================================

Set-StrictMode -Version Latest

function Get-GitSegment {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return '' }
    $branch = git rev-parse --abbrev-ref HEAD 2>$null
    if (-not $branch) { return '' }
    $dirty = git status --porcelain 2>$null | Select-Object -First 1
    $color = 'Green'
    if ($dirty) { $color = 'Red' }
    return @{ Text = " ($branch)"; Color = $color }
}

function prompt {
    $ok = $?
    # Capture FIRST: every native call below (git) overwrites $LASTEXITCODE.
    # Note: cmdlet-only failures leave a stale native code; the marker then
    # means "last native command failed", same tradeoff as bash `$?` vs $!.
    # $LASTEXITCODE does not exist until the first native command runs.
    $code = Get-Variable LASTEXITCODE -ValueOnly -ErrorAction SilentlyContinue
    if ($null -eq $code) { $code = 0 }
    $seg = Get-GitSegment
    # Track directory history for `back` (Set-Location - only exists on PS 6.2+).
    $here = (Get-Location).Path
    if (($global:__lastDir) -and ($global:__lastDir -ne $here)) { $global:__prevDir = $global:__lastDir }
    $global:__lastDir = $here
    Write-Host "$env:USERNAME" -NoNewline -ForegroundColor Green
    Write-Host '@' -NoNewline
    Write-Host "$env:COMPUTERNAME" -NoNewline -ForegroundColor Blue
    Write-Host ' : ' -NoNewline
    Write-Host $here -NoNewline -ForegroundColor Cyan
    if ($seg) { Write-Host $seg.Text -NoNewline -ForegroundColor $seg.Color }
    if ($ok) {
        Write-Host ' > ' -NoNewline -ForegroundColor Magenta
    } else {
        Write-Host " X($code) " -NoNewline -ForegroundColor Red
    }
    return ' '
}
