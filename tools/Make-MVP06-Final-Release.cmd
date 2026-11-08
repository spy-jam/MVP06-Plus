@echo off
rem The real release's draft (tag beta-1): see Make-MVP06-Test-Release.ps1. Publish it on GitHub when ready.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Make-MVP06-Test-Release.ps1" -Final %*
echo.
pause
