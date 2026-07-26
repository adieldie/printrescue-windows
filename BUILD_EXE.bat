@echo off
chcp 65001 >nul
title Compilar PrintRescue Windows
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
  set PY=py
) else (
  set PY=python
)

echo Instalando/atualizando PyInstaller...
%PY% -m pip install --upgrade pyinstaller
if errorlevel 1 goto erro

echo.
echo Gerando executavel...
%PY% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --uac-admin ^
  --name "PrintRescue_Windows" ^
  --collect-submodules printrescue ^
  "main.py"

if errorlevel 1 goto erro

echo.
echo ===============================================
echo PRONTO
echo Executavel:
echo %~dp0dist\PrintRescue_Windows.exe
echo ===============================================
pause
exit /b

:erro
echo.
echo Falha ao compilar. Verifique o Python e a internet.
pause
exit /b 1
