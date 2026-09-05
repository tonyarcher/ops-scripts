# =============================================================================
#  profile-aliases.ps1  --  command shortcuts
#
#  Dot-sourced by Microsoft.PowerShell_profile.ps1 (the hub). One shortcut
#  per line with a short comment. Mirrors dotfiles/bash/.bash_aliases.
#  Built-in file aliases (rm, cp, mv, ...) are left alone on purpose; only
#  the gc/gp content aliases are replaced (see the git section).
# =============================================================================

Set-StrictMode -Version Latest

# --- listing ------------------------------------------------------------------
function ll { Get-ChildItem -Force @args }          # long, incl. hidden
function la { Get-ChildItem -Force -Name @args }    # names only, incl. hidden
function l1 { Get-ChildItem -Name @args }           # one entry per line
function lt { Get-ChildItem | Sort-Object LastWriteTime @args }

# Modern replacement (winget: eza-community.eza)
if (Get-Command eza -ErrorAction SilentlyContinue) {
    function ll { eza -lah --group-directories-first --git @args }
    function la { eza -a --group-directories-first @args }
    function l1 { eza -1 --group-directories-first @args }
    function lt { eza -lahT --level=2 --group-directories-first @args }
    function tree { eza -lahT --group-directories-first @args }
}

# --- navigation -----------------------------------------------------------------
function .. { Set-Location .. }              # up one
function ... { Set-Location ..\.. }          # up two
function .... { Set-Location ..\..\.. }      # up three
function home { Set-Location ~ }             # back home
# back -> previous directory (tracked in prompt; `Set-Location -` needs PS 6.2+)
function back {
    if (($global:__prevDir) -and (Test-Path $global:__prevDir)) {
        $cur = (Get-Location).Path
        Set-Location $global:__prevDir
        $global:__prevDir = $cur
        $global:__lastDir = $cur
    } else {
        Write-Host 'back: no previous directory yet'
    }
}

# --- search (winget: BurntSushi.ripgrep.MSVC) --------------------------------------
function rg-smart { rg --smart-case --hidden @args }

# --- git ----------------------------------------------------------------------------
# NOTE: gc/gp are built-in PowerShell aliases (Get-Content/Get-ItemProperty)
# and aliases win over functions, so these two are removed first. This is
# opt-in (you installed this profile); restore with `Set-Alias gc Get-Content`.
Remove-Item Alias:gc -Force -ErrorAction SilentlyContinue
Remove-Item Alias:gp -Force -ErrorAction SilentlyContinue
function g { git @args }
function gs { git status @args }
function gst { git stash @args }
function gstp { git stash pop @args }
function ga { git add @args }
function gaa { git add --all @args }
function gc { git commit -m @args }
function gca { git commit --amend --no-edit @args }
function gp { git push @args }
function gpull { git pull --rebase @args }
function gl { git log --oneline --graph --decorate -20 @args }
function gd { git diff @args }
function gds { git diff --staged @args }
function gb { git branch -vv @args }
function gco { git checkout @args }
function gcb { git checkout -b @args }
# DANGER ZONE -- discards ALL local changes and untracked files
function gundo { git reset --hard HEAD; git clean -fd @args }

# --- docker ---------------------------------------------------------------------------
if (Get-Command docker -ErrorAction SilentlyContinue) {
    function dc { docker compose @args }
    function dps { docker ps @args }
    function dlogs { docker logs -f --tail 100 @args }
    function dsh { docker exec -it @args }   # dsh <container> powershell
}

# --- system ------------------------------------------------------------------------------
function mem { Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory }
function disk { Get-PSDrive -PSProvider FileSystem }
function ports { netstat -ano @args }
function psg {   # psg java -> find a process (usage printed with no args)
    if (-not $args.Count) { Write-Host 'usage: psg <name>'; return }
    Get-Process | Where-Object { $_.ProcessName -match $args[0] }
}

# --- misc -------------------------------------------------------------------------------
function reload { . $PROFILE }               # re-read the profile hub
function paths { $env:PATH -split ';' }      # print PATH one entry per line
