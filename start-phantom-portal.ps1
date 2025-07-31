# 0xPhantomPortal Start Script (PowerShell)
# This script starts the 0xPhantomPortal application using yarn

# Set execution policy for this session
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force

# Set the working directory to the script location
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "0xPhantomPortal - Starting with Yarn" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if package.json exists
if (-not (Test-Path "package.json")) {
    Write-Host "Error: package.json not found!" -ForegroundColor Red
    Write-Host "Please run this script from the project root directory." -ForegroundColor Yellow
    Write-Host "Current directory: $(Get-Location)" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if yarn is available
Write-Host "Checking Yarn installation..." -ForegroundColor Yellow
try {
    $yarnVersion = yarn --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Yarn version: $yarnVersion" -ForegroundColor Green
    } else {
        throw "Yarn not found"
    }
} catch {
    Write-Host "Error: Yarn is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Yarn first: npm install -g yarn" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if node_modules exists
if (-not (Test-Path "node_modules")) {
    Write-Host "Warning: node_modules not found!" -ForegroundColor Yellow
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    yarn install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to install dependencies" -ForegroundColor Red
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Check if dist folder exists
if (-not (Test-Path "dist")) {
    Write-Host "Warning: dist folder not found!" -ForegroundColor Yellow
    Write-Host "Building the application..." -ForegroundColor Yellow
    yarn build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to build the application" -ForegroundColor Red
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Run yarn start
Write-Host ""
Write-Host "Starting 0xPhantomPortal..." -ForegroundColor Green
Write-Host "Running: yarn start" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop the application" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

try {
    yarn start
} catch {
    Write-Host "Error running yarn start: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "0xPhantomPortal has exited." -ForegroundColor White
Write-Host "Press Enter to close this window..." -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Read-Host 