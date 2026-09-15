@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    if not exist ".venv\Scripts\pythonw.exe" goto :missing_python
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    where python.exe >nul 2>&1 || goto :missing_python
    where pythonw.exe >nul 2>&1 || goto :missing_python
    set "PYTHON=python.exe"
)

"%PYTHON%" -c "import comtypes, PIL, pystray" >nul 2>&1 || goto :missing_dependencies
"%PYTHON%" -m codex_usage_widget.launcher "%~dp0" || goto :launch_failed
exit /b 0

:missing_python
echo Python 3.11 or newer was not found.
echo Install Python from https://www.python.org/ and enable Add Python to PATH.
pause
exit /b 1

:missing_dependencies
echo Required packages are missing.
echo Run: "%PYTHON%" -m pip install -e .
pause
exit /b 1

:launch_failed
echo The widget could not be started independently.
echo Check the Windows Management Instrumentation service, then try again.
pause
exit /b 1
