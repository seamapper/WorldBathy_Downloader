# Building the WorldBathy Mac App

This guide explains how to create a macOS application (.app bundle) from the World Bathymetry Downloader application. The built app is named **WorldBathy_V** followed by the version from `main.py` (e.g. `WorldBathy_V2026.2.app`).

## Prerequisites

1. **macOS System**: You must build on a Mac (macOS 10.13 or later recommended)
2. **Python Environment**: Python 3.8 or higher installed
3. **Virtual Environment** (Recommended): Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
4. **Dependencies**: Install all required packages:
   ```bash
   pip install PyQt6 rasterio numpy requests pyproj Pillow pyinstaller
   ```

## Quick Start

The easiest way to build the Mac app is to use the provided build script:

1. Open Terminal
2. Navigate to the project directory:
   ```bash
   cd /path/to/your_project_folder
   ```
3. Make the script executable (if needed):
   ```bash
   chmod +x build_exe.sh
   ```
4. Run the build script:
   ```bash
   ./build_exe.sh
   ```

The script will:
- Check if PyInstaller is installed (install it if needed)
- Clean previous builds
- Build the application using the `WorldBathy_Downloader.spec` configuration file
- Create a `.app` bundle in the `dist` folder

## Manual Build Process

If you prefer to build manually or need to troubleshoot, follow these steps:

### Step 1: Activate Virtual Environment

If using a virtual environment:

```bash
source venv/bin/activate
```

### Step 2: Install PyInstaller

If PyInstaller is not already installed:

```bash
pip install pyinstaller
```

### Step 3: Verify Dependencies

Check that all required packages are installed:

```bash
python3 -c "import PyQt6, rasterio, numpy, requests, pyproj, PIL"
```

If any import fails, install the missing package:
```bash
pip install <package_name>
```

### Step 4: Clean Previous Builds (Optional)

Remove old build artifacts:

```bash
rm -rf build dist
```

### Step 5: Build the Application

Run PyInstaller with the spec file:

```bash
pyinstaller WorldBathy_Downloader.spec --clean --noconfirm
```

**Parameters explained:**
- `WorldBathy_Downloader.spec`: The configuration file that defines how to build the app
- `--clean`: Remove temporary files and cache before building
- `--noconfirm`: Overwrite output directory without asking

### Step 6: Locate the Mac App

After a successful build, the Mac app bundle will be in the `dist` folder:

```
dist/WorldBathy_V<version>.app
```

For example: `dist/WorldBathy_V2026.2.app`

The version number is automatically extracted from the `__version__` variable in `main.py`.

## Mac App Bundle Structure

A macOS `.app` bundle is actually a directory with a specific structure:

```
WorldBathy_V2026.2.app/
├── Contents/
│   ├── Info.plist          # App metadata
│   ├── MacOS/              # Executable binary
│   │   └── WorldBathy_V2026.2
│   ├── Resources/          # Resources (icons, data files)
│   │   └── CCOM.icns      # App icon (if converted)
│   └── Frameworks/         # Bundled frameworks
```

You can explore the bundle:
```bash
open dist/WorldBathy_V2026.2.app/Contents
```

## Mac-Specific Considerations

### Icon File Format

**Important**: The spec file currently references `media/CCOM.ico`, which is a Windows icon format. For macOS, you'll need an `.icns` file.

#### Option 1: Convert ICO to ICNS

If you have the original icon source, convert it to `.icns` format:

1. Use `iconutil` (built into macOS):
   ```bash
   # Create an iconset directory
   mkdir CCOM.iconset
   
   # Copy PNG files at different sizes (if you have them)
   # Or use sips to convert from ICO
   sips -s format png media/CCOM.ico --out CCOM.iconset/icon_16x16.png
   # ... repeat for other sizes (32x32, 64x64, 128x128, 256x256, 512x512, 1024x1024)
   
   # Create ICNS file
   iconutil -c icns CCOM.iconset -o media/CCOM.icns
   ```

2. Update the spec file to use the `.icns` file:
   ```python
   icon='media/CCOM.icns',  # Mac icon format
   ```

#### Option 2: Use Online Converter

Use an online tool to convert `.ico` to `.icns`, or use Image2icon or similar Mac apps.

#### Option 3: Build Without Custom Icon

The app will work without a custom icon (it will use the default Python icon). You can add the icon later by:
1. Right-click the `.app` bundle → "Get Info"
2. Drag an icon image onto the icon in the Info window

### Code Signing (Optional but Recommended)

For distribution outside the App Store, code signing helps users trust your app:

1. **Get a Developer ID** (requires Apple Developer account, $99/year)

2. **Sign the app**:
   ```bash
   codesign --deep --force --verify --verbose --sign "Developer ID Application: Your Name" dist/WorldBathy_V2026.2.app
   ```

3. **Verify signing**:
   ```bash
   codesign --verify --verbose dist/WorldBathy_V2026.2.app
   ```

### Notarization (For Distribution)

If distributing outside the App Store, notarization is required for macOS 10.15+:

1. **Create a zip file**:
   ```bash
   ditto -c -k --keepParent dist/WorldBathy_V2026.2.app WorldBathy_V2026.2.zip
   ```

2. **Submit for notarization**:
   ```bash
   xcrun altool --notarize-app \
     --primary-bundle-id "edu.unh.ccom.worldbathy" \
     --username "your-apple-id@example.com" \
     --password "@keychain:AC_PASSWORD" \
     --file WorldBathy_V2026.2.zip
   ```

3. **Check notarization status**:
   ```bash
   xcrun altool --notarization-info <request-uuid> \
     --username "your-apple-id@example.com" \
     --password "@keychain:AC_PASSWORD"
   ```

4. **Staple the notarization ticket**:
   ```bash
   xcrun stapler staple dist/WorldBathy_V2026.2.app
   ```

**Note**: Notarization requires an Apple Developer account and can take 10-30 minutes.

## Running the Mac App

### First Run: Gatekeeper Warning

On first launch, macOS may show a warning because the app isn't signed/notarized:

1. **Right-click** the `.app` bundle
2. Select **"Open"**
3. Click **"Open"** in the warning dialog

After this, you can double-click normally.

### Alternative: Remove Quarantine Attribute

If you built the app yourself, you can remove the quarantine attribute:

```bash
xattr -cr dist/WorldBathy_V2026.2.app
```

## Troubleshooting

### Error: "No module named 'PyQt6'"

**Problem**: PyInstaller cannot find PyQt6 modules.

**Solution**: 
- Ensure you're using the correct Python environment
- Verify PyQt6 is installed: `python3 -c "import PyQt6"`
- Check that PyInstaller is using the same Python interpreter

### Error: "No module named 'rasterio.sample'" (or other rasterio modules)

**Problem**: PyInstaller didn't bundle all rasterio submodules.

**Solution**: 
- The `WorldBathy_Downloader.spec` file should already include these as hidden imports
- If a new rasterio module is missing, add it to the `hiddenimports` list in the spec file
- Rebuild the app

### Error: "App can't be opened because it is from an unidentified developer"

**Problem**: macOS Gatekeeper is blocking the unsigned app.

**Solution**:
- Right-click → "Open" → "Open" (first time only)
- Or remove quarantine: `xattr -cr dist/WorldBathy_V2026.2.app`
- Or code sign the app (see Code Signing section above)

### App Crashes on Launch

**Problem**: The app crashes immediately after launching.

**Solution**:
1. **Check Console.app**: Open Console.app and look for crash logs
2. **Run from Terminal**: Launch from Terminal to see error messages:
   ```bash
   dist/WorldBathy_V2026.2.app/Contents/MacOS/WorldBathy_V2026.2
   ```
3. **Build with console enabled**: Edit the spec file temporarily:
   - Change `console=False` to `console=True`
   - Rebuild to see error output

### Build Takes Too Long

**Problem**: First build is very slow.

**Solution**: 
- This is normal for the first build (PyInstaller analyzes all dependencies)
- Subsequent builds are much faster (use `--clean` sparingly)
- The build process typically takes 2-5 minutes

### App Size is Large

**Problem**: The .app bundle is several hundred MB.

**Solution**:
- This is expected - the app includes:
  - Python interpreter
  - All Python dependencies (PyQt6, rasterio, numpy, etc.)
  - All frameworks and libraries
  - The application code
- The app is self-contained and doesn't require Python to be installed

### PyQt6 Issues on macOS

**Problem**: PyQt6 may have specific requirements on macOS.

**Solution**:
- Ensure you're using a compatible Python version (3.8+)
- Install PyQt6 using pip: `pip install PyQt6`
- If using Homebrew Python, ensure frameworks are linked correctly
- Some users may need: `pip install PyQt6 --no-binary PyQt6` (builds from source)

## Creating a DMG for Distribution

To create a disk image (.dmg) for easy distribution:

1. **Create a temporary directory structure**:
   ```bash
   mkdir -p dmg_build
   cp -R dist/WorldBathy_V2026.2.app dmg_build/
   ```

2. **Create a symbolic link to Applications**:
   ```bash
   ln -s /Applications dmg_build/Applications
   ```

3. **Create the DMG**:
   ```bash
   hdiutil create -volname "WorldBathy" \
     -srcfolder dmg_build \
     -ov -format UDZO \
     WorldBathy_V2026.2.dmg
   ```

4. **Clean up**:
   ```bash
   rm -rf dmg_build
   ```

## Build Output Structure

After building, you'll see:

```
<project_folder>/
├── build/                    # Temporary build files (can be deleted)
│   └── WorldBathy_Downloader/
├── dist/                     # Final app bundle location
│   └── WorldBathy_V2026.2.app
├── WorldBathy_Downloader.spec # PyInstaller configuration
├── build_exe.sh              # Build script
└── worldbathy_downloader_config.json  # App config (created at runtime if missing)
```

## Distribution

The `.app` bundle in the `dist` folder is standalone and can be distributed:

1. **Single Bundle**: The .app contains everything needed to run
2. **No Installation Required**: Users can drag it to Applications
3. **Portable**: Can be run from any location

**Recommended Distribution Methods:**

1. **DMG File**: Create a disk image (see above) for easy installation
2. **ZIP Archive**: Compress the .app bundle for download
3. **Direct .app**: Users can download and run directly

**Note**: For best user experience:
- Code sign the app
- Notarize the app (for macOS 10.15+)
- Create a DMG with Applications folder link
- Include a README with installation instructions

## Advanced Configuration

### Modifying the Spec File for Mac

The spec file works cross-platform, but you may want Mac-specific tweaks:

1. **Change Icon**: Update the `icon` parameter to use `.icns`:
   ```python
   icon='media/CCOM.icns',
   ```

2. **Add Info.plist Entries**: You can customize Info.plist by adding to the spec:
   ```python
   app = BUNDLE(
       exe,
       name='WorldBathy_V2026.2',
       icon='media/CCOM.icns',
       bundle_identifier='edu.unh.ccom.worldbathy',
       info_plist={
           'NSHighResolutionCapable': 'True',
           'NSRequiresAquaSystemAppearance': 'False',
       },
   )
   ```

3. **Code Signing Identity**: Add to the EXE section:
   ```python
   codesign_identity='Developer ID Application: Your Name',
   ```

### Building for Debugging

To build with debugging enabled:

1. Edit `WorldBathy_Downloader.spec`
2. Change `console=False` to `console=True`
3. Change `debug=False` to `debug=True`
4. Rebuild

This will show a Terminal window with error messages and print statements.

### Universal Binary (Apple Silicon + Intel)

To build a universal binary that works on both Apple Silicon and Intel Macs:

1. **Install dependencies for both architectures** (complex)
2. **Or build separately** and create a fat binary:
   ```bash
   # Build for Apple Silicon
   arch -arm64 pyinstaller WorldBathy_Downloader.spec
   mv dist/WorldBathy_V2026.2.app dist/WorldBathy_V2026.2_arm64.app
   
   # Build for Intel
   arch -x86_64 pyinstaller WorldBathy_Downloader.spec
   mv dist/WorldBathy_V2026.2.app dist/WorldBathy_V2026.2_x86_64.app
   
   # Create universal binary (requires lipo)
   # This is complex and may require manual framework merging
   ```

**Note**: PyInstaller typically builds for the current architecture. For universal binaries, consider using separate builds or specialized tools.

## Version Management

The app name includes the version number from `main.py`:

```python
__version__ = "2026.2"
```

The spec file automatically extracts this and creates: `WorldBathy_V2026.2.app`

To update the version:
1. Edit `__version__` in `main.py`
2. Rebuild the app
3. The new app will have the updated version number

## Additional Resources

- **PyInstaller Documentation**: https://pyinstaller.org/
- **PyInstaller Spec File**: https://pyinstaller.org/en/stable/spec-files.html
- **macOS Code Signing**: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution
- **Apple Developer**: https://developer.apple.com/

## Summary

Building the Mac app is straightforward:

1. Use the build script: `./build_exe.sh`
2. Or manually: `pyinstaller WorldBathy_Downloader.spec --clean --noconfirm`
3. Find the app in `dist/WorldBathy_V<version>.app`

The app is self-contained and ready for distribution. At runtime it reads/writes settings (e.g. output directory) from `worldbathy_downloader_config.json` in the same directory as the .app (or in the current working directory when launched). For production distribution, consider code signing and notarization.
