# 掘金仿真桥接环境一次性搭建（Python 3.10 + gmtrade）
# 用法: powershell -ExecutionPolicy Bypass -File setup_gm_env.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# 1. 定位 Python 3.10
$py310 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
if (-not (Test-Path $py310)) {
    Write-Host "[1/4] 未找到 Python 3.10，从 python.org 静默安装（用户级，不影响现有版本）..."
    $installer = Join-Path $env:TEMP "py310-install.exe"
    $url = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
    # 直连（限时90秒），失败则回退本地代理（如 Clash 127.0.0.1:7897）
    curl.exe -L -o $installer --connect-timeout 15 --max-time 90 -sS $url
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $installer)) {
        Write-Host "直连下载失败，尝试代理 127.0.0.1:7897 ..."
        curl.exe -L -x http://127.0.0.1:7897 -o $installer --connect-timeout 15 --max-time 240 -sS $url
        if ($LASTEXITCODE -ne 0) { throw "下载 Python 3.10 失败" }
    }
    if ((Get-Item $installer).Length -lt 20MB) {
        curl.exe -L -x http://127.0.0.1:7897 -o $installer --connect-timeout 15 --max-time 240 -sS $url
        if ($LASTEXITCODE -ne 0) { throw "下载 Python 3.10 失败" }
    }
    Start-Process -Wait $installer -ArgumentList "/quiet InstallAllUsers=0 TargetDir=`"$py310`" PrependPath=0 Include_test=0 Include_launcher=0"
    if (-not (Test-Path $py310)) { throw "Python 3.10 安装失败，请手动安装后重跑本脚本" }
} else {
    Write-Host "[1/4] 已找到 Python 3.10: $py310"
}

# 2. 创建 .gmenv 虚拟环境
Write-Host "[2/4] 创建 .gmenv 虚拟环境..."
& $py310 -m venv .gmenv
if ($LASTEXITCODE -ne 0) { throw "创建 .gmenv 失败" }
$envPython = Join-Path $root ".gmenv\Scripts\python.exe"
$envPip = Join-Path $root ".gmenv\Scripts\pip.exe"

# 3. 安装 gmtrade + filelock（protobuf 依赖会被 pip 自动解析为 3.x，隔离于主环境）
Write-Host "[3/4] 安装 gmtrade + filelock（约 1-2 分钟）..."
& $envPip install --disable-pip-version-check gmtrade filelock
if ($LASTEXITCODE -ne 0) { throw "安装 gmtrade 失败" }

# 4. 验证
Write-Host "[4/4] 验证..."
& $envPython -c "from gmtrade.api import set_token, set_endpoint, login, order_volume; print('gmtrade OK')"
if ($LASTEXITCODE -ne 0) { throw "gmtrade 验证失败" }

Write-Host ""
Write-Host "✅ 桥接环境搭建完成"
Write-Host "下一步: 在 .env 中配置 GM_ENABLED/GM_TOKEN/GM_ACCOUNT_ID，然后运行:"
Write-Host "  .gmenv\Scripts\python.exe gm_sync_worker.py --dry-run   # 验证登录"
Write-Host "  python gm_broker.py                                     # 查看对接状态"
