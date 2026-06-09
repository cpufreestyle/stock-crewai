# LM Studio 自动启动脚本
# 确保 gemma-4-12b-it 模型推理服务就绪

$lmStudioShortcut = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\LM Studio.lnk"
$lmStudioExe = $null

# 尝试从快捷方式解析真实路径
if (Test-Path $lmStudioShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($lmStudioShortcut)
    $lmStudioExe = $shortcut.TargetPath
}

# 快捷方式解析失败则用常见路径
if (-not $lmStudioExe -or -not (Test-Path $lmStudioExe)) {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\lm-studio\LM Studio.exe",
        "C:\Program Files\LM Studio\LM Studio.exe",
        "$env:APPDATA\LM Studio\LM Studio.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $lmStudioExe = $c; break }
    }
}

# 检查是否已运行
$lmProcess = Get-Process "LM Studio" -ErrorAction SilentlyContinue
if ($lmProcess) {
    Write-Host "[OK] LM Studio 已运行 (PID: $($lmProcess.Id))"
} else {
    if (-not $lmStudioExe) {
        Write-Error "找不到 LM Studio 可执行文件"
        exit 1
    }
    Write-Host "[启动] 正在启动 LM Studio: $lmStudioExe"
    Start-Process $lmStudioExe
    Start-Sleep 8  # 等待 GUI 加载
}

# 等待 API 就绪 (port 1234)
$maxWait = 60
$waited = 0
do {
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:1234/v1/models" -TimeoutSec 2 -ErrorAction Stop
        Write-Host "[OK] LM Studio API 已就绪 (port 1234)"
        if ($resp.data) {
            Write-Host "[模型] 已加载: $(($resp.data | ForEach-Object { $_.id }) -join ', ')"
        }
        break
    } catch {
        Start-Sleep 2
        $waited += 2
        Write-Host "[等待] LM Studio API 未就绪，已等待 ${waited}s..."
    }
} while ($waited -lt $maxWait)

if ($waited -ge $maxWait) {
    Write-Warning "LM Studio API 在 ${maxWait}s 内未就绪，请手动检查"
    exit 1
}

Write-Host "[完成] LM Studio 已就绪，可以运行分析"
