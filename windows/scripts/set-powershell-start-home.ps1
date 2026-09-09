# Set PowerShell's default opening directory to the user home folder.
# Patches Start Menu / Desktop / taskbar shortcuts (powershell.exe / pwsh.exe)
# and Windows Terminal PowerShell profiles. Does not touch cmd, WSL, or ISE.
#
# Needs no admin for user-scope shortcuts and Terminal settings. ProgramData
# shortcuts are skipped if this process cannot write them.
#
# The PowerShell profile also cds to $HOME when a host dumps the session in
# System32 (admin / empty "Start in"). Install that with install-profile.ps1.
#
# Run from the repo root:
#   powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/set-powershell-start-home.ps1
#   powershell ... -File windows/scripts/set-powershell-start-home.ps1 -WhatIf
#
# Does not change Explorer "Open here" or IDE terminals.

[CmdletBinding(SupportsShouldProcess = $true)]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$HomeDir = $env:USERPROFILE
if (-not $HomeDir) { throw 'USERPROFILE is not set' }
$WtStartDir = '%USERPROFILE%'

function Get-PowerShellShortcutPaths {
    $roots = @(
        (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu'),
        (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu'),
        (Join-Path $HomeDir 'Desktop'),
        (Join-Path $HomeDir 'OneDrive\Desktop'),
        (Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'),
        (Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\Start Menu')
    )
    $out = @()
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $out += @(Get-ChildItem $root -Recurse -Filter '*.lnk' -ErrorAction SilentlyContinue)
    }
    return $out
}

function Get-JsonObjectSpan {
    param(
        [string]$Text,
        [string]$Guid
    )
    $needleRe = [regex]('"guid"\s*:\s*"' + [regex]::Escape($Guid) + '"')
    $m = $needleRe.Match($Text)
    if (-not $m.Success) { return $null }

    $inString = $false
    $escape = $false
    $stack = New-Object System.Collections.Generic.List[int]
    for ($i = 0; $i -lt $m.Index; $i++) {
        $c = $Text[$i]
        if ($inString) {
            if ($escape) { $escape = $false; continue }
            if ($c -eq [char]0x5C) { $escape = $true; continue }
            if ($c -eq '"') { $inString = $false }
            continue
        }
        if ($c -eq '"') { $inString = $true; continue }
        if ($c -eq '{') { $stack.Add($i) }
        elseif ($c -eq '}') {
            if ($stack.Count -gt 0) { $stack.RemoveAt($stack.Count - 1) }
        }
    }
    if ($stack.Count -eq 0) { return $null }
    $start = $stack[$stack.Count - 1]

    $inString = $false
    $escape = $false
    $depth = 0
    $end = -1
    for ($i = $start; $i -lt $Text.Length; $i++) {
        $c = $Text[$i]
        if ($inString) {
            if ($escape) { $escape = $false; continue }
            if ($c -eq [char]0x5C) { $escape = $true; continue }
            if ($c -eq '"') { $inString = $false }
            continue
        }
        if ($c -eq '"') { $inString = $true; continue }
        if ($c -eq '{') { $depth++ }
        elseif ($c -eq '}') {
            $depth--
            if ($depth -eq 0) { $end = $i; break }
        }
    }
    if ($end -lt 0) { return $null }
    return @{
        Start  = $start
        Length = ($end - $start + 1)
        Text   = $Text.Substring($start, $end - $start + 1)
    }
}

function Set-JsonStringProperty {
    param(
        [string]$Json,
        [string]$Guid,
        [string]$Name,
        [string]$Value
    )
    $span = Get-JsonObjectSpan -Text $Json -Guid $Guid
    if (-not $span) {
        Write-Warning "Windows Terminal: could not locate profile object for $Guid"
        return $Json
    }
    $block = $span.Text
    $desired = '"' + $Name + '": "' + $Value + '"'
    $propRe = [regex]('"' + [regex]::Escape($Name) + '"\s*:\s*"[^"]*"')
    if ($propRe.IsMatch($block)) {
        $current = $propRe.Match($block).Value
        if ($current -eq $desired) { return $Json }
        $newBlock = $propRe.Replace($block, $desired, 1)
    } else {
        $inner = $block.Substring(0, $block.Length - 1).TrimEnd()
        if ($inner.Length -eq 0) {
            Write-Warning "Windows Terminal: empty profile object for $Guid"
            return $Json
        }
        if ($inner[$inner.Length - 1] -ne ',') { $inner += ',' }
        $nlMatch = [regex]::Match($block, '\r?\n')
        $nl = if ($nlMatch.Success) { $nlMatch.Value } else { "`r`n" }
        $indent = '                '
        $indentMatch = [regex]::Match($block, '(?m)^([ \t]+)"')
        if ($indentMatch.Success) { $indent = $indentMatch.Groups[1].Value }
        $closeIndent = '            '
        $closeMatch = [regex]::Match($block, '(?m)^([ \t]*)\}$')
        if ($closeMatch.Success) { $closeIndent = $closeMatch.Groups[1].Value }
        $newBlock = $inner + $nl + $indent + $desired + $nl + $closeIndent + '}'
    }
    return $Json.Remove($span.Start, $span.Length).Insert($span.Start, $newBlock)
}

function Get-WtPowerShellGuids {
    param([string]$Raw)
    $guids = New-Object System.Collections.Generic.List[string]
    try {
        $parsed = $Raw | ConvertFrom-Json
        foreach ($p in @($parsed.profiles.list)) {
            $cmd = ''
            $src = ''
            if ($p.PSObject.Properties['commandline']) { $cmd = [string]$p.commandline }
            if ($p.PSObject.Properties['source']) { $src = [string]$p.source }
            $isPs = ($cmd -match '(?i)[\\/](powershell|pwsh)\.exe') -or
                    ($src -eq 'Windows.Terminal.PowershellCore')
            if ($isPs -and $p.PSObject.Properties['guid']) {
                $guids.Add([string]$p.guid)
            }
        }
    } catch {
        foreach ($g in @(
                '{61c54bbd-c2c6-5271-96e7-009a87ff44bf}',
                '{574e775e-4f2a-5b96-ac1e-a2962a402336}'
            )) {
            if ($Raw -like "*$g*") { $guids.Add($g) }
        }
    }
    return @($guids)
}

# --- 1. Shortcuts (Start in = user home) ---------------------------------------
$sh = New-Object -ComObject WScript.Shell
$shortcutCount = 0
foreach ($lnkFile in Get-PowerShellShortcutPaths) {
    $lnk = $sh.CreateShortcut($lnkFile.FullName)
    $target = [string]$lnk.TargetPath
    if ($target -notmatch '(?i)[\\/](powershell|pwsh)\.exe$') { continue }
    if ([string]$lnk.WorkingDirectory -eq $HomeDir) { continue }
    if ($PSCmdlet.ShouldProcess($lnkFile.FullName, "Set WorkingDirectory to $HomeDir")) {
        try {
            $lnk.WorkingDirectory = $HomeDir
            $lnk.Save()
            Write-Host "    shortcut $($lnkFile.Name) -> $HomeDir"
            $shortcutCount += 1
        } catch {
            Write-Host "    skip $($lnkFile.FullName): $($_.Exception.Message)"
        }
    }
}

# --- 2. Windows Terminal PowerShell profiles -----------------------------------
$wtPaths = @(
    (Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json'),
    (Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json'),
    (Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\settings.json')
)
$wtCount = 0
foreach ($wtPath in $wtPaths) {
    if (-not (Test-Path $wtPath)) { continue }
    $raw = [System.IO.File]::ReadAllText($wtPath)
    $guids = @(Get-WtPowerShellGuids -Raw $raw)
    $new = $raw
    foreach ($guid in $guids) {
        $new = Set-JsonStringProperty -Json $new -Guid $guid -Name 'startingDirectory' -Value $WtStartDir
    }
    foreach ($guid in $guids) {
        $span = Get-JsonObjectSpan -Text $new -Guid $guid
        if (-not $span) {
            Write-Warning "Windows Terminal: profile $guid was not patched"
            continue
        }
        $desired = '"startingDirectory": "' + $WtStartDir + '"'
        if ($span.Text -notlike "*$desired*") {
            Write-Warning "Windows Terminal: profile $guid startingDirectory not set to $WtStartDir"
        }
    }
    if ($new -eq $raw) { continue }
    if ($PSCmdlet.ShouldProcess($wtPath, "Set PowerShell startingDirectory to $WtStartDir")) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $bak = "$wtPath.bak-$stamp"
        Copy-Item $wtPath $bak -Force
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($wtPath, $new, $utf8)
        Write-Host "    terminal $wtPath (backup $bak)"
        $wtCount += 1
    }
}

if ($WhatIfPreference) { return }

Write-Host '============================================================'
Write-Host " PowerShell default directory: $HomeDir"
Write-Host " Shortcuts updated: $shortcutCount"
Write-Host " Windows Terminal files updated: $wtCount"
Write-Host ' Profile fallback (System32 -> home): install-profile.ps1'
Write-Host ' Open a new shell to pick this up.'
Write-Host '============================================================'
