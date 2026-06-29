@echo off
REM Stock-CrewAI Claude Harness 启动脚本

cd /d "%~dp0"

echo ====================================
echo Stock-CrewAI Claude Harness
echo ====================================
echo.

REM 检查 Docker 是否运行
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Docker 未运行，请先启动 Docker Desktop
    pause
    exit /b 1
)

REM 启动 Claude Harness (Codex)
echo [1/2] 启动 Claude Codex...
start "Stock-CrewAI Codex" codex

timeout /t 3 /nobreak >nul

REM 检查 Harness 状态
echo [2/2] 检查 Harness 状态...
python harness_guard.py

echo.
echo ====================================
echo Harness 已启动！
echo.
echo 常用命令:
echo   codex              - 启动交互式 Codex
echo   python crew.py     - 运行交易系统（开发模式）
echo   docker compose up   - 启动 Docker 生产环境
echo ====================================
pause
