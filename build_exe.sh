#!/bin/bash
# Build script for GEBCO Bathymetry Downloader
# This script creates an executable using PyInstaller (works on Linux/Mac)

echo "Building GEBCO Bathymetry Downloader executable..."
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

# Clean previous builds
rm -rf build dist

# Build the executable using the spec file
echo "Running PyInstaller..."
pyinstaller WorldBathy_Downloader.spec

if [ $? -ne 0 ]; then
    echo ""
    echo "Build failed! Check the error messages above."
    exit 1
fi

echo ""
echo "Build completed successfully!"
echo "The executable is located in the 'dist' folder: dist/GEBCO_Downloader"
echo ""
