# Stock CrewAI auto-start script
# Triggered at user logon:
#   1) start Ollama (local LLM, with redirected USERPROFILE)
#   2) start Docker Desktop
#   3) wait for daemons -> docker-compose up -d
# NOTE: keep this file pure ASCII (Windows PowerShell 5.1 reads BOM-less .ps1 as ANSI)
$ErrorActionPreference = "Continue"

$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $project

# Work around the untrusted mount point on the user profile dir (affects Docker CLI)
$env:DOCKER_CONFIG = "C:\docker"
$env:DOCKER_BUILDKIT = "0"

# Ollama: USERPROFILE must point to a trusted dir, otherwise the ed25519
# private key under %USERPROFILE%\.ollama cannot be read (model pull / auth fails)
$ollamaExe = "C:\Users\qm081\AppData\Local\Programs\Ollama\ollama.exe"
$ollamaHome = "C:\ollama-home"
$ollamaModels = "C:\ollama-models"
$env:USERPROFILE = $ollamaHome
$env:OLLAMA_MODELS = $ollamaModels
$env:OLLAMA_HOST = "0.0.0.0:11434"

$logDir = Join-Path $project "history"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$logFile = Join-Path $logDir "autostart.log"
function Log($msg) {
    "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg | Out-File -FilePath $logFile -Append -Encoding utf8
}

function Wait-Port($port, $minutes, $label) {
    $deadline = (Get-Date).AddMinutes($minutes)
    while ((Get-Date) -lt $deadline) {
        $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($c) { Log "$label ready (port $port)"; return $true }
        Start-Sleep -Seconds 5
    }
    Log "$label NOT ready within $minutes min (port $port)"
    return $false
}

Log "=== autostart begin ==="

# 1. Start Ollama if needed
if (-not (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)) {
    if (Test-Path $ollamaExe) {
        Log "starting Ollama (home=$ollamaHome)"
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
    } else {
        Log "Ollama not found at $ollamaExe"
    }
} else {
    Log "Ollama already listening"
}
$ollamaOk = Wait-Port 11434 3 "Ollama"

# 2. Start Docker Desktop if needed
if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
    Log "starting Docker Desktop"
    $dd = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dd) { Start-Process $dd } else { Log "Docker Desktop not found at $dd" }
} else {
    Log "Docker Desktop already running"
}
$dockerOk = $false
$deadline = (Get-Date).AddMinutes(5)
while ((Get-Date) -lt $deadline) {
    $v = & docker info --format "{{.ServerVersion}}" 2>$null
    if ($LASTEXITCODE -eq 0 -and $v) { $dockerOk = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $dockerOk) { Log "Docker daemon not ready within 5 min, abort"; exit 1 }
Log "Docker daemon ready"

# 3. Bring up the compose services
$compose = (Get-Command docker-compose -ErrorAction SilentlyContinue).Source
if (-not $compose) { $compose = "C:\Program Files\Docker\Docker\resources\bin\docker-compose.exe" }

$out = & $compose up -d 2>&1
Log "compose up => $($out -join ' | ')"
Log "=== autostart end (ollama=$ollamaOk docker=$dockerOk) ==="
