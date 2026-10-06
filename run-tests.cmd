@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-windows.ps1"
set "testkit_exit=%ERRORLEVEL%"
echo.
if not "%testkit_exit%"=="0" echo Setup or tests failed. Read the error above.
pause
exit /b %testkit_exit%
