# GEBCO Bathymetry Downloader

A PyQt6-based desktop application for downloading bathymetry data from ArcGIS ImageServer REST endpoints and creating GeoTIFF files with interactive area selection.

## Overview

The GEBCO Bathymetry Downloader provides an intuitive graphical interface for selecting geographic areas and downloading bathymetry data from GEBCO (General Bathymetric Chart of the Oceans) datasets. The application supports multiple data sources and output formats, allowing users to extract specific subsets of bathymetry data based on measurement types.

## Features

### Interactive Map Interface
- **Interactive map widget** with area selection using mouse drag
- **World Imagery basemap** support for geographic reference
- **GEBCO Land Grey basemap** for land visualization
- **Bathymetry visualization** with customizable display options
- **Pan and zoom** functionality
- **Coordinate display** showing selected area bounds in WGS84 (EPSG:4326)

### Data Sources

#### GEBCO 2025
- **Full global bathymetry dataset** with combined bathymetry and land elevation
- **Native resolution**: ~15 arc-seconds (~450m at equator)
- **Coordinate system**: WGS84 (EPSG:4326)
- **Extent**: Global (-180° to 180° longitude, -90° to 90° latitude)

#### GEBCO 2025 TID (Type Identifier Dataset)
- **Type identifier grid** indicating data source types
- **Same resolution and extent** as GEBCO 2025
- **Used for filtering** bathymetry data by measurement type

### Output Options (GEBCO 2025 Only)

The **Output Options** panel contains an **Output Data Types** groupbox (visible only when GEBCO 2025 is selected) that allows you to select any combination of the following output types:

1. **Combined Bathymetry & Land** (default)
   - Complete grid with both bathymetry and land elevation values
   - No filtering applied

2. **Bathymetry Only**
   - Only cells where TID ≠ 0 (water/bathymetry areas)
   - Land cells are masked out

3. **Land Only**
   - Only cells where TID = 0 (land areas)
   - Bathymetry cells are masked out

4. **Direct Measurements Only**
   - Only cells where TID is 10-20 (direct measurement sources)
   - Extracts bathymetry values from direct measurement data

5. **Direct & Unknown Measurement Only**
   - Only cells where TID is 10-20, 44, or 70
   - Includes direct measurements and unknown measurement types

### File Output

- **Format**: GeoTIFF with LZW compression
- **Data types**:
  - GEBCO 2025: Signed 16-bit integer (nodata = -32768)
  - GEBCO 2025 TID: Signed 8-bit integer (nodata = -128)
- **Coordinate system**: WGS84 (EPSG:4326)
- **Automatic filename generation** with timestamp
- **Multiple file support**: When multiple output options are selected, each generates a separate GeoTIFF file

### User Interface

The application interface is organized into several panels:

- **Map Panel**: Interactive map display with selection tools
- **Right Panel**: Contains controls and information
  - **Data Source**: Dropdown to select GEBCO 2025 or GEBCO 2025 TID
  - **Selected Area**: Coordinate display and editing (West, South, East, North)
  - **Output Options**: Contains:
    - **Output Data Types** groupbox (visible only for GEBCO 2025): Checkboxes for selecting output types
    - **Pixel count display**: Shows number of pixels in selected area
  - **Output Directory**: Button and display for selecting save location
  - **Download button**: Initiates the download process
  - **Status Log**: Real-time feedback and operation logging

### Additional Features

- **Bounds snapping**: Selected area automatically snaps to cell-size grid
- **Tile download support**: Handles large datasets by downloading in tiles
- **Progress tracking**: Real-time progress bar and status log
- **Status log**: Detailed logging of operations with bold highlighting for TID extraction messages
- **Output directory selection**: Choose where to save downloaded files
- **Coordinate validation**: Ensures valid geographic bounds

## Installation

### Requirements

- Python 3.8 or higher
- PyQt6
- rasterio
- numpy
- requests
- pyproj
- Pillow (PIL)

### Install Dependencies

```bash
pip install PyQt6 rasterio numpy requests pyproj Pillow
```

### Running the Application

```bash
python main.py
```

### Building an Executable

To create a standalone Windows executable (.exe) file:

1. **Install PyInstaller** (if not already installed):
   ```bash
   pip install pyinstaller
   ```

2. **Run the build script**:
   ```bash
   build_exe.bat
   ```
   
   Or manually run PyInstaller:
   ```bash
   pyinstaller GEBCO_Downloader.spec
   ```

3. **Find the executable**: The built executable will be located in the `dist` folder as `GEBCO_Downloader.exe`

The executable includes:
- All required dependencies bundled
- The CCOM.ico icon from the `media` directory
- No console window (GUI-only application)
- Single-file distribution (all dependencies included)

**Note**: The first build may take several minutes as PyInstaller analyzes and bundles all dependencies. Subsequent builds are faster.

## Usage

### Selecting an Area

1. **Choose Data Source**: Select "GEBCO 2025" or "GEBCO 2025 TID" from the dropdown
2. **Select Area**: Click and drag on the map to draw a selection rectangle
3. **Adjust Coordinates**: Manually edit West, South, East, North coordinates if needed
4. **View Selection**: The selected area is highlighted on the map

### Downloading Data

#### For GEBCO 2025:

1. **Select Output Data Types**: In the "Output Data Types" groupbox, check one or more of:
   - Combined Bathymetry & Land
   - Bathymetry Only
   - Land Only
   - Direct Measurements Only
   - Direct & Unknown Measurement Only
   
   Note: The "Output Data Types" groupbox is only visible when "GEBCO 2025" (not "GEBCO 2025 TID") is selected as the data source.

2. **Choose Output Location**:
   - **Single file**: If only one option is selected, you can choose a specific filename via save dialog
   - **Multiple files**: If multiple options are selected, you must select an output directory

3. **Enable Tile Download** (optional): Check "Tile Download" for large areas

4. **Click Download**: The application will:
   - Download the main bathymetry grid
   - Download TID grid if needed for filtering
   - Apply masks based on selected options
   - Generate GeoTIFF file(s) with appropriate naming

#### For GEBCO 2025 TID:

1. Select output directory or filename
2. Click Download
3. A single GeoTIFF file is generated

### Status Log

The Status Log provides real-time feedback on operations:
- **Bold messages** appear when TID-based extraction options are selected
- Progress updates during download
- Error messages if issues occur
- Success confirmation when downloads complete

### Map Controls

- **Fit to Extent**: Zoom map to show full dataset extent
- **Clear Selection**: Remove current area selection
- **Refresh Map**: Reload map display

## File Naming Convention

Files are automatically named with the following pattern:

- **GEBCO 2025**: `GEBCO_2025_<mode>_<timestamp>.tif`
  - Examples:
    - `GEBCO_2025_combined_2026-02-17_14-30-45.tif`
    - `GEBCO_2025_bathymetry_only_2026-02-17_14-30-45.tif`
    - `GEBCO_2025_direct_measurements_only_2026-02-17_14-30-45.tif`

- **GEBCO 2025 TID**: `GEBCO_2025_TID_<timestamp>.tif`

## Technical Details

### Coordinate Systems
- **Input/Output**: WGS84 (EPSG:4326) - Geographic Coordinate System
- **Internal processing**: Maintains geographic coordinates throughout

### Data Types
- **GEBCO 2025**: Signed 16-bit integer (-32768 to 32767)
  - NoData value: -32768
  - Valid bathymetry values: -32767 to 32767
  - Note: Source nodata=0 is ignored (0 is a valid bathymetry value)

- **GEBCO 2025 TID**: Signed 8-bit integer (-128 to 127)
  - NoData value: -128
  - Valid TID values: 0-127

### TID Values

The Type Identifier Dataset uses the following values:
- **0**: Land
- **10-20**: Direct measurements
- **44**: Unknown measurement type
- **70**: Unknown measurement type
- **Other values**: Various interpolated and derived data sources

## License

BSD 3-Clause License

Copyright (c) 2025, Center for Coastal and Ocean Mapping, University of New Hampshire
All rights reserved.

See LICENSE file for full license text.

## Author

Paul Johnson  
Center for Coastal and Ocean Mapping  
University of New Hampshire

## Version

2026.1 - First release

## Support

For issues, questions, or contributions, please contact the Center for Coastal and Ocean Mapping at the University of New Hampshire.
