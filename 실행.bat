@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    if not exist ".venv\Scripts\pythonw.exe" goto :missing_python
    set "PYTHON=.venv\Scripts\python.exe"
    set "PYTHONW=.venv\Scripts\pythonw.exe"
) else (
    where python.exe >nul 2>&1 || goto :missing_python
    where pythonw.exe >nul 2>&1 || goto :missing_python
    set "PYTHON=python.exe"
    set "PYTHONW=pythonw.exe"
)

"%PYTHON%" -c "import comtypes, PIL, pystray" >nul 2>&1 || goto :missing_dependencies
start "" /b "%PYTHONW%" "%~dp0widget.pyw"
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
