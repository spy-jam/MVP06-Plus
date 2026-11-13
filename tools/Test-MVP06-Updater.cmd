@echo off
rem Tries the Launcher's updater on your private test release: see Test-MVP06-Updater.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Test-MVP06-Updater.ps1" %*
echo.
pause
