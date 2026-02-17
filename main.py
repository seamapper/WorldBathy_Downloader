"""
GEBCO Bathymetry Downloader
==========================

A PyQt6-based application for downloading bathymetry data from ArcGIS ImageServer
REST endpoints and creating GeoTIFF files with interactive area selection.

Features:
    - Interactive map widget with area selection
    - World Imagery basemap support
    - Bathymetry hillshade underlay layer
    - Multiple raster function support
    - Adjustable opacity and blend modes
    - Cell size selection (4m, 8m, 16m)
    - Coordinate system conversion (EPSG:3857, EPSG:4326)
    - Maximum download size validation
    - Automatic filename generation with timestamp

Author: Paul Johnson, Center for Coastal and Ocean Mapping, University of New Hampshire
Date: December 12, 2025

License: BSD 3-Clause License
Copyright (c) 2025, Center for Coastal and Ocean Mapping, University of New Hampshire
All rights reserved.

See LICENSE file for full license text.
"""

__version__ = "2026.1" # First release of the program

import sys
import os

# Set PROJ_LIB environment variable for PyInstaller builds
# This ensures pyproj can find its data files when running as an executable
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        proj_data_path = os.path.join(sys._MEIPASS, 'proj')
        if os.path.exists(proj_data_path):
            os.environ['PROJ_LIB'] = proj_data_path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QFileDialog, QComboBox, QProgressBar, QTextEdit,
                             QGroupBox, QMessageBox, QCheckBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from map_widget import MapWidget
from download_module import BathymetryDownloader
import requests
import json
import pyproj
from datetime import datetime


class ServiceInfoLoader(QThread):
    """Thread for loading service information asynchronously."""
    loaded = pyqtSignal(dict)  # Emits extent dict and raster functions
    error = pyqtSignal(str)  # Emits error message
    
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        
    def run(self):
        """Load service information from REST endpoint."""
        try:
            url = f"{self.base_url}?f=json"
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            # Extract extent
            extent = data.get("extent", {})
            extent_dict = {
                "xmin": extent.get("xmin", -8254538.5),
                "ymin": extent.get("ymin", 4898563.25),
                "xmax": extent.get("xmax", -7411670.5),
                "ymax": extent.get("ymax", 5636075.25)
            }
            
            # Extract raster functions
            raster_functions = ["None"]  # Always include "None" option
            raster_function_infos = data.get("rasterFunctionInfos", [])
            for rf_info in raster_function_infos:
                name = rf_info.get("name", "")
                if name and name != "None":
                    raster_functions.append(name)
            
            # Extract pixel size
            pixel_size_x = data.get("pixelSizeX", None)
            pixel_size_y = data.get("pixelSizeY", None)
            
            result = {
                "extent": extent_dict,
                "raster_functions": raster_functions,
                "pixel_size_x": pixel_size_x,
                "pixel_size_y": pixel_size_y
            }
            
            self.loaded.emit(result)
            
        except requests.exceptions.Timeout:
            self.error.emit("Connection timeout. Using default extent.")
        except requests.exceptions.RequestException as e:
            self.error.emit(f"Network error connecting to REST endpoint: {str(e)}. Using default extent.")
        except Exception as e:
            self.error.emit(f"Error loading service info: {str(e)}. Using default extent.")


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        # Data source configurations
        self.data_sources = {
            "WGOM-LI-SNE Hi Resolution": {
                "url": "https://gis.ccom.unh.edu/server/rest/services/WGOM_LI_SNE/WGOM_LI_SNE_BTY_4m_20231005_WMAS_2_IS/ImageServer",
                "bathymetry_raster_function": "StdDev - BlueGreen",
                "hillshade_raster_function": "Multidirectional Hillshade 3x",
                "default_extent": (-8254538.5, 4898559.25, -7411670.5, 5636075.25)
            },
            "WGOM-LI-SNE Regional": {
                "url": "https://gis.ccom.unh.edu/server/rest/services/WGOM_LI_SNE/WGOM_LI_SNE_BTY_20231004_16m_2_WMAS_IS/ImageServer",
                "bathymetry_raster_function": "StdDev - BlueGreen",
                "hillshade_raster_function": "Multidirectional Hillshade 3x",
                "default_extent": ( -8313630.50001078, 4898555.25001255, -7411662.50001078, 5636075.25001255)
            }
        }
        self.current_data_source = "WGOM-LI-SNE Hi Resolution"  # Default data source
        self.base_url = self.data_sources[self.current_data_source]["url"]
        # Use known extent as fallback (will be updated when service info loads)
        self.service_extent = self.data_sources[self.current_data_source]["default_extent"]
        self.pixel_size_x = None  # Pixel size in X direction from service
        self.pixel_size_y = None  # Pixel size in Y direction from service
        self.downloader = None
        self.service_loader = None
        self._updating_coordinates = False  # Flag to prevent recursive updates
        self.output_directory = None  # Store selected output directory
        self.config_file = "gebco_downloader_config.json"  # Config file path
        self._data_source_changing = False  # Flag to track when data source is changing
        
        self.init_ui()
        self.load_config()  # Load saved output directory
        self.load_service_info()
        
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle(f"GEBCO Bathymetry Downloader v{__version__} - pjohnson@ccom.unh.edu")
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel - Map
        self.map_group = QGroupBox("Map")
        self.map_group.setObjectName("Map")  # Set object name for finding
        map_layout = QVBoxLayout()
        
        # Map controls
        map_controls = QHBoxLayout()
        
        # Basemap and hillshade checkboxes (on the left)
        self.basemap_checkbox = QCheckBox("Imagery Basemap")
        self.basemap_checkbox.setChecked(True)
        self.basemap_checkbox.stateChanged.connect(self.on_basemap_toggled)
        map_controls.addWidget(self.basemap_checkbox)
        
        self.hillshade_checkbox = QCheckBox("Hillshade")
        self.hillshade_checkbox.setChecked(True)  # On by default
        self.hillshade_checkbox.stateChanged.connect(self.on_hillshade_toggled)
        map_controls.addWidget(self.hillshade_checkbox)
        
        self.legend_checkbox = QCheckBox("Legend")
        self.legend_checkbox.setChecked(False)  # Off by default
        self.legend_checkbox.stateChanged.connect(self.on_legend_toggled)
        map_controls.addWidget(self.legend_checkbox)
        
        # Buttons (to the right of checkboxes)
        self.fit_extent_btn = QPushButton("Zoom to Full Extent")
        self.fit_extent_btn.clicked.connect(self.fit_to_extent)
        self.clear_selection_btn = QPushButton("Clear Selection")
        self.clear_selection_btn.clicked.connect(self.clear_selection)
        self.refresh_map_btn = QPushButton("Refresh Map")
        self.refresh_map_btn.clicked.connect(self.refresh_map)
        map_controls.addWidget(self.fit_extent_btn)
        map_controls.addWidget(self.clear_selection_btn)
        map_controls.addWidget(self.refresh_map_btn)
        map_controls.addStretch()
        
        # Raster function will be set based on data source
        
        map_layout.addLayout(map_controls)
        
        # Map widget (will be created after service info is loaded)
        self.map_widget = None
        self.loading_label = QLabel("Loading service info...")
        map_layout.addWidget(self.loading_label)
        
        self.map_group.setLayout(map_layout)
        main_layout.addWidget(self.map_group)
        
        # Right panel - Controls
        right_panel = QWidget()
        right_panel.setFixedWidth(480)  # Fixed width: 40% of 1200px default window size
        right_layout = QVBoxLayout(right_panel)
        
        # Data Source selection
        data_source_group = QGroupBox("Data Source")
        data_source_layout = QVBoxLayout()
        
        self.data_source_combo = QComboBox()
        self.data_source_combo.addItems(list(self.data_sources.keys()))
        self.data_source_combo.setCurrentText(self.current_data_source)
        self.data_source_combo.currentTextChanged.connect(self.on_data_source_changed)
        data_source_layout.addWidget(self.data_source_combo)
        
        data_source_group.setLayout(data_source_layout)
        right_layout.addWidget(data_source_group)
        
        # Selection info
        selection_group = QGroupBox("Selected Area")
        selection_main_layout = QVBoxLayout()
        
        # Horizontal layout for coordinate groupboxes
        selection_coords_layout = QHBoxLayout()
        
        # WebMercator groupbox (left)
        webmercator_group = QGroupBox("WebMercator")
        webmercator_layout = QVBoxLayout()
        
        self.xmin_edit = QLineEdit()
        self.xmin_edit.setPlaceholderText("XMin")
        self.ymin_edit = QLineEdit()
        self.ymin_edit.setPlaceholderText("YMin")
        self.xmax_edit = QLineEdit()
        self.xmax_edit.setPlaceholderText("XMax")
        self.ymax_edit = QLineEdit()
        self.ymax_edit.setPlaceholderText("YMax")
        
        # XMin row
        xmin_row = QHBoxLayout()
        xmin_row.addWidget(QLabel("XMin:"))
        xmin_row.addWidget(self.xmin_edit)
        webmercator_layout.addLayout(xmin_row)
        
        # YMin row
        ymin_row = QHBoxLayout()
        ymin_row.addWidget(QLabel("YMin:"))
        ymin_row.addWidget(self.ymin_edit)
        webmercator_layout.addLayout(ymin_row)
        
        # XMax row
        xmax_row = QHBoxLayout()
        xmax_row.addWidget(QLabel("XMax:"))
        xmax_row.addWidget(self.xmax_edit)
        webmercator_layout.addLayout(xmax_row)
        
        # YMax row
        ymax_row = QHBoxLayout()
        ymax_row.addWidget(QLabel("YMax:"))
        ymax_row.addWidget(self.ymax_edit)
        webmercator_layout.addLayout(ymax_row)
        
        # Connect WebMercator field changes to update Geographic and map
        self.xmin_edit.editingFinished.connect(self.on_webmercator_changed)
        self.ymin_edit.editingFinished.connect(self.on_webmercator_changed)
        self.xmax_edit.editingFinished.connect(self.on_webmercator_changed)
        self.ymax_edit.editingFinished.connect(self.on_webmercator_changed)
        
        webmercator_group.setLayout(webmercator_layout)
        selection_coords_layout.addWidget(webmercator_group)
        
        # Geographic groupbox (right)
        geographic_group = QGroupBox("Geographic")
        geographic_layout = QVBoxLayout()
        
        self.west_edit = QLineEdit()
        self.west_edit.setPlaceholderText("West")
        self.south_edit = QLineEdit()
        self.south_edit.setPlaceholderText("South")
        self.east_edit = QLineEdit()
        self.east_edit.setPlaceholderText("East")
        self.north_edit = QLineEdit()
        self.north_edit.setPlaceholderText("North")
        
        # Connect Geographic field changes to update WebMercator and map
        self.west_edit.editingFinished.connect(self.on_geographic_changed)
        self.south_edit.editingFinished.connect(self.on_geographic_changed)
        self.east_edit.editingFinished.connect(self.on_geographic_changed)
        self.north_edit.editingFinished.connect(self.on_geographic_changed)
        
        # West row
        west_row = QHBoxLayout()
        west_row.addWidget(QLabel("West:"))
        west_row.addWidget(self.west_edit)
        geographic_layout.addLayout(west_row)
        
        # South row
        south_row = QHBoxLayout()
        south_row.addWidget(QLabel("South:"))
        south_row.addWidget(self.south_edit)
        geographic_layout.addLayout(south_row)
        
        # East row
        east_row = QHBoxLayout()
        east_row.addWidget(QLabel("East:"))
        east_row.addWidget(self.east_edit)
        geographic_layout.addLayout(east_row)
        
        # North row
        north_row = QHBoxLayout()
        north_row.addWidget(QLabel("North:"))
        north_row.addWidget(self.north_edit)
        geographic_layout.addLayout(north_row)
        
        geographic_group.setLayout(geographic_layout)
        selection_coords_layout.addWidget(geographic_group)
        
        selection_main_layout.addLayout(selection_coords_layout)
        
        selection_group.setLayout(selection_main_layout)
        right_layout.addWidget(selection_group)
        
        # Output options
        output_group = QGroupBox("Output Options")
        output_layout = QVBoxLayout()  # Vertical layout to accommodate pixel count at bottom
        
        # Top row: Cell size and CRS side by side
        output_top_layout = QHBoxLayout()
        
        # Left side: Cell size selector (label and dropdown on same line)
        cell_size_row = QHBoxLayout()
        cell_size_row.addWidget(QLabel("Cell Size (m):"))
        self.cell_size_combo = QComboBox()
        # Initial values will be set when service info loads
        # For now, use default values as placeholder
        self.cell_size_combo.addItems(["4", "8", "16"])
        self.cell_size_combo.setCurrentText("4")  # Default to first option
        self.cell_size_combo.setMinimumWidth(100)  # Make dropdown wider
        self.cell_size_combo.currentTextChanged.connect(self.on_cell_size_changed)
        cell_size_row.addWidget(self.cell_size_combo)
        cell_size_row.addStretch()  # Push to left side
        output_top_layout.addLayout(cell_size_row)
        
        # Right side: Output CRS selector (label and dropdown on same line)
        crs_row = QHBoxLayout()
        crs_row.addWidget(QLabel("Output CRS:"))
        self.crs_combo = QComboBox()
        self.crs_combo.addItems(["EPSG:3857", "EPSG:4326"])
        crs_row.addWidget(self.crs_combo)
        crs_row.addStretch()  # Push to right side
        output_top_layout.addLayout(crs_row)
        
        output_layout.addLayout(output_top_layout)
        
        # Pixel count display at the bottom
        self.pixel_count_label = QLabel("Pixels: --")
        self.pixel_count_label.setStyleSheet("font-weight: bold; padding: 5px;")
        output_layout.addWidget(self.pixel_count_label)
        
        output_group.setLayout(output_layout)
        right_layout.addWidget(output_group)
        
        # Output directory selection
        output_dir_btn = QPushButton("Select Output Directory")
        output_dir_btn.clicked.connect(self.select_output_directory)
        right_layout.addWidget(output_dir_btn)
        
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(QLabel("Directory:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("Not set")
        self.output_dir_edit.setReadOnly(True)  # Make it read-only, user clicks button to change
        output_dir_layout.addWidget(self.output_dir_edit, stretch=1)
        
        right_layout.addLayout(output_dir_layout)
        
        # Download and Export buttons (side by side)
        button_layout = QHBoxLayout()
        self.download_btn = QPushButton("Download Selected Area")
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setEnabled(False)
        button_layout.addWidget(self.download_btn)
        
        self.export_image_btn = QPushButton("Export Image")
        self.export_image_btn.clicked.connect(self.export_map_image)
        button_layout.addWidget(self.export_image_btn)
        
        right_layout.addLayout(button_layout)
        
        # Tile download checkbox
        self.tile_download_checkbox = QCheckBox("Tile Download")
        self.tile_download_checkbox.setChecked(True)  # On by default
        right_layout.addWidget(self.tile_download_checkbox)
        
        # Progress
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready")
        progress_layout.addWidget(self.status_label)
        
        progress_group.setLayout(progress_layout)
        right_layout.addWidget(progress_group)
        
        # Status log
        log_group = QGroupBox("Status Log")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        # Remove maximum height so it can expand to fill available space
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        right_layout.addWidget(log_group, 1)  # Add stretch factor to make it expand
        
        main_layout.addWidget(right_panel)
        
        # Map panel will take all remaining space (stretch=1), right panel has fixed width
        main_layout.setStretch(0, 1)  # Map panel: takes remaining space
        main_layout.setStretch(1, 0)  # Right panel: fixed width, no stretch
        
    def load_service_info(self):
        """Load service information from REST endpoint in background thread."""
        # Start with default extent and initialize map immediately
        self.log_message("Initializing map widget with default extent...")
        self.init_map_widget()
        if self.map_widget:
            self.log_message("Map widget created successfully on startup")
        else:
            self.log_message("WARNING: Map widget is None after initial creation attempt")
        
        # Try to load actual service info in background
        self.service_loader = ServiceInfoLoader(self.base_url)
        self.service_loader.loaded.connect(self.on_service_info_loaded)
        self.service_loader.error.connect(self.on_service_info_error)
        self.service_loader.start()
        
    def on_service_info_loaded(self, service_data):
        """Handle successful service info load."""
        extent_dict = service_data.get("extent", {})
        self.service_extent = (
            extent_dict["xmin"],
            extent_dict["ymin"],
            extent_dict["xmax"],
            extent_dict["ymax"]
        )
        self.log_message("Service info loaded successfully")
        self.log_message(f"REST endpoint extent (bathymetry data bounds): {self.service_extent}")
        
        # Don't set default bounds here - wait until map loads so extent is correct
        # Default bounds will be set in on_map_first_loaded after map loads with correct extent
        
        # Update cell size dropdown based on pixel size from service
        pixel_size_x = service_data.get("pixel_size_x")
        pixel_size_y = service_data.get("pixel_size_y")
        # Store pixel sizes for use in raster function selection
        self.pixel_size_x = pixel_size_x
        self.pixel_size_y = pixel_size_y
        if pixel_size_x is not None and pixel_size_y is not None:
            # Base cell size is the larger of pixelSizeX and pixelSizeY
            base_cell_size = max(abs(pixel_size_x), abs(pixel_size_y))
            # Force highest resolution when data source is changing
            self.update_cell_size_options(base_cell_size, force_highest_resolution=self._data_source_changing)
        else:
            # Fallback to default values if pixel size not available
            self.log_message("Warning: Pixel size not available from service, using default cell sizes")
            self.update_cell_size_options(4.0, force_highest_resolution=self._data_source_changing)  # Default to 4m if pixel size unavailable
        
        # Reset flag after updating cell size options
        self._data_source_changing = False
        
        # Raster function is fixed to "DAR - StdDev - BlueGreen" - no need to update combo box
        
        # Ensure map widget is initialized (this will remove loading label)
        if self.map_widget is None:
            self.log_message("Initializing map widget...")
            self.init_map_widget()
        
        # Update map extent (but don't reload if map widget already exists and is loading)
        if self.map_widget:
            # Check if base URL has changed (data source switch) BEFORE updating it
            url_changed = self.map_widget.base_url != self.base_url
            
            # Update pixel sizes in map widget from service info (this happens after service loads)
            self.map_widget.pixel_size_x = self.pixel_size_x
            self.map_widget.pixel_size_y = self.pixel_size_y
            
            self.map_widget.base_url = self.base_url
            
            # Update raster functions from current data source
            new_raster_function = self.data_sources[self.current_data_source]["bathymetry_raster_function"]
            new_hillshade_raster_function = self.data_sources[self.current_data_source]["hillshade_raster_function"]
            self.map_widget.raster_function = new_raster_function
            self.map_widget.hillshade_raster_function = new_hillshade_raster_function
            
            # Always set extent to REST endpoint service extent as a baseline
            # This ensures the map shows exactly the bathymetry data bounds from the REST endpoint
            # If there's a pending selection, zoom_to_selection will override it
            self.log_message(f"Updating map extent to REST endpoint extent: {self.service_extent}")
            self.map_widget.extent = self.service_extent
            # Also update _requested_extent to ensure coordinate conversion is correct
            # This ensures the map displays exactly the REST endpoint bounds, not a rounded or adjusted version
            self.map_widget._requested_extent = self.service_extent
            # Update service extent in map widget so it can distinguish dataset bounds from user selection
            self.map_widget.service_extent = self.service_extent
            # CRITICAL: Always update selected_bbox_world to REST endpoint extent if it matches default extent
            # This ensures the box shows the exact REST endpoint bounds, not the default extent
            # Check if selected_bbox_world is None OR if it matches the default extent (needs update)
            default_extent = self.data_sources[self.current_data_source]["default_extent"]
            needs_update = (
                self.map_widget.selected_bbox_world is None or
                self.map_widget.selected_bbox_world == default_extent
            )
            if needs_update:
                self.log_message(f"Updating selected_bbox_world from {self.map_widget.selected_bbox_world} to REST endpoint extent {self.service_extent}")
                self.map_widget.selected_bbox_world = self.service_extent
                self.map_widget.set_selection_validity(True)
                self.selected_bbox = self.service_extent
                # Update coordinate display to show REST endpoint bounds
                self.update_coordinate_display(*self.service_extent, update_map=False)
            if hasattr(self, '_pending_selection') and self._pending_selection:
                self.log_message(f"Preserving selection, will zoom to it after map loads")
            
            # CRITICAL: Always reload map with REST endpoint extent to ensure it shows exact bathymetry data bounds
            # Check if the map was loaded with a different extent (e.g., default extent)
            current_extent = self.map_widget.extent
            default_extent = self.data_sources[self.current_data_source]["default_extent"]
            
            # Check if map was loaded with default extent (needs reload with REST endpoint extent)
            extent_matches_default = (
                abs(current_extent[0] - default_extent[0]) < 0.1 and
                abs(current_extent[1] - default_extent[1]) < 0.1 and
                abs(current_extent[2] - default_extent[2]) < 0.1 and
                abs(current_extent[3] - default_extent[3]) < 0.1
            )
            
            # Ensure default bounds are set
            if self.map_widget.selected_bbox_world is None:
                self.map_widget.selected_bbox_world = self.service_extent
                self.map_widget.set_selection_validity(True)
                self.selected_bbox = self.service_extent
                self.map_widget.service_extent = self.service_extent
                self.log_message(f"Set default bounds to REST endpoint extent: {self.service_extent}")
            
            # Force reload if URL changed (data source switch) or if extent differs
            if url_changed or current_extent != self.service_extent or extent_matches_default:
                if url_changed:
                    self.log_message(f"Data source URL changed, reloading map with new service...")
                else:
                    self.log_message(f"Map extent ({current_extent}) differs from REST endpoint extent ({self.service_extent}), zooming to REST endpoint bounds...")
                if not getattr(self.map_widget, '_loading', False):
                    # CRITICAL: Use zoom_to_selection directly (like when user hits return)
                    # This recalculates the extent with padding and positions the box correctly
                    # Don't reload first - zoom_to_selection will reload with the correct extent
                    # Wait a bit longer to ensure widget is fully sized
                    QTimer.singleShot(300, lambda: self.zoom_to_selection(*self.service_extent))
            elif not self.map_widget.map_loaded and not getattr(self.map_widget, '_loading', False):
                self.log_message("Map not loaded yet, will load and zoom to REST endpoint extent...")
                # Map hasn't loaded yet - use zoom_to_selection which will load the map with correct extent
                # zoom_to_selection will:
                # 1. Calculate extent with padding
                # 2. Set map widget extent
                # 3. Call load_map() to reload basemap and raster layers
                # Wait a bit longer to ensure widget is fully sized
                QTimer.singleShot(300, lambda: self.zoom_to_selection(*self.service_extent))
            else:
                self.log_message("Map already loaded with REST endpoint extent")
        else:
            self.log_message("ERROR: Map widget is None after initialization attempt")
            
    def on_service_info_error(self, error_message):
        """Handle service info load error with helpful message."""
        # Log the error
        self.log_message(error_message)
        
        # Show error message with suggestion to check for updates
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Connection Error")
        msg.setText(
            f"Unable to connect to the REST endpoint.\n\n"
            f"{error_message}\n\n"
            f"If this problem persists, please:\n"
            f"1. Check for a new version at: https://github.com/seamapper/GEBCO_Downloader\n"
            f"2. Contact: pjohnson@ccom.unh.edu"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        
        # Continue with default extent - map should already be initialized
            
    def init_map_widget(self):
        """Initialize the map widget."""
        if self.service_extent is None:
            self.log_message("ERROR: service_extent is None, cannot initialize map")
            return
            
        # Get map group and layout - use stored reference
        if not hasattr(self, 'map_group') or not self.map_group:
            self.log_message("ERROR: map_group not found")
            return
            
        layout = self.map_group.layout()
        if not layout:
            self.log_message("ERROR: Map QGroupBox has no layout")
            return
            
        # Remove loading label if it exists - try multiple approaches
        label_removed = False
        
        # First, try to remove via the stored reference
        if hasattr(self, 'loading_label') and self.loading_label:
            try:
                layout.removeWidget(self.loading_label)
                self.loading_label.hide()
                self.loading_label.setParent(None)
                self.loading_label.deleteLater()
                self.loading_label = None
                label_removed = True
            except:
                pass
        
        # Also search for any QLabel with "Loading" text in the layout
        if not label_removed:
            for i in reversed(range(layout.count())):
                item = layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if isinstance(widget, QLabel) and "Loading" in widget.text():
                        try:
                            layout.removeWidget(widget)
                            widget.hide()
                            widget.setParent(None)
                            widget.deleteLater()
                            label_removed = True
                            break
                        except:
                            pass
                    
        # Create map widget if it doesn't exist
        if self.map_widget is None:
            try:
                # Get raster functions from current data source
                raster_function = self.data_sources[self.current_data_source]["bathymetry_raster_function"]
                hillshade_raster_function = self.data_sources[self.current_data_source]["hillshade_raster_function"]
                show_basemap = self.basemap_checkbox.isChecked() if hasattr(self, 'basemap_checkbox') else True
                show_hillshade = self.hillshade_checkbox.isChecked() if hasattr(self, 'hillshade_checkbox') else True
                # Blend mode is automatically enabled when hillshade is enabled
                use_blend = show_hillshade
                self.log_message(f"Creating MapWidget with extent: {self.service_extent}, raster function: {raster_function}, show_basemap: {show_basemap}, show_hillshade: {show_hillshade}, use_blend: {use_blend}")
                self.map_widget = MapWidget(self.base_url, self.service_extent, raster_function=raster_function, show_basemap=show_basemap, show_hillshade=show_hillshade, use_blend=use_blend, hillshade_raster_function=hillshade_raster_function)
                self.map_widget.bathymetry_opacity = 1.0  # Full opacity
                # Store service extent in map widget so it can distinguish dataset bounds from user selection
                self.map_widget.service_extent = self.service_extent
                # Store pixel sizes for raster function selection
                self.map_widget.pixel_size_x = self.pixel_size_x
                self.map_widget.pixel_size_y = self.pixel_size_y
                self.map_widget.selectionChanged.connect(self.on_selection_changed)
                self.map_widget.selectionCompleted.connect(self.on_selection_completed)
                self.map_widget.mapFirstLoaded.connect(self.on_map_first_loaded)
                self.map_widget.statusMessage.connect(self.log_message)  # Connect status messages to log
                layout.addWidget(self.map_widget)
                self.map_widget.show()
                # Force UI update
                self.map_group.update()
                layout.update()
                self.log_message("MapWidget created and added to layout successfully")
                
                # Don't set default bounds here - wait until map loads so extent is correct
                # Default bounds will be set in on_map_first_loaded after map loads
                
                # Trigger map load after a short delay to ensure widget is sized
                self.log_message("Scheduling map load in 200ms...")
                QTimer.singleShot(200, lambda: self.trigger_map_load())
            except Exception as e:
                self.log_message(f"ERROR creating MapWidget: {e}")
                import traceback
                self.log_message(traceback.format_exc())
                self.map_widget = None
                
    def trigger_map_load(self):
        """Trigger map load - called via timer."""
        # Don't load here - let on_service_info_loaded handle it
        # This ensures REST endpoint extent is available and widget is properly sized
        if self.map_widget:
            if self.service_extent:
                self.log_message(f"Widget ready, waiting for service info to trigger map load...")
                self.log_message(f"Widget size: {self.map_widget.width()}x{self.map_widget.height()}")
                self.log_message(f"REST endpoint extent: {self.service_extent}")
            else:
                self.log_message("REST endpoint extent not available yet, waiting for service info to load...")
        else:
            self.log_message("ERROR: map_widget is None when trying to trigger load")
            
    def fit_to_extent(self):
        """Fit map to full service extent - same as initial load with padding."""
        if self.map_widget and self.service_extent:
            # Use zoom_to_selection to zoom to service extent with padding (same as initial load)
            # This ensures the same behavior as the initial load: adds 5% padding and adjusts for widget aspect ratio
            self.map_widget.selected_bbox_world = self.service_extent
            self.map_widget.set_selection_validity(True)
            self.selected_bbox = self.service_extent
            self.map_widget.service_extent = self.service_extent
            # Use zoom_to_selection which will add padding and reload the map
            self.zoom_to_selection(*self.service_extent)
            # Update coordinate display to show the service extent
            self.update_coordinate_display(*self.service_extent, update_map=False)
            
    def clear_selection(self):
        """Clear the map selection."""
        if self.map_widget:
            self.map_widget.clear_selection()
        # Remove bold formatting from download button when selection is cleared
        if hasattr(self, 'download_btn'):
            font = self.download_btn.font()
            font.setBold(False)
            self.download_btn.setFont(font)
    
    def refresh_map(self):
        """Refresh the map display for the currently shown area."""
        if self.map_widget:
            self.log_message("Refreshing map display...")
            self.map_widget.load_map()
        else:
            self.log_message("Warning: Map widget not available for refresh")
    
    def export_map_image(self):
        """Export the current map display as a PNG image."""
        if not self.map_widget:
            self.log_message("Warning: Map widget not available for export")
            QMessageBox.warning(self, "Export Error", "Map widget not available.")
            return
        
        if not self.map_widget.map_loaded:
            self.log_message("Warning: Map not loaded yet")
            QMessageBox.warning(self, "Export Error", "Map is not loaded yet. Please wait for the map to load.")
            return
        
        # Generate default filename with timestamp
        from datetime import datetime
        date_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"GEBCO_Map_{date_time_str}.png"
        
        # Determine save location
        if self.output_directory and os.path.isdir(self.output_directory):
            default_path = os.path.join(self.output_directory, default_filename)
        else:
            default_path = default_filename
        
        # Prompt for save location
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Map Image",
            default_path,
            "PNG Files (*.png);;All Files (*)"
        )
        
        if not file_path:
            return  # User cancelled
        
        try:
            # Grab the map widget as a pixmap
            pixmap = self.map_widget.grab()
            
            if pixmap.isNull():
                raise Exception("Failed to capture map widget")
            
            # Save to file
            if not pixmap.save(file_path, "PNG"):
                raise Exception("Failed to save PNG file")
            
            self.log_message(f"✓ Map image exported: {file_path}")
            QMessageBox.information(self, "Success", f"Map image saved to:\n{file_path}")
            
        except Exception as e:
            error_msg = f"Error exporting map image: {str(e)}"
            self.log_message(f"✗ {error_msg}")
            QMessageBox.critical(self, "Export Error", error_msg)
            
    # Raster function is fixed to "DAR - StdDev - BlueGreen" - no handler needed
            
    def on_basemap_toggled(self, state):
        """Handle basemap checkbox toggle."""
        if self.map_widget:
            show_basemap = (state == Qt.CheckState.Checked.value or state == 2)
            self.map_widget.show_basemap = show_basemap
            if show_basemap:
                # Reload map to get basemap
                self.map_widget.load_map()
            else:
                # Just update display
                self.map_widget.update()
                
    def on_hillshade_toggled(self, state):
        """Handle hillshade checkbox toggle."""
        if self.map_widget:
            show_hillshade = (state == Qt.CheckState.Checked.value or state == 2)
            self.map_widget.show_hillshade = show_hillshade
            # Automatically enable/disable blend mode based on hillshade state
            self.map_widget.use_blend = show_hillshade
            if show_hillshade:
                # Reload map to get hillshade layer
                self.map_widget.load_map()
            else:
                # Just update display (blend will be off automatically)
                self.map_widget.update()
    
    def on_legend_toggled(self, state):
        """Handle legend checkbox toggle."""
        if self.map_widget:
            show_legend = (state == Qt.CheckState.Checked.value or state == 2)
            self.map_widget.show_legend = show_legend
            # Just update display (no need to reload map)
            self.map_widget.update()
                
    def check_and_update_download_button(self):
        """Check if selection is valid and within size limits, update download button state."""
        # Check if there's a valid selection
        bbox = None
        if hasattr(self, 'selected_bbox') and self.selected_bbox:
            bbox = self.selected_bbox
        elif self.map_widget:
            bbox = self.map_widget.get_selection_bbox()
        
        if not bbox:
            # No selection - disable button and clear selection validity
            self.download_btn.setEnabled(False)
            # Remove bold formatting when no selection
            font = self.download_btn.font()
            font.setBold(False)
            self.download_btn.setFont(font)
            if self.map_widget:
                self.map_widget.set_selection_validity(True)  # Default to valid (no selection shown)
            return
        
        # Check if selection exceeds maximum size
        try:
            xmin, ymin, xmax, ymax = bbox
            cell_size = float(self.cell_size_combo.currentText()) if hasattr(self, 'cell_size_combo') else 4.0
            width_meters = xmax - xmin
            height_meters = ymax - ymin
            pixels_width = int(width_meters / cell_size)
            pixels_height = int(height_meters / cell_size)
            
            # No size limit - always enable download button
            # Warning dialog will be shown when downloading large datasets
            is_valid = True
            
            # Update map widget selection color (always valid now)
            if self.map_widget:
                self.map_widget.set_selection_validity(is_valid)
            
            # Always enable download button (size limit removed with tiling support)
            self.download_btn.setEnabled(True)
            # Make text bold only if this is a user manual selection (not initial dataset bounds)
            # Check if selection matches service extent (initial dataset bounds)
            is_initial_bounds = False
            if hasattr(self, 'service_extent') and self.service_extent:
                se = self.service_extent
                # Use tolerance for floating point comparison
                tol = 0.1  # 0.1 meter tolerance
                if (abs(se[0] - xmin) < tol and abs(se[1] - ymin) < tol and
                    abs(se[2] - xmax) < tol and abs(se[3] - ymax) < tol):
                    is_initial_bounds = True
            
            # Only make bold if it's NOT the initial dataset bounds
            font = self.download_btn.font()
            font.setBold(not is_initial_bounds)
            self.download_btn.setFont(font)
        except Exception:
            # Error calculating - disable button to be safe
            self.download_btn.setEnabled(False)
            # Remove bold formatting on error
            font = self.download_btn.font()
            font.setBold(False)
            self.download_btn.setFont(font)
            if self.map_widget:
                self.map_widget.set_selection_validity(True)  # Default to valid on error
    
    def update_cell_size_options(self, base_cell_size, force_highest_resolution=False):
        """Update cell size dropdown options based on base cell size from service.
        
        Args:
            base_cell_size: The base cell size (max of pixelSizeX and pixelSizeY)
            force_highest_resolution: If True, always select the highest resolution (smallest cell size)
        """
        if not hasattr(self, 'cell_size_combo'):
            return
        
        # Calculate the five options: base, 2x, 3x, 4x, 5x
        option1 = base_cell_size  # Highest resolution (smallest cell size)
        option2 = base_cell_size * 2
        option3 = base_cell_size * 3
        option4 = base_cell_size * 4
        option5 = base_cell_size * 5
        
        # Store current selection if exists (only if not forcing highest resolution)
        current_text = self.cell_size_combo.currentText() if not force_highest_resolution else None
        
        # Clear and repopulate dropdown
        self.cell_size_combo.clear()
        self.cell_size_combo.addItems([f"{option1:.1f}", f"{option2:.1f}", f"{option3:.1f}", f"{option4:.1f}", f"{option5:.1f}"])
        
        if force_highest_resolution:
            # Always select the highest resolution (first option, smallest cell size)
            self.cell_size_combo.setCurrentIndex(0)
        else:
            # Try to restore previous selection if it matches one of the new options
            # Otherwise, select the first (smallest) option
            try:
                current_value = float(current_text)
                # Find closest match
                options = [option1, option2, option3, option4, option5]
                closest_idx = min(range(len(options)), key=lambda i: abs(options[i] - current_value))
                self.cell_size_combo.setCurrentIndex(closest_idx)
            except (ValueError, TypeError):
                # If previous selection was invalid, default to first option
                self.cell_size_combo.setCurrentIndex(0)
        
        # Update pixel count if selection exists
        if hasattr(self, 'selected_bbox') and self.selected_bbox:
            xmin, ymin, xmax, ymax = self.selected_bbox
            self.update_coordinate_display(xmin, ymin, xmax, ymax, update_map=False)
    
    def on_cell_size_changed(self, cell_size_text):
        """Handle cell size change - update pixel count if selection exists."""
        # Update pixel count display if there's a current selection
        if hasattr(self, 'selected_bbox') and self.selected_bbox:
            xmin, ymin, xmax, ymax = self.selected_bbox
            self.update_coordinate_display(xmin, ymin, xmax, ymax, update_map=False)
        # Update download button state
        self.check_and_update_download_button()
            
    def on_webmercator_changed(self):
        """Handle manual entry in WebMercator fields."""
        if self._updating_coordinates:
            return
            
        try:
            # Get values from WebMercator fields
            xmin_text = self.xmin_edit.text().strip()
            ymin_text = self.ymin_edit.text().strip()
            xmax_text = self.xmax_edit.text().strip()
            ymax_text = self.ymax_edit.text().strip()
            
            # Check if all fields have values
            if not (xmin_text and ymin_text and xmax_text and ymax_text):
                return
            
            xmin = float(xmin_text)
            ymin = float(ymin_text)
            xmax = float(xmax_text)
            ymax = float(ymax_text)
            
            # Validate that min < max
            if xmin >= xmax or ymin >= ymax:
                QMessageBox.warning(self, "Invalid Coordinates", "XMin must be less than XMax and YMin must be less than YMax.")
                return
            
            # Update the selection
            self.update_coordinate_display(xmin, ymin, xmax, ymax, update_map=True)
            # Button state will be updated by update_coordinate_display
            
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric coordinates.")
            self.check_and_update_download_button()  # Disable button on invalid input
            
    def on_geographic_changed(self):
        """Handle manual entry in Geographic fields."""
        if self._updating_coordinates:
            return
            
        try:
            # Get values from Geographic fields
            west_text = self.west_edit.text().strip()
            south_text = self.south_edit.text().strip()
            east_text = self.east_edit.text().strip()
            north_text = self.north_edit.text().strip()
            
            # Check if all fields have values
            if not (west_text and south_text and east_text and north_text):
                return
            
            west = float(west_text)
            south = float(south_text)
            east = float(east_text)
            north = float(north_text)
            
            # Validate that min < max
            if west >= east or south >= north:
                QMessageBox.warning(self, "Invalid Coordinates", "West must be less than East and South must be less than North.")
                return
            
            # Convert to WebMercator
            try:
                transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
                xmin, ymin = transformer.transform(west, south)
                xmax, ymax = transformer.transform(east, north)
                
                # Update the selection
                self.update_coordinate_display(xmin, ymin, xmax, ymax, update_map=True)
                # Button state will be updated by update_coordinate_display
            except Exception as e:
                QMessageBox.warning(self, "Conversion Error", f"Error converting coordinates: {str(e)}")
                self.check_and_update_download_button()  # Disable button on conversion error
                
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric coordinates.")
            self.check_and_update_download_button()  # Disable button on invalid input
            
    def update_coordinate_display(self, xmin, ymin, xmax, ymax, update_map=True):
        """Update both WebMercator and Geographic coordinate displays."""
        if self._updating_coordinates:
            return  # Prevent recursive updates
            
        self._updating_coordinates = True
        
        try:
            # Update WebMercator coordinates
            self.xmin_edit.setText(f"{xmin:.2f}")
            self.ymin_edit.setText(f"{ymin:.2f}")
            self.xmax_edit.setText(f"{xmax:.2f}")
            self.ymax_edit.setText(f"{ymax:.2f}")
            
            # Convert to Geographic (WGS84) coordinates
            try:
                transformer = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
                west, south = transformer.transform(xmin, ymin)
                east, north = transformer.transform(xmax, ymax)
                
                # Update Geographic coordinates
                self.west_edit.setText(f"{west:.6f}")
                self.south_edit.setText(f"{south:.6f}")
                self.east_edit.setText(f"{east:.6f}")
                self.north_edit.setText(f"{north:.6f}")
            except Exception as e:
                # If conversion fails, clear geographic fields
                self.west_edit.clear()
                self.south_edit.clear()
                self.east_edit.clear()
                self.north_edit.clear()
            
            # Update stored selection and map if requested
            if update_map:
                self.selected_bbox = (xmin, ymin, xmax, ymax)
                if self.map_widget:
                    self.zoom_to_selection(xmin, ymin, xmax, ymax)
        finally:
            self._updating_coordinates = False
        
        # Update download button state
        self.check_and_update_download_button()
        
        # Calculate expected number of pixels based on selected cell size (for download)
        try:
            width_meters = xmax - xmin
            height_meters = ymax - ymin
            # Get cell size from dropdown (default to 4 if not available)
            if hasattr(self, 'cell_size_combo') and self.cell_size_combo.currentText():
                cell_size = float(self.cell_size_combo.currentText())
            else:
                cell_size = 4.0
            
            pixels_width = int(width_meters / cell_size)
            pixels_height = int(height_meters / cell_size)
            total_pixels = pixels_width * pixels_height
            
            # Format with thousand separators
            pixels_width_str = f"{pixels_width:,}"
            pixels_height_str = f"{pixels_height:,}"
            total_pixels_str = f"{total_pixels:,}"
            
            # Show warning for large datasets (> 10,000 pixels in a dimension)
            large_size_threshold = 10000
            is_large = pixels_width > large_size_threshold or pixels_height > large_size_threshold
            
            if is_large:
                # Show warning in orange/yellow for large datasets
                self.pixel_count_label.setText(
                    f"⚠️ Pixels ({cell_size}m): {pixels_width_str} × {pixels_height_str} = {total_pixels_str} "
                    f"(LARGE DATASET!)"
                )
                self.pixel_count_label.setStyleSheet("font-weight: bold; padding: 5px; color: orange;")
            else:
                self.pixel_count_label.setText(
                    f"Pixels ({cell_size}m): {pixels_width_str} × {pixels_height_str} = {total_pixels_str}"
                )
                self.pixel_count_label.setStyleSheet("font-weight: bold; padding: 5px;")
        except Exception as e:
            self.pixel_count_label.setText("Pixels: --")
            self.pixel_count_label.setStyleSheet("font-weight: bold; padding: 5px;")
            
    def on_selection_changed(self, xmin, ymin, xmax, ymax):
        """Handle selection change from map (during dragging)."""
        if xmin == 0 and ymin == 0 and xmax == 0 and ymax == 0:
            # Selection cleared
            self.xmin_edit.clear()
            self.ymin_edit.clear()
            self.xmax_edit.clear()
            self.ymax_edit.clear()
            self.west_edit.clear()
            self.south_edit.clear()
            self.east_edit.clear()
            self.north_edit.clear()
            self.pixel_count_label.setText("Pixels: --")
            self.selected_bbox = None
            self.download_btn.setEnabled(False)
        else:
            # Show real-time values while selecting (without updating map to avoid recursion)
            self.update_coordinate_display(xmin, ymin, xmax, ymax, update_map=False)
            # Button state will be updated by update_coordinate_display (which calls check_and_update_download_button)
            
    def on_selection_completed(self, xmin, ymin, xmax, ymax):
        """Handle selection completion (when mouse is released) - zoom to selection."""
        if xmin != 0 or ymin != 0 or xmax != 0 or ymax != 0:
            # Store the selected bbox for download
            self.selected_bbox = (xmin, ymin, xmax, ymax)
            # Temporarily disconnect the selection changed signal to prevent clearing
            self.map_widget.selectionChanged.disconnect()
            self.zoom_to_selection(xmin, ymin, xmax, ymax)
            # Reconnect the signal
            self.map_widget.selectionChanged.connect(self.on_selection_changed)
            # Set the final bounds in the text fields after zoom (both coordinate systems)
            self.update_coordinate_display(xmin, ymin, xmax, ymax)
            # Button state will be updated by update_coordinate_display (which calls check_and_update_download_button)
            
    def zoom_to_selection(self, xmin, ymin, xmax, ymax):
        """Zoom map to the selected area."""
        if self.map_widget:
            # Get widget aspect ratio - ensure widget is properly sized
            widget_width = self.map_widget.width()
            widget_height = self.map_widget.height()
            
            # If widget isn't sized yet, wait a bit and try again
            if widget_width <= 0 or widget_height <= 0:
                self.log_message(f"Widget not sized yet ({widget_width}x{widget_height}), retrying zoom_to_selection in 200ms...")
                QTimer.singleShot(200, lambda: self.zoom_to_selection(xmin, ymin, xmax, ymax))
                return
            
            # Calculate the selected area dimensions
            selection_width = xmax - xmin
            selection_height = ymax - ymin
            
            # Add 5% padding around the selection
            padding_x = selection_width * 0.05
            padding_y = selection_height * 0.05
            
            # Start with padded extent
            padded_xmin = xmin - padding_x
            padded_ymin = ymin - padding_y
            padded_xmax = xmax + padding_x
            padded_ymax = ymax + padding_y
            
            padded_width = padded_xmax - padded_xmin
            padded_height = padded_ymax - padded_ymin
            
            if widget_width > 0 and widget_height > 0:
                widget_aspect = widget_width / widget_height
                padded_aspect = padded_width / padded_height
                
                # Calculate center of padded area
                center_x = (padded_xmin + padded_xmax) / 2
                center_y = (padded_ymin + padded_ymax) / 2
                
                # Adjust extent to match widget aspect ratio while containing the padded selection
                if padded_aspect > widget_aspect:
                    # Padded area is wider than widget - use padded width, adjust height
                    new_width = padded_width
                    new_height = new_width / widget_aspect
                else:
                    # Padded area is taller than widget - use padded height, adjust width
                    new_height = padded_height
                    new_width = new_height * widget_aspect
                
                # Create new extent centered on the padded selection
                new_extent = (
                    center_x - new_width / 2,
                    center_y - new_height / 2,
                    center_x + new_width / 2,
                    center_y + new_height / 2
                )
            else:
                # Fallback to padded extent if widget size not available
                new_extent = (padded_xmin, padded_ymin, padded_xmax, padded_ymax)
            
            # Set the extent FIRST, then store the selection bbox
            # This ensures the selection bbox is stored with the correct extent context
            self.map_widget.extent = new_extent
            self.map_widget._requested_extent = new_extent  # Also update _requested_extent for accurate coordinate conversion
            # Store the selected bbox in world coordinates for drawing (original selection, no modifications)
            # This is what will be shown in the yellow/green box and used for download
            self.map_widget.selected_bbox_world = (xmin, ymin, xmax, ymax)
            # Ensure service_extent is preserved for color distinction (yellow for dataset bounds, green for user selection)
            if not hasattr(self.map_widget, 'service_extent') or self.map_widget.service_extent is None:
                self.map_widget.service_extent = self.service_extent
            # Don't clear selection - keep it visible
            self.map_widget.load_map()
            
    def start_download(self):
        """Start downloading the selected area."""
        # Get bbox from stored selection or manual entry
        bbox = None
        
        # First try to use stored selected bbox
        if hasattr(self, 'selected_bbox') and self.selected_bbox:
            bbox = self.selected_bbox
        # Then try to get from map widget
        elif self.map_widget:
            bbox = self.map_widget.get_selection_bbox()
        # Finally try manual entry
        else:
            try:
                xmin_text = self.xmin_edit.text()
                ymin_text = self.ymin_edit.text()
                xmax_text = self.xmax_edit.text()
                ymax_text = self.ymax_edit.text()
                
                # Check if fields have actual values (not just placeholders)
                if xmin_text and ymin_text and xmax_text and ymax_text:
                    bbox = (
                        float(xmin_text),
                        float(ymin_text),
                        float(xmax_text),
                        float(ymax_text)
                    )
            except ValueError:
                QMessageBox.warning(self, "Invalid Input", "Please enter valid coordinates.")
                return
                
        if not bbox:
            QMessageBox.warning(self, "No Selection", "Please select an area on the map.")
            return
            
        output_crs = self.crs_combo.currentText()
        cell_size = float(self.cell_size_combo.currentText())  # Get cell size in meters
        
        # Calculate pixel dimensions
        xmin, ymin, xmax, ymax = bbox
        width_meters = xmax - xmin
        height_meters = ymax - ymin
        pixels_width = int(width_meters / cell_size)
        pixels_height = int(height_meters / cell_size)
        
        # Warn user if downloading a very large dataset (> 10,000 x 10,000 pixels)
        large_size_threshold = 10000
        if pixels_width > large_size_threshold or pixels_height > large_size_threshold:
            total_pixels = pixels_width * pixels_height
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Large Dataset Warning")
            msg.setText(
                f"You are about to download a very large dataset.\n\n"
                f"Requested size: {pixels_width:,} × {pixels_height:,} pixels\n"
                f"Total pixels: {total_pixels:,}\n\n"
                f"This download may take a significant amount of time and disk space.\n"
                f"{'Tiled download is enabled and will break this into multiple requests.' if self.tile_download_checkbox.isChecked() else 'Consider enabling Tile Download for better reliability.'}\n\n"
                f"Do you want to continue?"
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
            result = msg.exec()
            
            if result == QMessageBox.StandardButton.Cancel:
                return  # User cancelled
        
        # Generate default filename: "GEBCO_Bathy_" + cell_size + "_" + date_time + ".tif"
        current_time = datetime.now()
        date_time_str = current_time.strftime("%Y-%m-%d_%H-%M-%S")
        default_filename = f"GEBCO_Bathy_{int(cell_size)}m_{date_time_str}.tif"
        
        # Check if output directory has been selected
        if self.output_directory and os.path.isdir(self.output_directory):
            # Use the selected output directory without prompting
            output_path = os.path.join(self.output_directory, default_filename)
        else:
            # No output directory selected - prompt for save location
            default_path = default_filename
            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save GeoTIFF",
                default_path,
                "GeoTIFF Files (*.tif *.tiff);;All Files (*)"
            )
            
            # If user cancelled the dialog, abort download
            if not output_path:
                return
        
        # Disable download button
        self.download_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting download...")
        
        # Get tile download setting
        use_tile_download = self.tile_download_checkbox.isChecked()
        
        # Create downloader thread
        # max_size is still used when tiling is disabled
        max_size = 14000  # Maximum size for non-tiled downloads
        self.downloader = BathymetryDownloader(
            self.base_url,
            bbox,
            output_path,
            output_crs,
            pixel_size=cell_size,
            max_size=max_size,
            use_tile_download=use_tile_download
        )
        self.downloader.progress.connect(self.progress_bar.setValue)
        self.downloader.status.connect(self.on_status_update)
        self.downloader.finished.connect(self.on_download_finished)
        self.downloader.error.connect(self.on_download_error)
        self.downloader.start()
        
    def on_status_update(self, message):
        """Handle status update from downloader."""
        self.status_label.setText(message)
        self.log_message(message)
        
    def on_download_finished(self, file_path):
        """Handle download completion."""
        self.status_label.setText(f"Download complete: {file_path}")
        self.log_message(f"✓ Download complete: {file_path}")
        self.download_btn.setEnabled(True)
        # Remove bold formatting after download completes
        font = self.download_btn.font()
        font.setBold(False)
        self.download_btn.setFont(font)
        QMessageBox.information(self, "Success", f"GeoTIFF saved to:\n{file_path}")
        
    def on_download_error(self, error_message):
        """Handle download error."""
        self.status_label.setText(f"Error: {error_message}")
        self.log_message(f"✗ Error: {error_message}")
        self.download_btn.setEnabled(True)
        # Remove bold formatting after download error
        font = self.download_btn.font()
        font.setBold(False)
        self.download_btn.setFont(font)
        
        # Check if it's a connection error and show helpful message
        if "connection" in error_message.lower() or "timeout" in error_message.lower() or "network" in error_message.lower() or "rest endpoint" in error_message.lower():
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Connection Error")
            msg.setText(
                f"Unable to connect to the REST endpoint.\n\n"
                f"{error_message}\n\n"
                f"If this problem persists, please:\n"
                f"1. Check for a new version at: https://github.com/seamapper/GEBCO_Downloader\n"
                f"2. Contact: pjohnson@ccom.unh.edu"
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
        QMessageBox.critical(self, "Download Error", error_message)
        
    def log_message(self, message):
        """Add message to log."""
        # QTextEdit automatically handles both plain text and HTML
        self.log_text.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def resizeEvent(self, event):
        """Handle window resize event - refresh map display."""
        super().resizeEvent(event)
        # Refresh map when window is resized (with a small delay to avoid multiple refreshes)
        if self.map_widget and self.map_widget.map_loaded:
            # Use a timer to debounce rapid resize events
            if not hasattr(self, '_resize_timer'):
                self._resize_timer = QTimer()
                self._resize_timer.setSingleShot(True)
                self._resize_timer.timeout.connect(self._refresh_map_on_resize)
            
            # Restart timer - will trigger refresh 300ms after resize stops
            self._resize_timer.stop()
            self._resize_timer.start(300)
    
    def _refresh_map_on_resize(self):
        """Refresh map display after window resize."""
        if self.map_widget and self.map_widget.map_loaded:
            # Ensure widget size is updated before calculating new extent
            # Process events to ensure Qt has updated the widget size
            QApplication.processEvents()
            
            # Verify widget size is valid before proceeding
            widget_width = self.map_widget.width()
            widget_height = self.map_widget.height()
            
            if widget_width <= 0 or widget_height <= 0:
                # Widget not sized yet, skip this resize
                return
            
            # If there's a selected area, zoom to it to maintain constant visual size
            # This treats the resize as if the user made a new selection with the same bounds
            # The zoom_to_selection function will recalculate the extent based on the new widget size
            # making the selection box appear the same visual size
            if self.map_widget.selected_bbox_world:
                xmin, ymin, xmax, ymax = self.map_widget.selected_bbox_world
                # Zoom to the selection - this will recalculate the extent based on new widget size
                # making the selection box appear the same visual size
                self.zoom_to_selection(xmin, ymin, xmax, ymax)
            else:
                # No selection - just reload the map with current extent
                self.map_widget.load_map()
    
    def closeEvent(self, event):
        """Handle window close event."""
        if self.downloader and self.downloader.isRunning():
            reply = QMessageBox.question(
                self,
                "Download in Progress",
                "A download is in progress. Do you want to cancel it and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.downloader.cancel()
                self.downloader.wait(3000)  # Wait up to 3 seconds
            else:
                event.ignore()
                return
        event.accept()
    
    def load_config(self):
        """Load configuration from JSON file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.output_directory = config.get('output_directory')
                    # Update edit field if it exists (it should after init_ui)
                    if hasattr(self, 'output_dir_edit'):
                        if self.output_directory and os.path.isdir(self.output_directory):
                            self.output_dir_edit.setText(self.output_directory)
                        else:
                            self.output_directory = None
                            self.output_dir_edit.clear()
                    elif not (self.output_directory and os.path.isdir(self.output_directory)):
                        self.output_directory = None
        except Exception as e:
            # If config file is corrupted or can't be read, just use defaults
            self.output_directory = None
            if hasattr(self, 'output_dir_edit'):
                self.output_dir_edit.clear()
    
    def save_config(self):
        """Save configuration to JSON file."""
        try:
            config = {
                'output_directory': self.output_directory
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            # If we can't save config, just continue - it's not critical
            pass
    
    def select_output_directory(self):
        """Open dialog to select output directory."""
        # Start with current directory or saved directory
        start_dir = self.output_directory if self.output_directory and os.path.isdir(self.output_directory) else os.getcwd()
        
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            start_dir,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )
        
        if directory:
            self.output_directory = directory
            self.output_dir_edit.setText(directory)
            self.save_config()  # Save to config file
    
    def on_map_first_loaded(self):
        """Handle first successful map load - show instructions and set default bounds."""
        # If no selection exists yet, set default to REST endpoint service extent bounds
        # CRITICAL: Use the REST endpoint extent (service_extent) for the box, NOT the map's displayed extent
        # The map might show a slightly different area due to rounding or basemap coverage,
        # but the box should show the exact bathymetry data bounds from the REST endpoint
        if self.map_widget and self.map_widget.selected_bbox_world is None:
            if self.service_extent:
                # Set default selection to REST endpoint service extent bounds (exact bathymetry data bounds)
                # This is the correct extent from the REST endpoint, not the map's displayed extent
                self.map_widget.selected_bbox_world = self.service_extent
                self.map_widget.set_selection_validity(True)
                self.selected_bbox = self.service_extent
                # Ensure service_extent is stored in map widget (this is the REST endpoint extent)
                self.map_widget.service_extent = self.service_extent
                
                # CRITICAL: Zoom to the REST endpoint bounds using zoom_to_selection
                # This ensures the map extent is recalculated with padding and the box is positioned correctly
                # This mimics what happens when the user hits return in a coordinate field
                QTimer.singleShot(300, lambda: self.zoom_to_selection(*self.service_extent))
                self.log_message("Default selection set to service extent bounds, will zoom to dataset bounds")
    
    def _zoom_to_service_extent(self):
        """Zoom to service extent bounds - helper method for delayed zoom."""
        if self.map_widget and self.service_extent:
            # Ensure the selected bbox is set to service extent (this is the dataset bounds)
            self.map_widget.selected_bbox_world = self.service_extent
            self.map_widget.set_selection_validity(True)
            self.selected_bbox = self.service_extent
            # Ensure service extent is stored in map widget for color distinction
            self.map_widget.service_extent = self.service_extent
            
            # Zoom to the service extent - this will reload the map with the correct extent
            self.zoom_to_selection(*self.service_extent)
            # After zoom completes, the map will reload and the box should be visible
            # The box will be repainted in paintEvent when the new map loads
        
        instructions = [
            "",
            "=" * 60,
            "Map loaded successfully!",
            "=" * 60,
            "",
            "To select an area:",
            "  1. Click and drag with the left mouse button on the map",
            "  2. The selected area will be shown with a purple dashed box",
            "  3. You can also manually enter coordinates in the WebMercator or Geographic fields",
            "",
            "To download the selected area:",
            "  1. Select an area on the map (or enter coordinates)",
            "  2. Choose your output options (Cell Size, CRS)",
            "  3. Click 'Download Selected Area' button",
            "  4. Choose a filename and location (defaults to selected directory)",
            "",
            "Map controls:",
            "  - Mouse wheel: Zoom in/out (centered on window)",
            "  - Middle mouse button + drag: Pan the map",
            "  - Left mouse button + drag: Select area",
            "",
            "=" * 60
        ]
        
        for line in instructions:
            self.log_message(line)
    
    def _bboxes_overlap(self, bbox1, bbox2):
        """Check if two bounding boxes overlap.
        
        Args:
            bbox1: (xmin, ymin, xmax, ymax) tuple
            bbox2: (xmin, ymin, xmax, ymax) tuple
            
        Returns:
            True if boxes overlap, False otherwise
        """
        xmin1, ymin1, xmax1, ymax1 = bbox1
        xmin2, ymin2, xmax2, ymax2 = bbox2
        
        # Check if boxes overlap (not disjoint)
        return not (xmax1 < xmin2 or xmin1 > xmax2 or ymax1 < ymin2 or ymin1 > ymax2)
    
    def on_data_source_changed(self, data_source_name):
        """Handle data source selection change."""
        if data_source_name not in self.data_sources:
            return
        
        # Get new data source extent
        new_service_extent = self.data_sources[data_source_name]["default_extent"]
        
        # Check if current selection overlaps with new data source extent
        saved_selection = None
        if hasattr(self, 'selected_bbox') and self.selected_bbox:
            if self._bboxes_overlap(self.selected_bbox, new_service_extent):
                # Selection overlaps with new data source - keep it
                saved_selection = self.selected_bbox
            else:
                # Selection doesn't overlap - clear it
                self.selected_bbox = None
                if self.map_widget:
                    self.map_widget.selected_bbox_world = None
                    self.map_widget.clear_selection()
        
        # Update current data source
        self.current_data_source = data_source_name
        self.base_url = self.data_sources[data_source_name]["url"]
        self.service_extent = new_service_extent
        
        # Set flag to force highest resolution when cell size options are updated
        self._data_source_changing = True
        
        # Update map widget settings if it exists
        if self.map_widget:
            # Update raster functions
            new_raster_function = self.data_sources[data_source_name]["bathymetry_raster_function"]
            new_hillshade_raster_function = self.data_sources[data_source_name]["hillshade_raster_function"]
            self.map_widget.raster_function = new_raster_function
            self.map_widget.hillshade_raster_function = new_hillshade_raster_function
            self.map_widget.base_url = self.base_url
            # Update service extent in map widget so it can distinguish dataset bounds from user selection
            self.map_widget.service_extent = self.service_extent
            # Don't update pixel sizes here - they will be updated in on_service_info_loaded after the new service loads
            # This ensures we get the correct pixel sizes for the new data source
        
        # Reload service info (this will update extent and reload map)
        self.load_service_info()
        
        # Store selection to restore after map loads (will zoom to it if it overlaps)
        self._pending_selection = saved_selection
    
    def _reload_map_with_selection(self):
        """Reload map and restore selection if it exists."""
        # If there's a pending selection, let zoom_to_selection handle loading the map
        # Otherwise, load the map with current extent
        if self.map_widget:
            if hasattr(self, '_pending_selection') and self._pending_selection:
                # Wait a moment for map widget to be ready, then restore selection
                # zoom_to_selection will load the map with the correct extent
                QTimer.singleShot(100, lambda: self._restore_selection())
            else:
                # No selection - just reload the map with current extent
                self.map_widget.load_map()
    
    def _restore_selection(self):
        """Restore a previously saved selection and zoom to it."""
        if hasattr(self, '_pending_selection') and self._pending_selection:
            bbox = self._pending_selection
            self.selected_bbox = bbox
            
            # Zoom to the selection to maintain visual size
            self.zoom_to_selection(bbox[0], bbox[1], bbox[2], bbox[3])
            
            # Update coordinate displays (without updating map since zoom_to_selection already does)
            self.update_coordinate_display(bbox[0], bbox[1], bbox[2], bbox[3], update_map=False)
            
            # Clear pending selection
            self._pending_selection = None


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

