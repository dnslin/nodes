@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" proxyscrape_register.py %*
) else (
    python proxyscrape_register.py %*
)
exit /b %errorlevel%
