#!/bin/bash
# Build script for World Bathymetry Downloader
# This script creates an app/executable using PyInstaller (works on Linux/Mac)

echo "Building WorldBathy executable..."
echo ""

# Check if PyInstaller is installed
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "PyInstaller is not installed. Installing..."
    pip3 install pyinstaller
    if [ $? -ne 0 ]; then
        echo "Failed to install PyInstaller. Please install it manually:"
        echo "  pip3 install pyinstaller"
        exit 1
    fi
fi

# Check if PyQt6 is installed (required for the application)
if ! python3 -c "import PyQt6" 2>/dev/null; then
    echo "WARNING: PyQt6 is not installed in this Python environment."
    echo "The app will not work without PyQt6."
    echo "Please install it: pip3 install PyQt6"
    echo ""
    read -p "Press Enter to continue anyway (build may fail)..."
fi

# Clean previous builds
rm -rf build dist

# Build using the spec file
echo "Running PyInstaller..."
pyinstaller WorldBathy_Downloader.spec --clean --noconfirm

if [ $? -ne 0 ]; then
    echo ""
    echo "Build failed! Check the error messages above."
    exit 1
fi

echo ""
echo "Build completed successfully!"
echo "The executable name includes the version from main.py (e.g. WorldBathy_V2026.2)."
echo "Output is in the 'dist' folder (e.g. dist/WorldBathy_V2026.2.app on macOS)."
echo ""
