# connect-ops-vpn.ps1 — import or start a WireGuard client profile on Windows.
#
# What: copies a .conf from the VPN server into WireGuard and optionally
#       installs the tunnel service. Does not download WireGuard.
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/connect-ops-vpn.ps1 -Config .\laptop.conf
#       powershell ... -File windows/scripts/connect-ops-vpn.ps1 -Config .\laptop.conf -Connect
#
# Get the profile (contains a private key):
#   bash sites/vpn/deploy.sh peer laptop > laptop.conf
# Needs WireGuard for Windows. -Connect requires Administrator.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Config,
    [switch]$Connect
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Find-WireGuard {
    $candidates = @()
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles "WireGuard\wireguard.exe")
    }
    $x86 = ${env:ProgramFiles(x86)}
    if ($x86) {
        $candidates += (Join-Path $x86 "WireGuard\wireguard.exe")
    }
    foreach ($path in $candidates) {
        if (Test-Path $path) {
            return $path
        }
    }
    return $null
}

$resolved = (Resolve-Path $Config).Path
$wg = Find-WireGuard
if (-not $wg) {
    Write-Error "wireguard.exe not found. Install WireGuard for Windows, then Import tunnel from file: $resolved"
    exit 1
}

$destDir = Join-Path $env:USERPROFILE "ops-vpn"
New-Item -ItemType Directory -Force -Path $destDir | Out-Null
$dest = Join-Path $destDir (Split-Path $resolved -Leaf)
Copy-Item -Force $resolved $dest
Write-Host "Copied profile to $dest"
Write-Host "In WireGuard: Import tunnel(s) from file -> $dest"

if (-not $Connect) {
    exit 0
}
if (-not (Test-IsAdmin)) {
    Write-Error "-Connect needs Administrator (UAC). Import in the WireGuard GUI instead."
    exit 1
}

Write-Host "==> wireguard /installtunnelservice $dest"
& $wg /installtunnelservice $dest
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
