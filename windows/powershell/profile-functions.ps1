# =============================================================================
#  profile-functions.ps1  --  reusable shell functions
#
#  Dot-sourced by Microsoft.PowerShell_profile.ps1 (the hub). Add your own
#  below. Mirrors dotfiles/bash/.bash_functions.
# =============================================================================

Set-StrictMode -Version Latest

# --- cd + ls ------------------------------------------------------------------
# cdl <dir>  -> change directory, then list it
function cdl([string]$Dir) { Set-Location $Dir; Get-ChildItem }

# mkcd <dir> -> make a directory (and parents) then cd into it
function mkcd([string]$Dir) { New-Item -ItemType Directory -Force -Path $Dir | Out-Null; Set-Location $Dir }

# up [n] -> go up n directories (default 1); stops silently at the drive root
function up([int]$Depth = 1) {
    $target = (Get-Location).Path
    for ($i = 0; $i -lt $Depth; $i++) {
        $parent = Split-Path $target -ErrorAction SilentlyContinue
        if (-not $parent) { break }
        $target = $parent
    }
    Set-Location $target
}

# --- Archives -------------------------------------------------------------------
# extract <file> -> unpack whatever it is (needs 7-Zip for .7z/.rar)
function extract([string]$Archive) {
    if (-not (Test-Path $Archive)) { Write-Error "extract: no such file: $Archive"; return }
    switch -Regex ($Archive) {
        '\.zip$' { Expand-Archive $Archive -DestinationPath .; break }
        '\.7z$|\.rar$' {
            if (-not (Get-Command 7z -ErrorAction SilentlyContinue)) {
                Write-Error 'extract: 7z not found (winget: 7zip.7zip)'; return
            }
            7z x $Archive; break
        }
        '\.tar\.gz$|\.tgz$' { tar xzf $Archive; break }
        '\.tar$' { tar xf $Archive; break }
        default { Write-Error "extract: unsupported archive type: $Archive" }
    }
}

# --- Files ------------------------------------------------------------------------
# backup <file>... -> make timestamped .bak copies
function backup([string[]]$Files) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    foreach ($f in $Files) {
        if (-not (Test-Path $f)) { Write-Error "backup: no such file: $f"; continue }
        Copy-Item $f "$f.bak.$stamp"
    }
}

# findhere <pattern> -> case-insensitive filename search, ignoring .git
function findhere([string]$Pattern) {
    Get-ChildItem -Recurse -Filter "*$Pattern*" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\.git' } |
        Select-Object -First 50
}

# --- Dev ----------------------------------------------------------------------------
# serve [port] -> static file server in the current directory
function serve([int]$Port = 8000) { python -m http.server $Port }

# --- System -----------------------------------------------------------------------------
# repeat <seconds> <cmd...> -> run a command every N seconds
function repeat([int]$Interval = 2, [Parameter(ValueFromRemainingArguments=$true)][string[]]$rest) {
    if (-not $rest) { Write-Error 'usage: repeat <seconds> <command...>'; return }
    while ($true) {
        Clear-Host
        Invoke-Expression ($rest -join ' ')
        Start-Sleep -Seconds $Interval
    }
}

# sysinfo -> motd-ish summary of the machine
function sysinfo {
    Write-Host '== host =='; hostname
    Write-Host '== os =='; (Get-CimInstance Win32_OperatingSystem).Caption
    Write-Host '== cpu =='; (Get-CimInstance Win32_Processor).Name | Select-Object -First 1
    Write-Host '== mem =='; Get-CimInstance Win32_OperatingSystem |
        Select-Object TotalVisibleMemorySize, FreePhysicalMemory
    Write-Host '== disk =='; Get-PSDrive -PSProvider FileSystem
}
