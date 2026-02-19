# Building the GEBCO Downloader Executable

This guide explains how to create a standalone Windows executable (.exe) file from the GEBCO Bathymetry Downloader application.

## Prerequisites

1. **Python Environment**: Ensure you have Python 3.8 or higher installed
2. **Virtual Environment**: The project uses a virtual environment located at:
   ```
   C:\Users\pjohnson\PycharmProjects\.venv
   ```
3. **Dependencies**: All required packages must be installed in the virtual environment:
   - PyQt6
   - rasterio
   - numpy
   - requests
   - pyproj
   - Pillow (PIL)
   - PyInstaller

## Quick Start

The easiest way to build the executable is to use the provided build script:

1. Open a command prompt or PowerShell window
2. Navigate to the project directory:
   ```bash
   cd C:\Users\pjohnson\PycharmProjects\GEBCO_Downloader
   ```
3. Run the build script:
   ```bash
   build_exe.bat
   ```

The script will:
- Check if PyInstaller is installed (install it if needed)
- Verify PyQt6 is available
- Clean previous builds
- Build the executable using the `WorldBathy_Downloader.spec` configuration file
- Create the executable in the `dist` folder

## Manual Build Process

If you prefer to build manually or need to troubleshoot, follow these steps:

### Step 1: Activate Virtual Environment

Ensure you're using the correct Python interpreter from the virtual environment:

```bash
C:\Users\pjohnson\PycharmProjects\.venv\Scripts\activate
```

Or use the Python executable directly:
```bash
C:\Users\pjohnson\PycharmProjects\.venv\Scripts\python.exe
```

### Step 2: Install PyInstaller

If PyInstaller is not already installed:

```bash
C:\Users\pjohnson\PycharmProjects\.venv\Scripts\python.exe -m pip install pyinstaller
```

### Step 3: Verify Dependencies

Check that all required packages are installed:

```bash
C:\Users\pjohnson\PycharmProjects\.venv\Scripts\python.exe -c "import PyQt6, rasterio, numpy, requests, pyproj, PIL"
```

If any import fails, install the missing package:
```bash
C:\Users\pjohnson\PycharmProjects\.venv\Scripts\python.exe -m pip install <package_name>
```

### Step 4: Clean Previous Builds (Optional)

Remove old build artifacts:

```bash
rmdir /s /q build
rmdir /s /q dist
```

### Step 5: Build the Executable

Run PyInstaller with the spec file:

```bash
C:\Users\pjohnson\PycharmProjects\.venv\Scripts\python.exe -m PyInstaller WorldBathy_Downloader.spec --clean --noconfirm
```

**Parameters explained:**
- `WorldBathy_Downloader.spec`: The configuration file that defines how to build the executable
- `--clean`: Remove temporary files and cache before building
- `--noconfirm`: Overwrite output directory without asking

### Step 6: Locate the Executable

After a successful build, the executable will be in the `dist` folder:

```
dist\WorldBathy_V<version>.exe
```

For example: `dist\WorldBathy_V2026.2.exe`

The version number is automatically extracted from the `__version__` variable in `main.py`.

## Understanding the Spec File

The `WorldBathy_Downloader.spec` file contains the PyInstaller configuration:

### Key Components

1. **Version Extraction**: Automatically reads the version from `main.py`
2. **Entry Point**: `main.py` is the application entry point
3. **Hidden Imports**: Explicitly includes rasterio submodules that PyInstaller might miss:
   - `rasterio.sample`
   - `rasterio.vrt`
   - `rasterio._features`
   - `rasterio._warp`
   - And other rasterio submodules
4. **Icon**: Uses `media/CCOM.ico` as the executable icon
5. **Console Window**: Set to `False` (GUI-only application)

### Why Hidden Imports Are Needed

Some Python packages (like rasterio) use dynamic imports that PyInstaller cannot automatically detect. The spec file explicitly lists these modules to ensure they're included in the executable bundle.

## Troubleshooting

### Error: "No module named 'PyQt6'"

**Problem**: PyInstaller cannot find PyQt6 modules.

**Solution**: 
- Ensure you're using the virtual environment Python
- Verify PyQt6 is installed: `python -c "import PyQt6"`
- Check that the build script uses the correct Python path

### Error: "No module named 'rasterio.sample'" (or other rasterio modules)

**Problem**: PyInstaller didn't bundle all rasterio submodules.

**Solution**: 
- The `WorldBathy_Downloader.spec` file should already include these as hidden imports
- If a new rasterio module is missing, add it to the `hiddenimports` list in the spec file
- Rebuild the executable

### Error: "Failed to execute script"

**Problem**: The executable crashes on startup.

**Solution**:
- Build with console enabled temporarily to see error messages:
  - Edit `WorldBathy_Downloader.spec` and change `console=False` to `console=True`
  - Rebuild and run to see the error output
- Check that all DLLs are bundled (especially PyQt6 and rasterio dependencies)
- Verify the icon file exists at `media/CCOM.ico`

### Build Takes Too Long

**Problem**: First build is very slow.

**Solution**: 
- This is normal for the first build (PyInstaller analyzes all dependencies)
- Subsequent builds are much faster (use `--clean` sparingly)
- The build process typically takes 1-3 minutes

### Executable Size is Large

**Problem**: The .exe file is several hundred MB.

**Solution**:
- This is expected - the executable includes:
  - Python interpreter
  - All Python dependencies (PyQt6, rasterio, numpy, etc.)
  - All DLLs and data files
  - The application code
- The executable is self-contained and doesn't require Python to be installed

## Build Output Structure

After building, you'll see:

```
GEBCO_Downloader/
├── build/              # Temporary build files (can be deleted)
│   └── GEBCO_Downloader/
├── dist/               # Final executable location
│   └── WorldBathy_V2026.2.exe
├── WorldBathy_Downloader.spec  # PyInstaller configuration
└── build_exe.bat       # Build script
```

## Distribution

The executable in the `dist` folder is standalone and can be distributed:

1. **Single File**: The .exe contains everything needed to run
2. **No Installation Required**: Users don't need Python or any dependencies
3. **Portable**: Can be run from any location (though it's recommended to keep it in a folder)

**Note**: The executable is built for Windows. To create executables for other platforms (Linux, macOS), you'll need to:
- Build on the target platform
- Use the appropriate build script (`build_exe.sh` for Linux/Mac)
- Ensure all dependencies are available for that platform

## Advanced Configuration

### Modifying the Spec File

If you need to customize the build:

1. **Add Hidden Imports**: Add module names to the `hiddenimports` list
2. **Include Data Files**: Add files to the `datas` list (e.g., `[('media/CCOM.ico', 'media')]`)
3. **Add Binary Files**: Add DLLs or other binaries to the `binaries` list
4. **Change Icon**: Modify the `icon` parameter in the `EXE` section

### Building for Debugging

To build with debugging enabled:

1. Edit `WorldBathy_Downloader.spec`
2. Change `console=False` to `console=True`
3. Change `debug=False` to `debug=True`
4. Rebuild

This will show a console window with error messages and print statements.

## Version Management

The executable name includes the version number from `main.py`:

```python
__version__ = "2026.2"
```

The spec file automatically extracts this and creates: `WorldBathy_V2026.2.exe`

To update the version:
1. Edit `__version__` in `main.py`
2. Rebuild the executable
3. The new executable will have the updated version number

## Additional Resources

- **PyInstaller Documentation**: https://pyinstaller.org/
- **PyInstaller Spec File**: https://pyinstaller.org/en/stable/spec-files.html
- **Troubleshooting Guide**: https://pyinstaller.org/en/stable/when-things-go-wrong.html

## Summary

Building the executable is straightforward:

1. Use the build script: `build_exe.bat`
2. Or manually: `python -m PyInstaller WorldBathy_Downloader.spec --clean --noconfirm`
3. Find the executable in `dist\WorldBathy_V<version>.exe`

The executable is self-contained and ready for distribution!
