# stock-crewai autostart script
# Start Ollama -> wait ready -> wait Docker -> docker-compose up -d
$ErrorActionPreference = "Continue"
$proj = "D:\aishare\repo\stock-crewai-master"
$log = "$proj\autostart.log"
function Write-Log($m) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"
    Out-File -FilePath $log -Append -Encoding utf8 -InputObject $line
}

Write-Log "==== autostart begin ===="

# 1. Start Ollama if not running
$ollamaProc = Get-Process ollama -ErrorAction SilentlyContinue
if ($null -eq $ollamaProc) {
    # 27B cold load costs ~36s; without keep-alive the model gets evicted from VRAM
    $env:OLLAMA_KEEP_ALIVE = "20m"
    Start-Process -FilePath "C:\Users\qm081\AppData\Local\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden
    Write-Log "Ollama started"
} else {
    Write-Log "Ollama already running"
}

# 2. Wait for Ollama port 11434
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    $conn = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
    if ($null -ne $conn) { $ok = $true; break }
    Start-Sleep -Seconds 2
}
if ($ok) { Write-Log "Ollama port ready" } else { Write-Log "Ollama port timeout" }

# 3. Wait for Docker daemon
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { $ok = $true; break }
    Start-Sleep -Seconds 3
}
if ($ok) { Write-Log "Docker daemon ready" } else { Write-Log "Docker daemon timeout" }

# 4. Start project containers
Set-Location $proj
$env:DOCKER_CONFIG = "C:\docker"
$env:DOCKER_BUILDKIT = "0"
$out = docker-compose up -d 2>&1
Out-File -FilePath $log -Append -Encoding utf8 -InputObject $out
Write-Log "==== autostart done ===="
