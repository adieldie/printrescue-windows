@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process py -ArgumentList '\"%~dp0main.py\"' -WorkingDirectory '\"%~dp0\"' -Verb RunAs"
  exit /b
)

where python >nul 2>&1
if %errorlevel%==0 (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process python -ArgumentList '\"%~dp0main.py\"' -WorkingDirectory '\"%~dp0\"' -Verb RunAs"
  exit /b
)

echo Python nao encontrado.
pause
