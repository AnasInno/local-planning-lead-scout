@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 scripts\owner_app.py
) else (
  python scripts\owner_app.py
)
pause
