@echo off
title 0xPhantomPortal - Starting with Yarn

:: Set the working directory to the script location
cd /d "%~dp0"

echo ========================================
echo 0xPhantomPortal - Starting with Yarn
echo ========================================
echo.

:: Check if package.json exists
if not exist "package.json" (
    echo Error: package.json not found!
    echo Please run this script from the project root directory.
    echo Current directory: %CD%
    echo.
    pause
    exit /b 1
)

:: Check if yarn is available
echo Checking Yarn installation...
yarn --version >nul 2>&1
if %errorLevel% neq 0 (
    echo Error: Yarn is not installed or not in PATH
    echo Please install Yarn first: npm install -g yarn
    echo.
    pause
    exit /b 1
)

:: Check if node_modules exists
if not exist "node_modules" (
    echo Warning: node_modules not found!
    echo Installing dependencies...
    yarn install
    if %errorLevel% neq 0 (
        echo Error: Failed to install dependencies
        echo.
        pause
        exit /b 1
    )
)

:: Check if dist folder exists
if not exist "dist" (
    echo Warning: dist folder not found!
    echo Building the application...
    yarn build
    if %errorLevel% neq 0 (
        echo Error: Failed to build the application
        echo.
        pause
        exit /b 1
    )
)

:: Run yarn start
echo.
echo Starting 0xPhantomPortal...
echo Running: yarn start
echo.
echo Press Ctrl+C to stop the application
echo ========================================
echo.

yarn start

echo.
echo ========================================
echo 0xPhantomPortal has exited.
echo Press any key to close this window...
echo ========================================
pause >nul 