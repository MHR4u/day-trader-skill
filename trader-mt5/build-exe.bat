@echo off
REM Build dtcli.exe on Windows: one file that runs all twelve tools.
REM Needs Python 3.8+ on PATH. MetaTrader5 is installed so the frozen binary
REM can talk to a running terminal; without it the binary still reads snapshots.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.8 or newer is required: https://www.python.org/downloads/windows/
  echo Tick "Add python.exe to PATH" in the installer.
  exit /b 1
)

echo Installing PyInstaller and the MetaTrader5 package...
python -m pip install --upgrade pip >nul
python -m pip install --upgrade pyinstaller MetaTrader5
if errorlevel 1 (
  echo Could not install the build tools. Check your internet connection.
  exit /b 1
)

echo Building...
python -m PyInstaller --clean --noconfirm --distpath "%~dp0..\dist" --workpath "%~dp0..\build" "%~dp0daytrader.spec"
if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo.
echo Built: %~dp0..\dist\dtcli.exe
echo Try it:
echo    "%~dp0..\dist\dtcli.exe" list
echo    "%~dp0..\dist\dtcli.exe" mt5 doctor
echo.
echo Copy dtcli.exe anywhere. It writes its state to a trader\ folder in the
echo directory you run it from, exactly like the scripts do.
endlocal
