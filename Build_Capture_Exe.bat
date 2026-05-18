@echo off
REM ================================================================
REM Momentum Capture - experimental chat-like version builder
REM Builds MomentumCapture.exe without replacing FocusTracker.exe.
REM ================================================================

setlocal
set "HERE=%~dp0"
cd /d "%HERE%"

if not exist "%HERE%momentum_capture.py" (
    echo ERROR: momentum_capture.py not found in this folder:
    echo   %HERE%
    pause
    exit /b 1
)

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo ERROR: Python is not installed or not on PATH.
    pause
    exit /b 1
)

echo Installing / updating app dependencies...
%PY% -m pip install --user --upgrade -r "%HERE%requirements.txt"
if errorlevel 1 (
    echo Failed to install app dependencies. See messages above.
    pause
    exit /b 1
)

echo Installing / updating PyInstaller...
%PY% -m pip install --user --upgrade pyinstaller
if errorlevel 1 (
    echo Failed to install PyInstaller. See messages above.
    pause
    exit /b 1
)

echo.
echo Building MomentumCapture.exe (this takes 30-90 seconds)...
set "ICON_ARG="
if exist "%HERE%app_icon.ico" set "ICON_ARG=--icon=%HERE%app_icon.ico"

%PY% -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name MomentumCapture ^
    %ICON_ARG% ^
    --collect-all tokenizers ^
    --distpath "%HERE%dist" ^
    --workpath "%HERE%build" ^
    --specpath "%HERE%" ^
    "%HERE%momentum_capture.py"

if not exist "%HERE%dist\MomentumCapture.exe" (
    echo.
    echo Build failed. Scroll up to see why.
    pause
    exit /b 1
)

move /Y "%HERE%dist\MomentumCapture.exe" "%HERE%MomentumCapture.exe" >nul
rmdir /S /Q "%HERE%dist" 2>nul
rmdir /S /Q "%HERE%build" 2>nul
del /Q "%HERE%MomentumCapture.spec" 2>nul

set "SHORTCUT=%USERPROFILE%\Desktop\Momentum Capture.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = '%HERE%MomentumCapture.exe';" ^
  "$s.WorkingDirectory = '%HERE%';" ^
  "$s.IconLocation = '%HERE%app_icon.ico';" ^
  "$s.WindowStyle = 1;" ^
  "$s.Description = 'Momentum chat-like capture version';" ^
  "$s.Save()"

echo.
echo =====================================================
echo  Done.
echo  App:      %HERE%MomentumCapture.exe
echo  Shortcut: Momentum Capture  (on your Desktop)
echo  Data:     %HERE%momentum.sqlite3
echo  Captures: %HERE%momentum_captures
echo  Local AI: %HERE%experiments\three_class\latest
echo =====================================================
pause
