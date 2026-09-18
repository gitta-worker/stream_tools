@echo off
setlocal

set "APP_DIR=%~dp0"
set "PYTHON=%APP_DIR%.venv-translation\Scripts\python.exe"
set "SERVER=%APP_DIR%translation_server.py"

if not exist "%PYTHON%" (
    where py.exe >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python 3 was not found. Install Python 3 and run setup.bat again.
        exit /b 1
    )

    echo [SETUP] Creating the local Python environment...
    py.exe -3 -m venv "%APP_DIR%.venv-translation"
    if errorlevel 1 exit /b 1

    echo [SETUP] Installing required Python packages...
    "%PYTHON%" -m pip install -r "%APP_DIR%requirements.txt"
    if errorlevel 1 exit /b 1
)

"%PYTHON%" "%SERVER%" --setup-only --open-browser
endlocal
