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

# winget Gradle.Gradle puts gradle on PATH. Unpacked zip (Linux-style) is optional.
if (-not $env:GRADLE_HOME) {
    $opt = Join-Path $HOME '.local\opt'
    if (Test-Path $opt) {
        $localGradle = @(Get-ChildItem $opt -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like 'gradle-*' -and (Test-Path (Join-Path $_.FullName 'bin\gradle.bat')) } |
                Sort-Object Name -Descending | Select-Object -First 1)
        if ($localGradle) { $env:GRADLE_HOME = $localGradle.FullName }
    }
}
if (($env:GRADLE_HOME) -and (Test-Path (Join-Path $env:GRADLE_HOME 'bin\gradle.bat'))) {
    Add-PathPrefix (Join-Path $env:GRADLE_HOME 'bin')
}

# $env:ANDROID_HOME = "$HOME\AppData\Local\Android\Sdk"
# if (Test-Path $env:ANDROID_HOME) { Add-PathPrefix (Join-Path $env:ANDROID_HOME 'platform-tools') }

# ---------------------------------------------------------------------------
#  Languages -- per-tool homes plus their bins (all guarded)
# ---------------------------------------------------------------------------
# Go (winget installs to Program Files; default GOPATH bin is per-user)
if (Test-Path "$HOME\go\bin") { Add-PathPrefix "$HOME\go\bin" }

# Rust (cargo)
if (Test-Path "$HOME\.cargo\bin") { Add-PathPrefix "$HOME\.cargo\bin" }

# uv tool binaries (ruff, mypy). OpenCode formatter needs this on PATH too;
# install-tools.ps1 also persists it on the user PATH.
if (Test-Path "$HOME\.local\bin") { Add-PathPrefix "$HOME\.local\bin" }

# Python -- pip --user. Enumerate the versioned directories rather than naming
# one: the interpreter is reinstalled and upgraded over time, and a hardcoded
# Python3xx silently stops matching, which leaves pip's console scripts off PATH
# with no error to notice it by.
$PythonUserBase = "$HOME\AppData\Roaming\Python"
if (Test-Path $PythonUserBase) {
    # Two things this sort has to get right, both learned the hard way.
    # Parse Python<major><minor> into a real version: Python39 sorts AFTER
    # Python314 as text but is five releases older, so a name sort hands
    # priority to the oldest interpreter. Casting the bare digits to [version]
    # throws on "39" because a version needs a dot, which kills profile load
    # under StrictMode, so major and minor are reassembled with a dot. Then
    # iterate OLDEST first, because Add-PathPrefix prepends - the last
    # directory in wins the head of PATH, so walking up to the newest is what
    # leaves the newest Scripts directory in front.
    Get-ChildItem $PythonUserBase -Directory -ErrorAction SilentlyContinue |
        Sort-Object {
            if ($_.Name -match '^Python(\d)(\d+)$') {
                [version]::new("$($Matches[1]).$($Matches[2])")
            }
            else { [version]'0.0' }
        } |
        ForEach-Object {
            $Scripts = Join-Path $_.FullName 'Scripts'
            if (Test-Path $Scripts) { Add-PathPrefix $Scripts }
        }
}

# The interpreter itself, not just its scripts. uv-managed CPython lives under
# Roaming\uv\python\cpython-<version>-<build>, where the patch and build are part
# of the directory name, so the directories are enumerated and the 3.12 line is
# selected rather than one full path being named. Naming it would rot on the next
# patch release with nothing to notice it by.
#
# 3.12 and not "newest" on purpose: CI pins python-version 3.12 and both repos
# target py312 in ruff.toml, so this is the interpreter the work is verified
# against. Leaving the newest here lets a test pass on an interpreter CI never
# runs, which is how the json decoder difference between 3.12 and 3.14 shipped a
# test that only held on the machine that wrote it.
$UvPythonBase = "$HOME\AppData\Roaming\uv\python"
if (Test-Path $UvPythonBase) {
    $Newest312 = Get-ChildItem $UvPythonBase -Directory -Filter 'cpython-3.12*' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        Where-Object { Test-Path (Join-Path $_.FullName 'python.exe') } |
        Select-Object -First 1
    if ($Newest312) { Add-PathPrefix $Newest312.FullName }
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
