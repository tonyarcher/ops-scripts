# deploy-ops-vpn.ps1 — Windows entry for sites/vpn/deploy.py
#
# What: finds Python and runs the VPN compose driver (SSH tunnel + compose).
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/deploy-ops-vpn.ps1 --remote up
#       powershell ... -File windows/scripts/deploy-ops-vpn.ps1 peer laptop
#       powershell ... -File windows/scripts/deploy-ops-vpn.ps1 lock-ssh
#
# Copy sites/vpn/.env.example to sites/vpn/.env and set VPN_HOST first.
# Needs docker (Rancher Desktop) and OpenSSH (`ssh`).

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$DeployArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Script = Join-Path $RepoRoot 'sites\vpn\deploy.py'

function Invoke-Python([string[]]$PyArgs) {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python @PyArgs
        return $LASTEXITCODE
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 @PyArgs
        return $LASTEXITCODE
    }
    Write-Error 'python not found'
    return 1
}

if (-not (Test-Path $Script)) {
    Write-Error "missing $Script"
    exit 1
}

$code = Invoke-Python (@($Script) + @($DeployArgs))
exit $code
