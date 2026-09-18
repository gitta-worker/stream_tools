@echo off
setlocal

set "APP_DIR=%~dp0"
set "LAUNCHER=%APP_DIR%haishin_launcher.ps1"

if not exist "%LAUNCHER%" (
    echo [ERROR] Launcher was not found: %LAUNCHER%
    endlocal
    exit /b 1
)

title Haishin Launcher
echo [INFO] Keep this window open while streaming.
echo [INFO] Stop streaming in OBS before stopping this launcher.
echo [INFO] Press Ctrl+C or close this window to stop launched tools.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%"
set "EXIT_CODE=%ERRORLEVEL%"

endlocal & exit /b %EXIT_CODE%
