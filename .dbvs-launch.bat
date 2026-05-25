@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
where python >nul 2>&1 || (echo [X] Python not found && pause && exit /b 1)

echo ========================================
echo   stock-crewai
echo   python -m uvicorn main:app --reload
echo ========================================
echo.
python -m uvicorn main:app --reload
if %ERRORLEVEL% neq 0 (
    echo.
    echo [X] Exit code: %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)
echo.
echo ========================================
echo   Done
echo ========================================
pause
