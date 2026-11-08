@echo off
rem Makes a private test release in your Downloads folder: see Make-MVP06-Test-Release.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Make-MVP06-Test-Release.ps1" %*
echo.
pause
