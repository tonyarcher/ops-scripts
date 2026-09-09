# Windows dev-tool installer. Mirrors `dotfiles/setup.sh --install-tools`
# (ripgrep, eza, fzf, zoxide, jq, bat, fd, 7zip) plus vim and the AI/power-user
# extras proven on this box: gh, pwsh 7, lazygit, uv, opencode, ffmpeg, Go,
# JDK 21, rustup. Also installs the user-wide AGENTS.md pointer (symlink or copy).
#
# Idempotent: installed tools are skipped (winget also no-ops on them).
# Needs no admin for user-scope installs; winget self-elevates per package
# when a machine-scope installer (e.g. Git) requires it.
#
# fzf note: the winget build is blocked by some Device Guard policies. When
# its install fails and Go is present, this falls back to
# `go install github.com/junegunn/fzf@latest` (lands in ~/go/bin).
#
# Run:
#   powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/install-tools.ps1
#   powershell ... -File windows/scripts/install-tools.ps1 -DryRun   (list only)
#   powershell ... -File windows/scripts/install-tools.ps1 -Force    (reinstall all)
#
# Or right-click the .ps1 -> Run with PowerShell.

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

# winget id, and the command that proves it is already usable.
$Tools = @(
    @{ Id = 'Git.Git'; Cmd = 'git' }
    @{ Id = 'OpenJS.NodeJS'; Cmd = 'node' }
    @{ Id = 'Python.Python.3.12'; Cmd = 'python' }
    @{ Id = 'GitHub.cli'; Cmd = 'gh' }
    @{ Id = 'Microsoft.PowerShell'; Cmd = 'pwsh' }
    @{ Id = 'BurntSushi.ripgrep.MSVC'; Cmd = 'rg' }
    @{ Id = 'eza-community.eza'; Cmd = 'eza' }
    @{ Id = 'ajeetdsouza.zoxide'; Cmd = 'zoxide' }
    @{ Id = 'jqlang.jq'; Cmd = 'jq' }
    @{ Id = 'sharkdp.bat'; Cmd = 'bat' }
    @{ Id = 'sharkdp.fd'; Cmd = 'fd' }
    @{ Id = '7zip.7zip'; Cmd = '7z' }
    @{ Id = 'JesseDuffield.lazygit'; Cmd = 'lazygit' }
    @{ Id = 'astral-sh.uv'; Cmd = 'uv' }
    @{ Id = 'SST.opencode'; Cmd = 'opencode' }
    @{ Id = 'Gyan.FFmpeg'; Cmd = 'ffmpeg' }
    @{ Id = 'vim.vim'; Cmd = 'vim' }
    @{ Id = 'GoLang.Go'; Cmd = 'go' }
    @{ Id = 'Microsoft.OpenJDK.21'; Cmd = 'java' }
    @{ Id = 'Rustlang.Rustup'; Cmd = 'rustup' }
)

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

function Update-SessionPath {
    # winget edits the registry PATH; refresh this process so just-installed
    # tools resolve without a shell restart.
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
        [System.Environment]::GetEnvironmentVariable('Path', 'User')
}

function Test-ToolUsable([string]$Cmd) {
    if (-not (Get-Command $Cmd -ErrorAction SilentlyContinue)) { return $false }
    # Fresh Windows ships a python.exe Store stub that matches Get-Command
    # but opens the Store instead of running. Only trust it if it reports.
    if ($Cmd -eq 'python') {
        python --version 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    return $true
}

function Install-WingetTool([string]$Id, [string]$Cmd) {
    if ((-not $Force) -and (Test-ToolUsable $Cmd)) {
        Write-Host "    already have $Cmd ($Id) -- skip"
        return
    }
    if ($DryRun) {
        Write-Host "    would install $Id"
        return
    }
    # NOTE: winget is a native exe -- a failed install does NOT throw, so the
    # exit code must be checked explicitly.
    winget install --id $Id --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    FAIL $Id : winget exit code $LASTEXITCODE"
        return
    }
    Update-SessionPath
    if (Test-ToolUsable $Cmd) {
        Write-Host "    installed $Id"
    } else {
        Write-Host "    FAIL $Id : installed but $Cmd not on PATH (restart the shell and retry)"
    }
}

function Install-Fzf {
    # winget fzf first (fast path); Device Guard fallback is a local go build.
    if ((-not $Force) -and (Test-ToolUsable 'fzf')) {
        Write-Host '    already have fzf -- skip'
        return
    }
    if ($DryRun) {
        Write-Host '    would install junegunn.fzf (winget, go-build fallback)'
        return
    }
    winget install --id junegunn.fzf --silent --accept-source-agreements --accept-package-agreements
    Update-SessionPath
    if (Test-ToolUsable 'fzf') {
        Write-Host '    installed junegunn.fzf'
        return
    }
    Write-Host '    winget fzf unusable here (Device Guard blocks some builds), trying go install'
    if (-not (Test-ToolUsable 'go')) {
        Write-Host '    FAIL fzf: no Go toolchain for the fallback (winget: GoLang.Go)'
        return
    }
    go install github.com/junegunn/fzf@latest
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    FAIL fzf go fallback : go exit code $LASTEXITCODE"
        return
    }
    Update-SessionPath
    if (Test-ToolUsable 'fzf') {
        Write-Host '    installed fzf via go (~/go/bin)'
    } else {
        Write-Host '    FAIL fzf: go build ok but fzf not on PATH (restart the shell and retry)'
    }
}

function Install-UvTools {
    if (-not (Test-ToolUsable 'uv')) {
        Write-Host '    skip: uv not on PATH'
        return
    }
    foreach ($pkg in @('ruff', 'mypy')) {
        if ((-not $Force) -and (Test-ToolUsable $pkg)) {
            Write-Host "    already have $pkg -- skip"
            continue
        }
        if ($DryRun) {
            Write-Host "    would uv tool install $pkg"
            continue
        }
        uv tool install $pkg
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    FAIL uv tool install $pkg : exit $LASTEXITCODE"
        } else {
            Write-Host "    installed $pkg (uv tool)"
        }
    }
}

function Install-AgentsMd {
    $script = Join-Path $RepoRoot 'dotfiles\install-agents.py'
    $pyArgs = @($script)
    if ($DryRun) { $pyArgs += '--dry-run' }
    if ($Force) { $pyArgs += '--force' }
    if (Test-ToolUsable 'python') {
        & python @pyArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    FAIL install-agents.py : python exit $LASTEXITCODE"
        }
        return
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 @pyArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    FAIL install-agents.py : py -3 exit $LASTEXITCODE"
        }
        return
    }
    Write-Host '    FAIL: python not on PATH (install Python first)'
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Error 'winget not found -- install App Installer from the Microsoft Store first.'
    exit 1
}

Write-Host '==> dev tools (winget)'
foreach ($t in $Tools) {
    Install-WingetTool -Id $t.Id -Cmd $t.Cmd
}

Write-Host '==> fzf (winget, go-build fallback)'
Install-Fzf

Write-Host '==> python tools (ruff, mypy) via uv'
Install-UvTools

Write-Host '==> user-wide AGENTS.md (OpenCode pointer)'
Install-AgentsMd

Write-Host 'Done. Restart the shell so the new PATH entries take effect.'
Write-Host 'Then run windows/scripts/install-profile.ps1 for the PowerShell profile.'
