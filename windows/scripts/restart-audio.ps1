# Restart ROG/Windows audio when the Cirrus speaker amp dies and a tinny
# motherboard device (Intel SST / HD Audio) takes over.
#
# Recycles Cirrus Logic Awesome Speaker Amps, the Realtek codec, related
# vendor services, and the Windows Audio stack. Does not uninstall drivers
# or change the default playback device.
#
# Needs Administrator. Self-elevates via UAC if launched unelevated.
#
# Run:
#   powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/restart-audio.ps1
#   powershell ... -File windows/scripts/restart-audio.ps1 -NoPause
#
# Or right-click the .ps1 -> Run with PowerShell. Waits for Enter unless -NoPause.

[CmdletBinding()]
param(
    [switch]$NoPause
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`""
    )
    if ($NoPause) { $argList += "-NoPause" }
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argList
    exit 0
}

function Write-Step([string]$Message) {
    Write-Host "==> $Message"
}

function Restart-NamedService([string]$Name) {
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "    skip service $Name (not installed)"
        return
    }
    try {
        Restart-Service -Name $Name -Force -ErrorAction Stop
        $after = Get-Service -Name $Name
        Write-Host "    $($after.Name) -> $($after.Status)"
    } catch {
        Write-Host "    FAIL $Name : $($_.Exception.Message)"
    }
}

function Restart-NamedDevice([string]$InstanceId, [string]$FriendlyName) {
    Write-Host "    recycle $FriendlyName"
    try {
        Disable-PnpDevice -InstanceId $InstanceId -Confirm:$false -ErrorAction Stop
        Start-Sleep -Seconds 2
        Enable-PnpDevice -InstanceId $InstanceId -Confirm:$false -ErrorAction Stop
        Start-Sleep -Seconds 2
        $after = Get-PnpDevice -InstanceId $InstanceId -ErrorAction Stop
        Write-Host "    $($after.Status)  $FriendlyName"
    } catch {
        Write-Host "    FAIL $FriendlyName : $($_.Exception.Message)"
    }
}

Write-Step "PnP devices (Cirrus amp + Realtek codec)"
$deviceFilter = "Cirrus Logic Awesome Speaker Amps|Realtek High Definition Audio|^Realtek\(R\) Audio$"
$devices = @(Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object {
    $_.FriendlyName -match $deviceFilter -and $_.Class -match "MEDIA|System"
})
if ($devices.Count -eq 0) {
    Write-Host "    no Cirrus/Realtek MEDIA devices found"
} else {
    foreach ($d in $devices) {
        Restart-NamedDevice -InstanceId $d.InstanceId -FriendlyName $d.FriendlyName
    }
}

Write-Step "Vendor audio services"
Restart-NamedService "RtkAudioUniversalService"
Restart-NamedService "IntelAudioService"
Restart-NamedService "DolbyDAXAPI"

Write-Step "Windows Audio stack"
Restart-NamedService "AudioEndpointBuilder"
Start-Sleep -Seconds 1
Restart-NamedService "Audiosrv"

Write-Step "Status"
Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object {
    $_.FriendlyName -match "Cirrus|Realtek\(R\) Audio$|Speakers \(Realtek|Smart Sound"
} | Format-Table Status, Class, FriendlyName -AutoSize | Out-String | Write-Host

Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue |
    Format-Table Status, FriendlyName -AutoSize | Out-String | Write-Host

Write-Host "Done. If it is still tinny, pick Speakers (Realtek) in Settings > System > Sound."

if (-not $NoPause) {
    Read-Host "Press Enter to close"
}
