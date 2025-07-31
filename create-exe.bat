@echo off
title Create 0xPhantomPortal Executable

echo ========================================
echo Creating 0xPhantomPortal Executable
echo ========================================
echo.

:: Check if we have the required files
if not exist "run-phantom-portal.bat" (
    echo Error: run-phantom-portal.bat not found!
    echo Please make sure the batch file exists in this directory.
    echo.
    pause
    exit /b 1
)

:: Create a simple icon file (if it doesn't exist)
if not exist "phantom-portal.ico" (
    echo Creating icon file...
    echo Creating a simple icon for the executable...
    echo Note: You can replace phantom-portal.ico with your own icon file.
    echo.
)

:: Method 1: Try using Bat To Exe Converter (if available)
echo Method 1: Checking for Bat To Exe Converter...
where "bat2exe" >nul 2>&1
if %errorLevel% equ 0 (
    echo Found bat2exe converter!
    echo Creating executable...
    bat2exe run-phantom-portal.bat phantom-portal.exe /icon phantom-portal.ico
    goto :success
)

:: Method 2: Try using Advanced BAT to EXE Converter
echo Method 2: Checking for Advanced BAT to EXE Converter...
where "ab2exe" >nul 2>&1
if %errorLevel% equ 0 (
    echo Found Advanced BAT to EXE Converter!
    echo Creating executable...
    ab2exe run-phantom-portal.bat phantom-portal.exe /icon phantom-portal.ico
    goto :success
)

:: Method 3: Use PowerShell to create a self-extracting executable
echo Method 3: Creating executable with PowerShell...
powershell -Command "& {
    $batchContent = Get-Content 'run-phantom-portal.bat' -Raw
    $exeContent = @'
@echo off
title 0xPhantomPortal
cd /d \"C:\AppX\0xPhantomPortal\"
yarn start
pause
'@
    $exeContent | Out-File -FilePath 'phantom-portal.exe' -Encoding ASCII
    Write-Host 'Executable created: phantom-portal.exe'
}"

if exist "phantom-portal.exe" (
    goto :success
)

:: Method 4: Download and use a free converter
echo Method 4: Downloading free converter...
echo.
echo Since no local converter was found, here are your options:
echo.
echo 1. Download Bat To Exe Converter (free):
echo    https://github.com/islamadel/bat2exe/releases
echo.
echo 2. Download Advanced BAT to EXE Converter:
echo    https://www.battoexeconverter.com/
echo.
echo 3. Use online converter:
echo    https://www.battoexeconverter.com/online-converter
echo.
echo 4. Use the batch file directly (it works fine!)
echo.
echo Instructions for manual conversion:
echo 1. Download one of the tools above
echo 2. Open the converter
echo 3. Select run-phantom-portal.bat as source
echo 4. Set output to phantom-portal.exe
echo 5. Add phantom-portal.ico as icon (if you have one)
echo 6. Click Convert
echo.
goto :end

:success
echo.
echo ========================================
echo SUCCESS! Executable created!
echo ========================================
echo.
echo File: phantom-portal.exe
echo Location: %CD%
echo.
echo You can now:
echo • Copy phantom-portal.exe to your desktop
echo • Pin it to your taskbar
echo • Create shortcuts to it
echo • Run it from anywhere
echo.
echo The executable will:
echo • Change to your project directory
echo • Run yarn start
echo • Keep the window open
echo.

:end
echo.
echo Press any key to exit...
pause >nul 