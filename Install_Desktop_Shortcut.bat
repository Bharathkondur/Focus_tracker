@echo off
REM ================================================================
REM Focus Tracker — desktop shortcut installer
REM Run this once. Put it in the same folder as focus_tracker.py.
REM It will:
REM   1. Make a FocusTracker.pyw copy (so launching shows no console).
REM   2. Create a "Focus Tracker" shortcut on your Desktop.
REM ================================================================

setlocal
set "HERE=%~dp0"

REM --- Step 1: ensure a .pyw version exists next to the .py ---
if exist "%HERE%focus_tracker.py" (
    if not exist "%HERE%FocusTracker.pyw" (
        copy /Y "%HERE%focus_tracker.py" "%HERE%FocusTracker.pyw" >nul
    )
)

if not exist "%HERE%FocusTracker.pyw" (
    echo ERROR: Could not find focus_tracker.py in this folder:
    echo   %HERE%
    echo.
    echo Put this .bat next to focus_tracker.py and run it again.
    pause
    exit /b 1
)

set "TARGET=%HERE%FocusTracker.pyw"
set "SHORTCUT=%USERPROFILE%\Desktop\Focus Tracker.lnk"

REM --- Step 2: create the Desktop shortcut via PowerShell ---
REM Icon "shell32.dll,43" is the calendar icon built into Windows.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = '%TARGET%';" ^
  "$s.WorkingDirectory = '%HERE%';" ^
  "$s.IconLocation = 'shell32.dll,43';" ^
  "$s.WindowStyle = 1;" ^
  "$s.Description = 'Daily goal tracker';" ^
  "$s.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo Done. Look for "Focus Tracker" on your Desktop.
) else (
    echo.
    echo Shortcut creation failed. You can still pin FocusTracker.pyw manually.
)

echo.
pause
