@echo off
rem Messstand starten (Windows 11). Doppelklick genuegt.
rem Andere Station: start.bat stations\macmini.yaml
cd /d "%~dp0"

set KONFIG=%1
if "%KONFIG%"=="" set KONFIG=stations\laptop.yaml

where uv >nul 2>nul
if errorlevel 1 (
  echo.
  echo   uv ist nicht installiert oder nicht im Pfad.
  echo   Installation: winget install astral-sh.uv
  echo.
  pause
  exit /b 1
)

if not exist "%KONFIG%" (
  echo.
  echo   Konfigurationsdatei nicht gefunden: %KONFIG%
  echo   Vorhanden sind:
  dir /b stations\*.yaml
  echo.
  pause
  exit /b 1
)

uv run messstand --config "%KONFIG%"
echo.
echo   Messstand beendet.
pause
