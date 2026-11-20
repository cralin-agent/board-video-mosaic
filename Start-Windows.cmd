@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  set "PY=py -3"
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo Python 3 is not installed. Install Python 3.11+ from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
  echo Initial setup: creating private Python environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Could not create environment.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Installation failed. Check internet, Python version, and disk space.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" gui.py
if errorlevel 1 pause
endlocal
