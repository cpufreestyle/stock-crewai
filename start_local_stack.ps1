# stock-crewai 本地模型全栈自启守卫（开机由 stock-crewai-autostart.vbs 无窗口调用）
# 顺序: 杀托盘(自动更新源) -> 锁 cuda_v12 后端 -> 校准 num_ctx -> 设 keep_alive -> 起 serve -> 预热(带自愈) -> 注册交易日 15:35 定时运行(到点由计划任务跑, 跑完自动卸模型)
$ErrorActionPreference = 'Continue'
$Repo = "D:\aishare\repo\stock-crewai-master"
$OllamaDir = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
$OllamaExe  = Join-Path $OllamaDir "ollama.exe"
$Python    = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
$LogDir    = Join-Path $Repo "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("autostart-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))
function Log($m) {
    Add-Content -Path $Log -Value ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) -Encoding UTF8
}
Log "=== local stack autostart begin ==="

# 1) 托盘是自动更新源(0.33.2 会被升成崩 GPU 的 0.34.4), 见到就杀
Get-Process "ollama app" -ErrorAction SilentlyContinue | ForEach-Object {
    Log "stop tray pid=$($_.Id)"
    Stop-Process -Id $_.Id -Force
}

# 2) 禁用 cuda_v13 后端(driver 13.4 选它必崩 PTX JIT), 只留 cuda_v12
$V13 = Join-Path $OllamaDir "lib\ollama\cuda_v13"
if (Test-Path $V13) {
    Rename-Item $V13 "cuda_v13.disabled" -Force
    Log "cuda_v13 -> cuda_v13.disabled"
} else {
    Log "cuda_v13 already disabled/absent"
}
# 3) 校准 num_ctx=16384 (32768 在 4060 Ti 16G 上必 OOM)
$want = '{"num_ctx":16384}'
$blobDir = Join-Path $env:USERPROFILE ".ollama\models\blobs"
Get-ChildItem $blobDir -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -lt 64 } | ForEach-Object {
    $txt = (Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue)
    if ($txt -and $txt.Trim() -like "*num_ctx*") {
        if ($txt.Trim() -ne $want) {
            [System.IO.File]::WriteAllText($_.FullName, $want)
            Log ("num_ctx fixed in " + $_.Name + ": " + $txt.Trim() + " -> " + $want)
        } else {
            Log ("num_ctx already 16384 in " + $_.Name)
        }
    }
}

# 3.5) 显式空闲卸载时限: 最后一次请求后超过 OLLAMA_KEEP_ALIVE 无新请求就自动卸载模型
if ([string]::IsNullOrEmpty($env:OLLAMA_KEEP_ALIVE)) { $env:OLLAMA_KEEP_ALIVE = "5m" }
Log ("keep_alive = " + $env:OLLAMA_KEEP_ALIVE)

# 4.0) 防重复: 已有 crew / 包装器在跑就只保服务, 不预热不重启(避免烫死在跑的流水线)
$running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like '*crew.py*' -or $_.CommandLine -like '*run_crew_then_release*' }
if ($running) {
    Log ('crew run already active (pid ' + ($running.ProcessId -join ',') + '), ensure server only')
    $up2 = $false
    for ($i = 0; $i -lt 20; $i++) {
        try {
            $r2 = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/version" -UseBasicParsing -TimeoutSec 3
            if ($r2.StatusCode -eq 200) { $up2 = $true; break }
        } catch {}
        Start-Sleep -Seconds 2
    }
    if (-not $up2) { Start-Process -FilePath $OllamaExe -ArgumentList serve -WindowStyle Hidden; Start-Sleep -Seconds 10 }
    Log '=== autostart done (run already active, server ensured) ==='
    exit 0
}
# 4) 起服务 (已在线则跳过)
$up = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/version" -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) { $up = $true; Log ("ollama already up") }
} catch {}
if (-not $up) {
    Log "starting ollama serve ..."
    Start-Process -FilePath $OllamaExe -ArgumentList serve -WindowStyle Hidden
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/version" -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $up = $true; Log ("ollama up"); break }
        } catch {}
    }
}
if (-not $up) { Log 'FATAL: ollama server not responding'; exit 1 }

# 5) 预热 + 自愈: 一次真实推理确认链路; 失败则整体重启 ollama(清掉僵死 runner)再试
function Restart-Ollama {
    Log "restarting whole ollama stack (kill server + runners) ..."
    Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
    Start-Process -FilePath $OllamaExe -ArgumentList serve -WindowStyle Hidden
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/version" -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { Log ("ollama restarted: " + $r.Content); return $true }
        } catch {}
    }
    return $false
}
$warmOk = $false
for ($round = 1; $round -le 2 -and -not $warmOk; $round++) {
    Log ("warmup attempt " + $round)
    & $Python (Join-Path $Repo "warmup_llm.py") 2>&1 | ForEach-Object { Log ("warmup: " + $_) }
    if ($LASTEXITCODE -eq 0) { $warmOk = $true; break }
    if ($round -eq 1) {
        if (-not (Restart-Ollama)) { Log 'FATAL: restart failed'; exit 1 }
        Start-Sleep -Seconds 5
    }
}
if (-not $warmOk) { Log 'FATAL: warmup failed after restart, skip crew run'; exit 1 }
# 6) 注册/刷新定时运行任务(周一~周五 15:35 由计划任务跑, 不在登录时立即跑)
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repo "ensure_run_schedule.ps1") 2>&1 | ForEach-Object { Log ("schedule: " + $_) }
Log "=== local stack autostart done (server ready, run scheduled) ==="
