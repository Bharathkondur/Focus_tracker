@echo off
REM ================================================================
REM Focus Tracker — one-click .exe builder
REM Run this once. Put it in the same folder as focus_tracker.py.
REM It will:
REM   1. Install app dependencies and PyInstaller (if missing).
REM   2. Build FocusTracker.exe (single file, no console).
REM   3. Drop a "Focus Tracker" shortcut on your Desktop.
REM
REM After this you can delete focus_tracker.py and Python and the
REM .exe still works.
REM ================================================================

setlocal
set "HERE=%~dp0"
cd /d "%HERE%"

if not exist "%HERE%focus_tracker.py" (
    echo ERROR: focus_tracker.py not found in this folder:
    echo   %HERE%
    pause
    exit /b 1
)

REM --- Find a Python launcher --------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo ERROR: Python is not installed or not on PATH.
    echo Install from https://www.python.org/downloads/  (tick "Add Python to PATH")
    pause
    exit /b 1
)

REM --- Install dependencies ----------------------------------------
echo Installing / updating app dependencies...
%PY% -m pip install --user --upgrade -r "%HERE%requirements.txt"
if errorlevel 1 (
    echo Failed to install app dependencies. See messages above.
    pause
    exit /b 1
)

REM --- Make sure pyinstaller is available --------------------------
echo Installing / updating PyInstaller...
%PY% -m pip install --user --upgrade pyinstaller
if errorlevel 1 (
    echo Failed to install PyInstaller. See messages above.
    pause
    exit /b 1
)

REM --- Build ------------------------------------------------------
echo.
echo Building FocusTracker.exe (this takes 30-90 seconds)...
set "ICON_ARG="
if exist "%HERE%app_icon.ico" set "ICON_ARG=--icon=%HERE%app_icon.ico"

%PY% -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name FocusTracker ^
    %ICON_ARG% ^
    --distpath "%HERE%dist" ^
    --workpath "%HERE%build" ^
    --specpath "%HERE%" ^
    "%HERE%focus_tracker.py"

if not exist "%HERE%dist\FocusTracker.exe" (
    echo.
    echo Build failed. Scroll up to see why.
    pause
    exit /b 1
)

REM --- Move .exe to the folder root, clean up build junk ----------
move /Y "%HERE%dist\FocusTracker.exe" "%HERE%FocusTracker.exe" >nul
rmdir /S /Q "%HERE%dist" 2>nul
rmdir /S /Q "%HERE%build" 2>nul
del /Q "%HERE%FocusTracker.spec" 2>nul

REM --- Desktop shortcut -------------------------------------------
set "SHORTCUT=%USERPROFILE%\Desktop\Focus Tracker.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = '%HERE%FocusTracker.exe';" ^
  "$s.WorkingDirectory = '%HERE%';" ^
  "$s.IconLocation = 'shell32.dll,43';" ^
  "$s.WindowStyle = 1;" ^
  "$s.Description = 'Daily goal tracker';" ^
  "$s.Save()"

echo.
echo =====================================================
echo  Done.
echo  App:      %HERE%FocusTracker.exe
echo  Shortcut: Focus Tracker  (on your Desktop)
echo  Data:     %HERE%momentum.sqlite3
echo =====================================================
pause
