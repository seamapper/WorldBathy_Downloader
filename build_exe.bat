@echo off
REM Build script for World Bathymetry Downloader
REM This script creates a Windows executable using PyInstaller

echo Building World Bathymetry Downloader executable...
echo(

REM Use Python from virtual environment
set VENV_PYTHON=C:\Users\pjohnson\PycharmProjects\.venv\Scripts\python.exe

REM Check if virtual environment Python exists
if not exist "%VENV_PYTHON%" (
    echo ERROR: Virtual environment Python not found at: %VENV_PYTHON%
    echo Please ensure the virtual environment is set up correctly.
    pause
    exit /b 1
)

REM Check if PyInstaller is installed
"%VENV_PYTHON%" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed. Installing...
    "%VENV_PYTHON%" -m pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller. Please install it manually:
        echo   "%VENV_PYTHON%" -m pip install pyinstaller
        pause
        exit /b 1
    )
)

REM Check if PyQt6 is installed (required for the application)
"%VENV_PYTHON%" -c "import PyQt6" 2>nul
if errorlevel 1 (
    echo WARNING: PyQt6 is not installed in this Python environment.
    echo The executable will not work without PyQt6.
    echo Please install it: "%VENV_PYTHON%" -m pip install PyQt6
    echo(
    echo Press any key to continue anyway - build may fail...
    pause >nul
)

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build the executable using the spec file
echo Running PyInstaller...
"%VENV_PYTHON%" -m PyInstaller WorldBathy_Downloader.spec

if errorlevel 1 (
    echo(
    echo Build failed! Check the error messages above.
    pause
    exit /b 1
)

echo(
echo Build completed successfully!
echo The executable name includes the version number from main.py
echo The executable is located in the 'dist' folder.
echo(
pause
