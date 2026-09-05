# =============================================================================
#  profile-env.ps1  --  THE file for environment variables and PATH
#
#  Dot-sourced by Microsoft.PowerShell_profile.ps1 (the hub). This is the
#  single place to add/change JAVA_HOME, MAVEN_HOME, GOPATH, and personal
#  PATH entries. Mirrors dotfiles/bash/.bash_env.
#
#  PATH rule: prepend (`$env:PATH = "X;$env:PATH"`) so your tool wins,
#  append (`$env:PATH += ";X"`) to only add a fallback. Never drop the
#  existing $env:PATH. Every entry below is guarded by Test-Path so a
#  missing tool is simply ignored on a fresh machine.
# =============================================================================

Set-StrictMode -Version Latest

function Add-PathPrefix([string]$Dir) {
    if (-not $Dir) { return }
    if (-not (Test-Path $Dir)) { return }
    # Exact, case-insensitive match on the split list (no substring games).
    if ((($env:PATH -split ';') -notcontains $Dir)) {
        $env:PATH = "$Dir;$env:PATH"
    }
}

# ---------------------------------------------------------------------------
#  JAVA_HOME -- auto-detect the newest Temurin/Adoptium or Oracle JDK.
#  To pin a version instead, comment this out and set an explicit path:
#      $env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.7.6-hotspot'
# ---------------------------------------------------------------------------
# Option A (recommended): auto-detect the newest JDK. Prefers real JDKs over
# JREs and compares numerically so jdk-21 beats jdk-9 (plain name sort fails).
function Find-BestJavaHome([string[]]$Roots) {
    $cands = @()
    foreach ($root in $Roots) {
        if (Test-Path $root) {
            $cands += @(Get-ChildItem $root -Directory -ErrorAction SilentlyContinue |
                Where-Object { Test-Path (Join-Path $_.FullName 'bin\java.exe') })
        }
    }
    $jdks = @($cands | Where-Object { $_.Name -like 'jdk*' })
    $pool = if ($jdks.Count -gt 0) { $jdks } else { $cands }
    return ($pool | Sort-Object {
        $m = [regex]::Match($_.Name, '\d+(\.\d+)*')
        if ($m.Success) { [version]$m.Value } else { [version]'0.0' }
    } -Descending | Select-Object -First 1)
}
$bestJava = Find-BestJavaHome @(
    'C:\Program Files\Eclipse Adoptium',
    'C:\Program Files\Java',
    'C:\Program Files (x86)\Java'
)
if ($bestJava) { $env:JAVA_HOME = $bestJava.FullName }
if (($env:JAVA_HOME) -and (Test-Path (Join-Path $env:JAVA_HOME 'bin\java.exe'))) {
    Add-PathPrefix (Join-Path $env:JAVA_HOME 'bin')
}

# ---------------------------------------------------------------------------
#  Other JVM-family tools (same pattern: *_HOME + bin on PATH)
# ---------------------------------------------------------------------------
if (-not $env:MAVEN_HOME) { $env:MAVEN_HOME = "$HOME\tools\apache-maven-3.9.9" }
if (Test-Path $env:MAVEN_HOME) { Add-PathPrefix (Join-Path $env:MAVEN_HOME 'bin') }

# $env:GRADLE_HOME = "$HOME\tools\gradle-8.10.2"
# if (Test-Path $env:GRADLE_HOME) { Add-PathPrefix (Join-Path $env:GRADLE_HOME 'bin') }

# $env:ANDROID_HOME = "$HOME\AppData\Local\Android\Sdk"
# if (Test-Path $env:ANDROID_HOME) { Add-PathPrefix (Join-Path $env:ANDROID_HOME 'platform-tools') }

# ---------------------------------------------------------------------------
#  Languages -- per-tool homes plus their bins (all guarded)
# ---------------------------------------------------------------------------
# Go (winget installs to Program Files; default GOPATH bin is per-user)
if (Test-Path "$HOME\go\bin") { Add-PathPrefix "$HOME\go\bin" }

# Rust (cargo)
if (Test-Path "$HOME\.cargo\bin") { Add-PathPrefix "$HOME\.cargo\bin" }

# Python -- pip --user and uv put binaries here
if (Test-Path "$HOME\AppData\Roaming\Python\Python312\Scripts") {
    Add-PathPrefix "$HOME\AppData\Roaming\Python\Python312\Scripts"
}

# Node -- npm globals land here
if (Test-Path "$HOME\AppData\Roaming\npm") { Add-PathPrefix "$HOME\AppData\Roaming\npm" }

# ---------------------------------------------------------------------------
#  YOUR personal PATH entries -- uncomment and adapt. Examples:
#      Add-PathPrefix "$HOME\bin"
#      Add-PathPrefix "$HOME\tools\bin"
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
#  Misc environment
# ---------------------------------------------------------------------------
if (-not $env:EDITOR) { $env:EDITOR = 'notepad' }
if (-not $env:PAGER) { $env:PAGER = 'more' }
