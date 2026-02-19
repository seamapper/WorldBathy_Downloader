@echo off
REM Build script for GEBCO Bathymetry Downloader
REM This script creates a Windows executable using PyInstaller

echo Building GEBCO Bathymetry Downloader executable...
echo.

REM Check if PyInstaller is installed
py -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed. Installing...
    py -m pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller. Please install it manually:
        echo   py -m pip install pyinstaller
        pause
        exit /b 1
    )
)

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build the executable using the spec file
echo Running PyInstaller...
py -m PyInstaller GEBCO_Downloader.spec

if errorlevel 1 (
    echo.
    echo Build failed! Check the error messages above.
    pause
    exit /b 1
)

echo.
echo Build completed successfully!
echo The executable is located in the 'dist' folder: dist\GEBCO_Downloader.exe
echo.
pause
