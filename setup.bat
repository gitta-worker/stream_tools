@echo off
setlocal

set "APP_DIR=%~dp0"
set "EXE=%APP_DIR%translation_server.exe"
set "PYTHON=%APP_DIR%.venv-translation\Scripts\python.exe"
set "SERVER=%APP_DIR%translation_server.py"

if exist "%EXE%" (
    "%EXE%" --setup-only --open-browser
    set "EXIT_CODE=%ERRORLEVEL%"
    if not "%EXIT_CODE%"=="0" pause
    endlocal & exit /b %EXIT_CODE%
)

if not exist "%PYTHON%" (
    where py.exe >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Translation runtime was not found.
        echo [INFO] Download and extract the Windows release package to use this tool without Python.
        echo [INFO] Developers can install Python 3 and run this source version instead.
        pause
        exit /b 1
    )

    echo [SETUP] Creating the local Python environment...
    py.exe -3 -m venv "%APP_DIR%.venv-translation"
    if errorlevel 1 (
        echo [ERROR] Failed to create the local Python environment.
        pause
        exit /b 1
    )

    echo [SETUP] Installing required Python packages...
    "%PYTHON%" -m pip install -r "%APP_DIR%requirements.txt"
    if errorlevel 1 (
        echo [ERROR] Failed to install required Python packages.
        pause
        exit /b 1
    )
)

"%PYTHON%" "%SERVER%" --setup-only --open-browser
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
endlocal & exit /b %EXIT_CODE%
