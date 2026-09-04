# deploy-opencode-docker.ps1 — build + run the opencode Docker image (Windows)
#
# What: wraps `docker compose` with env checks and friendly errors.
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File windows/scripts/deploy-opencode-docker.ps1
#       powershell ... -File windows/scripts/deploy-opencode-docker.ps1 -Command up -WithJava
#       powershell ... -File windows/scripts/deploy-opencode-docker.ps1 -Command shell
#
# Env:  reads sites/opencode/docker-image/.env (created from .env.example if missing).
#       Provider keys (XAI_API_KEY, etc.) must be set in .env — never baked.
# Params:
#   -Command  build|up|down|restart|logs|shell|clean|config|ps  (default: up)
#   -WithJava switch to build with JDK/Maven/Gradle
#   -ExtraArgs passthrough to docker compose

[CmdletBinding()]
param(
    [ValidateSet("build", "up", "down", "restart", "logs", "shell", "clean", "config", "ps")]
    [string]$Command = "up",
    [switch]$WithJava,
    [string[]]$ExtraArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ImageDir = Join-Path $RepoRoot "sites\opencode\docker-image"
$ComposeFile = Join-Path $ImageDir "docker-compose.yml"
$EnvFile = Join-Path $ImageDir ".env"
$EnvExample = Join-Path $ImageDir ".env.example"

function Test-Cmd($name) {
    $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Test-Cmd "docker")) {
    Write-Error "docker not found. Install Docker Desktop."
    exit 1
}
docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "'docker compose' (v2) not found. Update Docker Desktop."
    exit 1
}
if (-not (Test-Path $ComposeFile)) {
    Write-Error "Compose file not found: $ComposeFile"
    exit 1
}

if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Host "Created $EnvFile from .env.example — edit provider keys before running." -ForegroundColor Yellow
        Write-Host "  notepad $EnvFile"
    } else {
        Write-Error "No $EnvFile and no .env.example found — cannot start."
        exit 1
    }
}
if (Test-Path $EnvFile) {
    $hasKey = Select-String -Path $EnvFile -Pattern "API_KEY=.+|GITHUB_TOKEN=.+" -Quiet 2>$null
    if (-not $hasKey) {
        Write-Host "note: $EnvFile has no API keys set. opencode will run but models will fail." -ForegroundColor Yellow
        Write-Host "      Fill XAI_API_KEY / OPENCODE_GO_API_KEY etc. in $EnvFile"
    }
}

if ($WithJava) {
    $env:WITH_JAVA = "true"
    Write-Host "Building with Java (WITH_JAVA=true)" -ForegroundColor Cyan
}

function Invoke-Compose([string[]]$ComposeArgs) {
    if (Test-Path $EnvFile) {
        $all = @("compose", "-f", $ComposeFile, "--env-file", $EnvFile) + $ComposeArgs
    } else {
        $all = @("compose", "-f", $ComposeFile) + $ComposeArgs
    }
    Write-Host "==> docker $($all -join ' ')" -ForegroundColor DarkGray
    & docker @all
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# Helper: safely concatenate base args + ExtraArgs (handles $null)
function Invoke-ComposeWithExtra([string[]]$BaseArgs) {
    $extra = @()
    if ($null -ne $ExtraArgs -and $ExtraArgs.Count -gt 0) { $extra = $ExtraArgs }
    Invoke-Compose ($BaseArgs + $extra)
}

switch ($Command) {
    "build"   { Invoke-ComposeWithExtra @("build") }
    "up"      {
        Invoke-ComposeWithExtra @("up", "--build", "-d")
        Write-Host "==> ok. Try:" -ForegroundColor Green
        Write-Host "    docker compose -f $ComposeFile exec opencode bash"
        Write-Host "    docker compose -f $ComposeFile logs -f"
        Invoke-Compose @("ps")
    }
    "down"    { Invoke-ComposeWithExtra @("down") }
    "restart" { Invoke-ComposeWithExtra @("restart") }
    "logs"    {
        if (-not $ExtraArgs -or $ExtraArgs.Count -eq 0) { $ExtraArgs = @("-f") }
        Invoke-Compose (@("logs") + $ExtraArgs)
    }
    "shell"   { Invoke-ComposeWithExtra @("exec", "opencode", "bash") }
    "clean"   {
        Write-Host "==> stopping and removing image + volume..." -ForegroundColor Yellow
        try { Invoke-Compose @("down", "-v", "--rmi", "local") } catch {}
        try { docker volume rm ops-opencode-data 2>$null | Out-Null } catch {}
    }
    "config"  { Invoke-ComposeWithExtra @("config") }
    "ps"      { Invoke-ComposeWithExtra @("ps") }
}
