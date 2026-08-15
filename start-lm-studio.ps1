$ErrorActionPreference = "Stop"

# --- 配置 ---
$CtxSize = 8192
$ModelsRoot = "C:\Users\michael\.lmstudio\models"

# --- 找一个空闲端口 ---
function Get-FreePort {
    $port = 12340
    while ($true) {
        $inUse = netstat -ano | Select-String ":${port}\s+"
        if (-not $inUse) { return $port }
        $port++
        if ($port -gt 13000) { throw "无法找到空闲端口" }
    }
}

$Port = Get-FreePort
Write-Host "[信息] 使用端口: $Port"

# 写入端口文件供 Python 使用
$PortFile = "$PSScriptRoot\.lm-studio-port.txt"
$Port | Out-File -FilePath $PortFile -Encoding ASCII -NoNewline
Write-Host "[信息] 端口已写入: $PortFile"

# --- 找 llama-server.exe（优先 Vulkan）---
$BackendBase = "C:\Users\michael\.lmstudio\extensions\backends"
$PreferredOrder = @(
    "llama.cpp-win-x86_64-vulkan-avx2-2.23.1",
    "llama.cpp-win-x86_64-vulkan-avx2-2.22.0",
    "llama.cpp-win-x86_64-avx2-2.23.1",
    "llama.cpp-win-x86_64-nvidia-cuda12-avx2-2.23.1"
)

$LlamaServer = $null
foreach ($b in $PreferredOrder) {
    $exe = Join-Path $BackendBase "$b\llama-server.exe"
    if (Test-Path $exe) { $LlamaServer = $exe; break }
}
if (-not $LlamaServer) {
    Write-Error "[启动失败] 找不到 llama-server.exe"
    exit 1
}
Write-Host "[信息] llama-server: $LlamaServer"

# --- 搜索目录（优先小模型）---
$SearchDirs = @(
    "lmstudio-community\gemma-4-12B-it-GGUF",
    "catlilface\Gemma-4-26B-A4B-NVFP4-GGUF",
    "llmfan46\Qwen3.6-27B-uncensored-heretic-v2-Native-MTP-Preserved-NVFP4-GGUF"
)

$bestFile = $null
foreach ($sub in $SearchDirs) {
    $dir = Join-Path $ModelsRoot $sub
    if (-not (Test-Path $dir)) { continue }
    $ggufFiles = @(Get-ChildItem $dir -Filter "*.gguf" -File -ErrorAction SilentlyContinue)
    if ($ggufFiles.Count -eq 0) { continue }
    $candidate = $null
    foreach ($f in $ggufFiles) {
        if ($f.BaseName -notlike "*mmproj*") {
            if ($null -eq $candidate -or $f.Length -gt $candidate.Length) {
                $candidate = $f
            }
        }
    }
    if ($null -eq $candidate) { continue }
    $bestFile = $candidate
    break
}

if ($null -eq $bestFile) {
    Write-Error "[启动失败] 找不到任何可用模型 GGUF 文件"
    exit 1
}

$ModelPath = $bestFile.FullName
$ModelName = $bestFile.BaseName
$SizeGB = [math]::Round($bestFile.Length / 1GB, 1)
Write-Host "[信息] 选中: $ModelPath ($SizeGB GB)"

# --- GPU 层数（VRAM ~4GB，8GB 以上模型用 CPU）---
$GpuLayers = 99
if ($SizeGB -gt 8) {
    Write-Host "[警告] 模型 $SizeGB GB > 8GB，VRAM 不足，改用 CPU"
    $GpuLayers = 0
}

# --- 找 mmproj（仅 Gemma4-26b）---
$ModelDir = Split-Path $ModelPath -Parent
$Mmproj = $null
if ($ModelName -like "*Gemma4-26b*") {
    $pmFiles = @(Get-ChildItem $ModelDir -Filter "mmproj*.gguf" -File -ErrorAction SilentlyContinue)
    if ($pmFiles.Count -gt 0) { $Mmproj = $pmFiles[0].FullName; Write-Host "[信息] mmproj: $Mmproj" }
}

# --- 检查 llama-server 是否已在运行（读取端口文件）---
$PortFile = "$PSScriptRoot\.lm-studio-port.txt"
if (Test-Path $PortFile) {
    $savedPort = (Get-Content $PortFile -Raw).Trim()
    if ($savedPort -match "^\d+$") {
        $Port = [int]$savedPort
        Write-Host "[信息] 从文件读取端口: $Port"
    }
}

$Existing = Get-Process "llama-server" -ErrorAction SilentlyContinue
if ($Existing) {
    try {
        Invoke-RestMethod -Uri "http://localhost:$Port/v1/models" -TimeoutSec 3 -ErrorAction SilentlyContinue | Out-Null
        Write-Host "[OK] llama-server 已在运行 (port $Port)"
        exit 0
    } catch {
        Write-Host "[警告] 重启旧的 llama-server..."
        Stop-Process $Existing -Force -ErrorAction SilentlyContinue
        Start-Sleep 3
    }
}

# --- 启动 llama-server ---
Write-Host "[启动] 启动 llama-server..."
$args = @(
    "-m", $ModelPath,
    "-c", $CtxSize,
    "-ngl", $GpuLayers,
    "--host", "127.0.0.1",
    "--port", $Port
)
if ($Mmproj) { $args += @("--mmproj", $Mmproj) }

$proc = Start-Process -FilePath $LlamaServer -ArgumentList $args -PassThru -NoNewWindow
Write-Host "[启动] PID: $($proc.Id)，等待初始化..."

# --- 等待 API 就绪 ---
$maxWait = 180
$waited = 0
while ($waited -lt $maxWait) {
    Start-Sleep 3
    $waited += 3
    if ($proc.HasExited) {
        Write-Host "[崩溃] llama-server 已退出，exit code: $($proc.ExitCode)"
        exit 1
    }
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:$Port/v1/models" -TimeoutSec 5 -ErrorAction Stop
        $models = $resp.data | ForEach-Object { $_.id }
        Write-Host "[OK] LM Studio API 已就绪 (port $Port)"
        Write-Host "[模型] $($models -join ', ')"
        Write-Host "[完成] llama-server 已就绪"
        exit 0
    } catch {
        Write-Host "[等待] 已等待 ${waited}s..."
    }
}

Write-Error "[超时] API 在 ${maxWait}s 内未就绪"
exit 1
