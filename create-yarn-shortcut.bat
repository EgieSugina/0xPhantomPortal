@echo off
setlocal enabledelayedexpansion

echo ========================================
echo 0xPhantomPortal Yarn Shortcut Creator
echo ========================================

:: Set paths
set "SCRIPT_DIR=%~dp0"
set "APP_NAME=0xPhantomPortal"
set "DESKTOP_PATH=%USERPROFILE%\Desktop"
set "START_MENU_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs"

:: Check if yarn is available
yarn --version >nul 2>&1
if %errorLevel% neq 0 (
    echo Error: Yarn is not installed or not in PATH
    echo Please install Yarn first: npm install -g yarn
    echo.
    pause
    exit /b 1
)

:: Check if package.json exists
if not exist "%SCRIPT_DIR%package.json" (
    echo Error: package.json not found!
    echo Please run this script from the project root directory.
    echo.
    pause
    exit /b 1
)

:: Choose which start script to use
echo Choose start script type:
echo 1. Batch script (start-phantom-portal.bat) - Recommended
echo 2. PowerShell script (start-phantom-portal.ps1) - Alternative
echo.
set /p "choice=Enter choice (1 or 2): "

if "%choice%"=="2" (
    set "EXECUTABLE_PATH=powershell.exe"
    set "SCRIPT_ARGS=-ExecutionPolicy Bypass -File %SCRIPT_DIR%start-phantom-portal.ps1"
    set "SCRIPT_NAME=start-phantom-portal.ps1"
) else (
    set "EXECUTABLE_PATH=%SCRIPT_DIR%start-phantom-portal.bat"
    set "SCRIPT_ARGS="
    set "SCRIPT_NAME=start-phantom-portal.bat"
)

echo.
echo Using: %SCRIPT_NAME%
echo.

:: Create desktop shortcut
echo Creating desktop shortcut...
set "DESKTOP_SHORTCUT=%DESKTOP_PATH%\%APP_NAME%.lnk"

if "%choice%"=="2" (
    powershell -Command "& {$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%DESKTOP_SHORTCUT%'); $Shortcut.TargetPath = '%EXECUTABLE_PATH%'; $Shortcut.Arguments = '%SCRIPT_ARGS%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Description = '0xPhantomPortal - Start with Yarn'; $Shortcut.IconLocation = 'powershell.exe,0'; $Shortcut.Save()}"
) else (
    powershell -Command "& {$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%DESKTOP_SHORTCUT%'); $Shortcut.TargetPath = '%EXECUTABLE_PATH%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Description = '0xPhantomPortal - Start with Yarn'; $Shortcut.IconLocation = 'cmd.exe,0'; $Shortcut.Save()}"
)

if exist "%DESKTOP_SHORTCUT%" (
    echo ✓ Desktop shortcut created: %DESKTOP_SHORTCUT%
) else (
    echo ✗ Failed to create desktop shortcut
)

:: Create start menu shortcut
echo.
echo Creating start menu shortcut...
if not exist "%START_MENU_PATH%" mkdir "%START_MENU_PATH%"
set "START_MENU_SHORTCUT=%START_MENU_PATH%\%APP_NAME%.lnk"

if "%choice%"=="2" (
    powershell -Command "& {$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU_SHORTCUT%'); $Shortcut.TargetPath = '%EXECUTABLE_PATH%'; $Shortcut.Arguments = '%SCRIPT_ARGS%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Description = '0xPhantomPortal - Start with Yarn'; $Shortcut.IconLocation = 'powershell.exe,0'; $Shortcut.Save()}"
) else (
    powershell -Command "& {$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU_SHORTCUT%'); $Shortcut.TargetPath = '%EXECUTABLE_PATH%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Description = '0xPhantomPortal - Start with Yarn'; $Shortcut.IconLocation = 'cmd.exe,0'; $Shortcut.Save()}"
)

if exist "%START_MENU_SHORTCUT%" (
    echo ✓ Start menu shortcut created: %START_MENU_SHORTCUT%
) else (
    echo ✗ Failed to create start menu shortcut
)

:: Create taskbar shortcut
echo.
echo Creating taskbar shortcut...
set "TASKBAR_PATH=%APPDATA%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"

if exist "%TASKBAR_PATH%" (
    set "TASKBAR_SHORTCUT=%TASKBAR_PATH%\%APP_NAME%.lnk"
    
    if "%choice%"=="2" (
        powershell -Command "& {$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%TASKBAR_SHORTCUT%'); $Shortcut.TargetPath = '%EXECUTABLE_PATH%'; $Shortcut.Arguments = '%SCRIPT_ARGS%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Description = '0xPhantomPortal - Start with Yarn'; $Shortcut.IconLocation = 'powershell.exe,0'; $Shortcut.Save()}"
    ) else (
        powershell -Command "& {$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%TASKBAR_SHORTCUT%'); $Shortcut.TargetPath = '%EXECUTABLE_PATH%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Description = '0xPhantomPortal - Start with Yarn'; $Shortcut.IconLocation = 'cmd.exe,0'; $Shortcut.Save()}"
    )
    
    if exist "%TASKBAR_SHORTCUT%" (
        echo ✓ Taskbar shortcut created: %TASKBAR_SHORTCUT%
    ) else (
        echo ✗ Failed to create taskbar shortcut
    )
) else (
    echo ⚠ Taskbar directory not found, skipping taskbar shortcut
)

echo.
echo ========================================
echo Shortcut creation completed!
echo ========================================
echo.
echo Created shortcuts:
if exist "%DESKTOP_SHORTCUT%" echo • Desktop: %DESKTOP_SHORTCUT%
if exist "%START_MENU_SHORTCUT%" echo • Start Menu: %START_MENU_SHORTCUT%
if exist "%TASKBAR_SHORTCUT%" echo • Taskbar: %TASKBAR_SHORTCUT%
echo.
echo These shortcuts will run: yarn start
echo Using script: %SCRIPT_NAME%
echo.
echo Troubleshooting:
echo - If shortcuts don't work, try the PowerShell version
echo - Make sure yarn is installed: npm install -g yarn
echo - Run the script directly to test: %SCRIPT_NAME%
echo.
pause 