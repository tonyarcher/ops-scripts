# Map a LAN hostname to its IP in the Windows hosts file so Chrome (and ping,
# curl, SSH) resolve it without router DNS. Idempotent: existing mapping is
# a no-op. Backs up hosts before writing. Needs Administrator (self-elevates).
#
# Run from the repo root:
#   powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/add-lan-host.ps1
#   powershell ... -File windows/scripts/add-lan-host.ps1 -Ip 10.0.0.63 -Hostname thinkpad.lan
#   powershell ... -File windows/scripts/add-lan-host.ps1 -WhatIf
#
# Defaults match sites/hosts/hosts.json (thinkpad -> thinkpad.lan 10.0.0.63).
# Afterward: restart Chrome (it caches DNS) and open https://thinkpad.lan/ .
# Or right-click the .ps1 -> Run with PowerShell (UAC prompt appears).

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Ip = "10.0.0.63",
    [string]$Hostname = "thinkpad.lan"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$HostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
$Marker = "# ops-scripts lan-host"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-HostMapped {
    param([string]$Path, [string]$Addr, [string]$Name)
    if (-not (Test-Path $Path)) { return $false }
    $escapedIp = [regex]::Escape($Addr)
    $escapedName = [regex]::Escape($Name)
    $lines = Get-Content $Path
    foreach ($line in $lines) {
        if ($line -match "^\s*#") { continue }
        if ($line -match "^\s*$escapedIp\s+.*\b$escapedName\b") { return $true }
    }
    return $false
}

if ([string]::IsNullOrWhiteSpace($Ip) -or [string]::IsNullOrWhiteSpace($Hostname)) {
    Write-Error "Ip and Hostname must not be blank."
    exit 1
}

if (Test-HostMapped -Path $HostsPath -Addr $Ip -Name $Hostname) {
    Write-Host "already mapped: $Ip $Hostname"
    exit 0
}

if (-not (Test-IsAdmin) -and -not $WhatIfPreference) {
    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-Ip", "`"$Ip`"",
        "-Hostname", "`"$Hostname`""
    )
    if ($WhatIfPreference) { $argList += "-WhatIf" }
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argList
    exit 0
}

if ($PSCmdlet.ShouldProcess($HostsPath, "Add '$Ip $Hostname'")) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item $HostsPath "$HostsPath.bak-$stamp" -Force
    Add-Content -Path $HostsPath -Value "$Ip`t$Hostname`t$Marker" -Encoding Ascii
    Write-Host "added: $Ip $Hostname (backup $HostsPath.bak-$stamp)"
    try {
        ipconfig /flushdns | Out-Null
    } catch {
        Write-Host "    note: ipconfig /flushdns failed: $($_.Exception.Message)"
    }
}

if ($WhatIfPreference) { return }

Write-Host "Restart Chrome (it caches DNS), then open https://$Hostname/ ."
