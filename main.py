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
                             QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, 
                             QFileDialog, QComboBox, QProgressBar, QTextEdit,
                             QGroupBox, QMessageBox, QCheckBox, QSizePolicy)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QMouseEvent
from map_widget import MapWidget
from download_module import BathymetryDownloader
import requests
import json
from datetime import datetime


class ClickableLabel(QLabel):
    """A QLabel that emits a clicked signal when clicked."""
    clicked = pyqtSignal()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


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
        # GEBCO 2025: everything in GCS (EPSG:4326), full extent to poles
        _world_4326 = (-180.0, -90.0, 180.0, 90.0)
        self.data_sources = {
            "GEBCO 2025": {
                "url": "https://gis.ccom.unh.edu/server/rest/services/GEBCO2025/GEBCO_2025_IS/ImageServer",
                "display_url": "https://gis.ccom.unh.edu/server/rest/services/GEBCO/GEBCO_2025_Depths_Haxby_GCS/MapServer",
                "land_display_url": "https://gis.ccom.unh.edu/server/rest/services/GEBCO/GEBCO_2025_Land_Grey_GCS/MapServer",
                "bathymetry_raster_function": "None",
                "hillshade_raster_function": "None",
                "default_extent": _world_4326,
                "service_crs": "EPSG:4326",
                "native_resolution_only": True,
                "native_pixel_size_degrees": 0.004166666666666667,
                "attribution": "GEBCO Compilation Group (2025) GEBCO 2025 Grid (doi:10.5285/37c52e96-24ea-67ce-e063-7086abc05f29)",
                "attribution_url": "https://www.bodc.ac.uk/data/published_data_library/catalogue/10.5285/37c52e96-24ea-67ce-e063-7086abc05f29",
            },
            "GEBCO 2025 TID": {
                "url": "https://gis.ccom.unh.edu/server/rest/services/GEBCO2025/GEBCO_2025_TID_IS/ImageServer",
                "display_url": "https://gis.ccom.unh.edu/server/rest/services/GEBCO/GEBCO_2025_TID_GCS/MapServer",
                "land_display_url": "https://gis.ccom.unh.edu/server/rest/services/GEBCO/GEBCO_2025_Land_Grey_GCS/MapServer",
                "bathymetry_raster_function": "None",
                "hillshade_raster_function": "None",
                "default_extent": _world_4326,
                "service_crs": "EPSG:4326",
                "native_resolution_only": True,
                "native_pixel_size_degrees": 0.004166666666666667,
                "attribution": "GEBCO Compilation Group (2025) GEBCO 2025 Grid (doi:10.5285/37c52e96-24ea-67ce-e063-7086abc05f29)",
                "attribution_url": "https://www.bodc.ac.uk/data/published_data_library/catalogue/10.5285/37c52e96-24ea-67ce-e063-7086abc05f29",
            }
        }
        self.current_data_source = "GEBCO 2025"
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
        
        # Legend checkbox (on the left)
        self.legend_checkbox = QCheckBox("Legend")
        self.legend_checkbox.setChecked(True)  # On by default
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
        
        # Left side container (Map + Attribution)
        left_container = QWidget()
        left_container_layout = QVBoxLayout(left_container)
        left_container_layout.setContentsMargins(0, 0, 0, 0)  # No margins
        left_container_layout.addWidget(self.map_group)
        
        # Data Set Attribution (below Map groupbox)
        attribution_group = QGroupBox("Data Set Attribution")
        attribution_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)  # Fixed height, don't expand
        attribution_group.setMaximumHeight(40)  # Constrain maximum height
        attribution_layout = QVBoxLayout()
        attribution_layout.setContentsMargins(2, 1, 2, 1)  # Very minimal margins (top/bottom: 1px)
        attribution_layout.setSpacing(0)  # No spacing between items
        self.attribution_label = ClickableLabel()
        self.attribution_label.setWordWrap(True)
        self.attribution_label.setStyleSheet("color: green; text-decoration: underline; cursor: pointer; padding: 0px; margin: 0px; border: none;")
        self.attribution_label.setContentsMargins(0, 0, 0, 0)  # Remove any label margins
        self.attribution_label.clicked.connect(self._open_attribution_url)
        self._current_attribution_url = None  # Store current attribution URL
        attribution_layout.addWidget(self.attribution_label)
        attribution_group.setLayout(attribution_layout)
        left_container_layout.addWidget(attribution_group)
        
        main_layout.addWidget(left_container)
        
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
        selection_main_layout = QGridLayout()
        
        # Selection coordinates in GCS (EPSG:4326) only
        self.west_edit = QLineEdit()
        self.west_edit.setPlaceholderText("West")
        self.south_edit = QLineEdit()
        self.south_edit.setPlaceholderText("South")
        self.east_edit = QLineEdit()
        self.east_edit.setPlaceholderText("East")
        self.north_edit = QLineEdit()
        self.north_edit.setPlaceholderText("North")
        
        # Connect GCS field changes to update map
        self.west_edit.editingFinished.connect(self.on_geographic_changed)
        self.south_edit.editingFinished.connect(self.on_geographic_changed)
        self.east_edit.editingFinished.connect(self.on_geographic_changed)
        self.north_edit.editingFinished.connect(self.on_geographic_changed)
        
        # Layout in "+" shape (3x3 grid):
        # Row 0, Col 1: North (top center)
        north_layout = QHBoxLayout()
        north_layout.addWidget(QLabel("North:"))
        north_layout.addWidget(self.north_edit)
        selection_main_layout.addLayout(north_layout, 0, 1)
        
        # Row 1, Col 0: West (middle left)
        west_layout = QHBoxLayout()
        west_layout.addWidget(QLabel("West:"))
        west_layout.addWidget(self.west_edit)
        selection_main_layout.addLayout(west_layout, 1, 0)
        
        # Row 1, Col 2: East (middle right)
        east_layout = QHBoxLayout()
        east_layout.addWidget(QLabel("East:"))
        east_layout.addWidget(self.east_edit)
        selection_main_layout.addLayout(east_layout, 1, 2)
        
        # Row 2, Col 1: South (bottom center)
        south_layout = QHBoxLayout()
        south_layout.addWidget(QLabel("South:"))
        south_layout.addWidget(self.south_edit)
        selection_main_layout.addLayout(south_layout, 2, 1)
        
        selection_group.setLayout(selection_main_layout)
        right_layout.addWidget(selection_group)
        
        # Output options
        output_group = QGroupBox("Output Options")
        output_layout = QVBoxLayout()
        
        # Output Data Types groupbox (GEBCO 2025 only): any combination of Combined, Bathymetry Only, Land Only, Direct Measurements Only
        self.output_data_types_group = QGroupBox("Output Grid Data Types")
        output_data_types_layout = QVBoxLayout()
        self.download_mode_container = QWidget()
        download_mode_layout = QGridLayout(self.download_mode_container)
        self.check_combined = QCheckBox("Combined Bathymetry && Land")
        self.check_combined.setChecked(True)
        self.check_combined.setToolTip("Native grid with bathymetry and elevation")
        download_mode_layout.addWidget(self.check_combined, 0, 0)
        self.check_direct_measurements_only = QCheckBox("Direct Measurements")
        self.check_direct_measurements_only.setToolTip("Only cells where TID is 10–20 (direct measurements)")
        download_mode_layout.addWidget(self.check_direct_measurements_only, 0, 1)
        self.check_direct_unknown_measurements_only = QCheckBox("Direct && Unknown Measurement")
        self.check_direct_unknown_measurements_only.setToolTip("Only cells where TID is 10–20, 44, or 70 (direct and unknown measurements)")
        download_mode_layout.addWidget(self.check_direct_unknown_measurements_only, 1, 1)
        self.check_bathymetry_only = QCheckBox("Bathymetry")
        self.check_bathymetry_only.setToolTip("Only cells where TID is not 0 (water)")
        download_mode_layout.addWidget(self.check_bathymetry_only, 1, 0)
        self.check_land_only = QCheckBox("Land")
        self.check_land_only.setToolTip("Only cells where TID is 0 (land)")
        download_mode_layout.addWidget(self.check_land_only, 2, 0)
        for cb in (self.check_combined, self.check_bathymetry_only, self.check_land_only, self.check_direct_measurements_only, self.check_direct_unknown_measurements_only):
            cb.toggled.connect(self.check_and_update_download_button)
        self.check_direct_measurements_only.toggled.connect(
            lambda checked: self.log_message("Only extracting bathymetry values with associated TID values from 10 to 17", bold=True) if checked else None
        )
        self.check_direct_unknown_measurements_only.toggled.connect(
            lambda checked: self.log_message("Only extracting bathymetry values with TID 10 to 17, 44 and 70", bold=True) if checked else None
        )
        output_data_types_layout.addWidget(self.download_mode_container)
        self.output_data_types_group.setLayout(output_data_types_layout)
        output_layout.addWidget(self.output_data_types_group)
        
        # Pixel count display at the bottom
        self.pixel_count_label = QLabel("Pixels: --")
        self.pixel_count_label.setStyleSheet("font-weight: bold; padding: 5px;")
        output_layout.addWidget(self.pixel_count_label)
        
        output_group.setLayout(output_layout)
        right_layout.addWidget(output_group)
        
        # Show download mode options only for GEBCO 2025 (not TID)
        self._update_download_mode_visibility()
        
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
        
        # Update attribution text based on current data source
        self._update_attribution()
        
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
        ds = self.data_sources.get(self.current_data_source, {})
        if ds.get("service_crs") == "EPSG:4326":
            # Keep extent in GCS (4326), full range to poles
            self.service_extent = (
                extent_dict["xmin"],
                extent_dict["ymin"],
                extent_dict["xmax"],
                extent_dict["ymax"]
            )
        else:
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
        self.pixel_size_x = pixel_size_x
        self.pixel_size_y = pixel_size_y
        if ds.get("native_resolution_only"):
            self._set_native_cell_size_only()
        elif pixel_size_x is not None and pixel_size_y is not None:
            base_cell_size = max(abs(pixel_size_x), abs(pixel_size_y))
            self.update_cell_size_options(base_cell_size, force_highest_resolution=self._data_source_changing)
        else:
            self.log_message("Warning: Pixel size not available from service, using default cell sizes")
            self.update_cell_size_options(4.0, force_highest_resolution=self._data_source_changing)
        
        self._data_source_changing = False
        
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
            
            # Update raster functions and display URL from current data source
            new_raster_function = self.data_sources[self.current_data_source]["bathymetry_raster_function"]
            new_hillshade_raster_function = self.data_sources[self.current_data_source]["hillshade_raster_function"]
            self.map_widget.raster_function = new_raster_function
            self.map_widget.hillshade_raster_function = new_hillshade_raster_function
            self.map_widget.display_url = self.data_sources[self.current_data_source].get("display_url")
            self.map_widget.land_display_url = self.data_sources[self.current_data_source].get("land_display_url")
            
            # Check if there's a pending selection to preserve
            if hasattr(self, '_pending_selection') and self._pending_selection:
                # Use the pending selection extent instead of full service extent
                selection_extent = self._pending_selection
                self.log_message(f"Preserving selection, will zoom to it: {selection_extent}")
                self.map_widget.extent = selection_extent
                self.map_widget._requested_extent = selection_extent
            else:
                # Always set extent to REST endpoint service extent as a baseline
                # This ensures the map shows exactly the bathymetry data bounds from the REST endpoint
                self.log_message(f"Updating map extent to REST endpoint extent: {self.service_extent}")
                self.map_widget.extent = self.service_extent
                # Also update _requested_extent to ensure coordinate conversion is correct
                # This ensures the map displays exactly the REST endpoint bounds, not a rounded or adjusted version
                self.map_widget._requested_extent = self.service_extent
            
            # Update service extent in map widget
            self.map_widget.service_extent = self.service_extent
            
            # CRITICAL: Always update selected_bbox_world to REST endpoint extent if it matches default extent
            # This ensures the box shows the exact REST endpoint bounds, not the default extent
            # Check if selected_bbox_world is None OR if it matches the default extent (needs update)
            default_extent = self.data_sources[self.current_data_source]["default_extent"]
            needs_update = (
                self.map_widget.selected_bbox_world is None or
                self.map_widget.selected_bbox_world == default_extent
            )
            if needs_update and not (hasattr(self, '_pending_selection') and self._pending_selection):
                self.log_message(f"Updating selected_bbox_world from {self.map_widget.selected_bbox_world} to REST endpoint extent {self.service_extent}")
                self.map_widget.selected_bbox_world = self.service_extent
                self.map_widget.set_selection_validity(True)
                self.selected_bbox = self.service_extent
                # Update coordinate display to show REST endpoint bounds
                self.update_coordinate_display(*self.service_extent, update_map=False)
            
            # CRITICAL: Always reload map with REST endpoint extent to ensure it shows exact bathymetry data bounds
            # Check if the map was loaded with a different extent (e.g., default extent)
            current_extent = self.map_widget.extent
            default_extent = self.data_sources[self.current_data_source]["default_extent"]
            
            # Check if map was loaded with default extent (tolerance in degrees for GCS)
            _tol = 1e-5
            extent_matches_default = (
                abs(current_extent[0] - default_extent[0]) < _tol and
                abs(current_extent[1] - default_extent[1]) < _tol and
                abs(current_extent[2] - default_extent[2]) < _tol and
                abs(current_extent[3] - default_extent[3]) < _tol
            )
            
            # Ensure default bounds are set
            if self.map_widget.selected_bbox_world is None:
                self.map_widget.selected_bbox_world = self.service_extent
                self.map_widget.set_selection_validity(True)
                self.selected_bbox = self.service_extent
                self.map_widget.service_extent = self.service_extent
                self.log_message(f"Set default bounds to REST endpoint extent: {self.service_extent}")
            
            # Check if there's a pending selection to restore
            if hasattr(self, '_pending_selection') and self._pending_selection:
                # Restore the selection - this will zoom to it and reload the map
                self.log_message(f"Restoring pending selection: {self._pending_selection}")
                QTimer.singleShot(300, lambda: self._restore_selection())
            # Force reload if URL changed (data source switch) or if extent differs
            elif url_changed or current_extent != self.service_extent or extent_matches_default:
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
                show_basemap = False
                show_hillshade = False
                use_blend = False
                self.log_message(f"Creating MapWidget with extent: {self.service_extent}, raster function: {raster_function}")
                display_url = self.data_sources[self.current_data_source].get("display_url")
                land_display_url = self.data_sources[self.current_data_source].get("land_display_url")
                self.map_widget = MapWidget(self.base_url, self.service_extent, raster_function=raster_function, show_basemap=show_basemap, show_hillshade=show_hillshade, use_blend=use_blend, hillshade_raster_function=hillshade_raster_function, display_url=display_url, land_display_url=land_display_url)
                self.map_widget.bathymetry_opacity = 1.0  # Full opacity
                # Sync legend visibility with checkbox state
                if hasattr(self, 'legend_checkbox'):
                    self.map_widget.show_legend = self.legend_checkbox.isChecked()
                # Store service extent in map widget
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
        
        # Check if selection exceeds maximum size (bbox is in GCS: west, south, east, north)
        try:
            west, south, east, north = bbox
            ds = self.data_sources.get(self.current_data_source, {})
            if ds.get("native_resolution_only"):
                deg_per_pixel = ds.get("native_pixel_size_degrees", 0.004166666666666667)
                pixels_width = int((east - west) / deg_per_pixel)
                pixels_height = int((north - south) / abs(deg_per_pixel))
            else:
                ct = self.cell_size_combo.currentText() if hasattr(self, 'cell_size_combo') else ""
                try:
                    cell_size = float(ct) if ct else 4.0
                except ValueError:
                    cell_size = 4.0
                width_m = (east - west) * 111320 * 0.5
                height_m = (north - south) * 110540
                pixels_width = int(width_m / cell_size)
                pixels_height = int(height_m / cell_size)
            
            # No size limit - always enable download button
            # Warning dialog will be shown when downloading large datasets
            is_valid = True
            
            # Update map widget selection color (always valid now)
            if self.map_widget:
                self.map_widget.set_selection_validity(is_valid)
            
            # Enable download button unless GEBCO 2025 with no output option selected
            self.download_btn.setEnabled(True)
            if (self.current_data_source == "GEBCO 2025" and hasattr(self, 'check_combined') and
                not (self.check_combined.isChecked() or self.check_bathymetry_only.isChecked() or self.check_land_only.isChecked() or self.check_direct_measurements_only.isChecked() or self.check_direct_unknown_measurements_only.isChecked())):
                self.download_btn.setEnabled(False)
            # Make text bold only if this is a user manual selection (not initial dataset bounds)
            is_initial_bounds = False
            if hasattr(self, 'service_extent') and self.service_extent:
                se = self.service_extent
                tol = 1e-5  # degrees
                if (abs(se[0] - west) < tol and abs(se[1] - south) < tol and
                    abs(se[2] - east) < tol and abs(se[3] - north) < tol):
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
    
    def _set_native_cell_size_only(self):
        """Set cell size dropdown to single 'Native' option (for sources with native_resolution_only)."""
        if not hasattr(self, 'cell_size_combo'):
            return
        if hasattr(self, 'cell_size_label'):
            self.cell_size_label.setText("Resolution:")
        self.cell_size_combo.clear()
        self.cell_size_combo.addItems(["Native"])
        if hasattr(self, 'selected_bbox') and self.selected_bbox:
            xmin, ymin, xmax, ymax = self.selected_bbox
            self.update_coordinate_display(xmin, ymin, xmax, ymax, update_map=False)
    
    def update_cell_size_options(self, base_cell_size, force_highest_resolution=False):
        """Update cell size dropdown options based on base cell size from service.
        
        Args:
            base_cell_size: The base cell size (max of pixelSizeX and pixelSizeY)
            force_highest_resolution: If True, always select the highest resolution (smallest cell size)
        """
        if not hasattr(self, 'cell_size_combo'):
            return
        if hasattr(self, 'cell_size_label'):
            self.cell_size_label.setText("Cell Size (m):")
        
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
        if not hasattr(self, 'cell_size_combo'):
            return
        # Update pixel count display if there's a current selection
        if hasattr(self, 'selected_bbox') and self.selected_bbox:
            xmin, ymin, xmax, ymax = self.selected_bbox
            self.update_coordinate_display(xmin, ymin, xmax, ymax, update_map=False)
        # Update download button state
        self.check_and_update_download_button()
            
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
            
            # Snap bounds to cell size grid
            snapped_west, snapped_south, snapped_east, snapped_north, was_adjusted = self._snap_bounds_to_cell_size(west, south, east, north)
            
            if was_adjusted:
                self.log_message(
                    f"Selection bounds adjusted to align with cell size grid: "
                    f"({west:.6f}, {south:.6f}, {east:.6f}, {north:.6f}) → "
                    f"({snapped_west:.6f}, {snapped_south:.6f}, {snapped_east:.6f}, {snapped_north:.6f})"
                )
            
            self.update_coordinate_display(snapped_west, snapped_south, snapped_east, snapped_north, update_map=True)
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric coordinates.")
            self.check_and_update_download_button()  # Disable button on invalid input
            
    def update_coordinate_display(self, west, south, east, north, update_map=True):
        """Update GCS (West, South, East, North) display. All coordinates in 4326."""
        if self._updating_coordinates:
            return
        self._updating_coordinates = True
        try:
            self.west_edit.setText(f"{west:.6f}")
            self.south_edit.setText(f"{south:.6f}")
            self.east_edit.setText(f"{east:.6f}")
            self.north_edit.setText(f"{north:.6f}")
            if update_map:
                self.selected_bbox = (west, south, east, north)
                if self.map_widget:
                    self.zoom_to_selection(west, south, east, north)
        finally:
            self._updating_coordinates = False
        
        # Update download button state
        self.check_and_update_download_button()
        
        # Calculate expected number of pixels (bbox is in GCS: west, south, east, north)
        try:
            ds = self.data_sources.get(self.current_data_source, {})
            if ds.get("native_resolution_only"):
                deg_per_pixel = ds.get("native_pixel_size_degrees", 0.004166666666666667)
                pixels_width = int((east - west) / deg_per_pixel)
                pixels_height = int((north - south) / abs(deg_per_pixel))
                cell_size_label = "native"
            else:
                width_meters = (east - west) * 111320 * 0.5  # approx at mid-lat
                height_meters = (north - south) * 110540
                ct = self.cell_size_combo.currentText() if hasattr(self, 'cell_size_combo') else ""
                try:
                    cell_size = float(ct) if ct else 4.0
                except ValueError:
                    cell_size = 4.0
                pixels_width = int(width_meters / cell_size)
                pixels_height = int(height_meters / cell_size)
                cell_size_label = f"{cell_size}m"
            
            total_pixels = pixels_width * pixels_height
            pixels_width_str = f"{pixels_width:,}"
            pixels_height_str = f"{pixels_height:,}"
            total_pixels_str = f"{total_pixels:,}"
            large_size_threshold = 10000
            is_large = pixels_width > large_size_threshold or pixels_height > large_size_threshold
            
            if is_large:
                self.pixel_count_label.setText(
                    f"⚠️ Output Grid Pixels : {pixels_width_str} × {pixels_height_str} = {total_pixels_str} "
                    f"(LARGE DATASET!)"
                )
                self.pixel_count_label.setStyleSheet("font-weight: bold; padding: 5px; color: orange;")
            else:
                self.pixel_count_label.setText(
                    f"Output Grid Pixels : {pixels_width_str} × {pixels_height_str} = {total_pixels_str}"
                )
                self.pixel_count_label.setStyleSheet("font-weight: bold; padding: 5px;")
        except Exception:
            self.pixel_count_label.setText("Pixels: --")
            self.pixel_count_label.setStyleSheet("font-weight: bold; padding: 5px;")
            
    def on_selection_changed(self, xmin, ymin, xmax, ymax):
        """Handle selection change from map (during dragging)."""
        if xmin == 0 and ymin == 0 and xmax == 0 and ymax == 0:
            # Selection cleared
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
            
    def _snap_bounds_to_cell_size(self, west, south, east, north):
        """Snap bounding box to align with cell size grid.
        
        Returns:
            tuple: (snapped_west, snapped_south, snapped_east, snapped_north, was_adjusted)
        """
        import math
        ds = self.data_sources.get(self.current_data_source, {})
        
        # Determine pixel size in degrees
        if ds.get("native_resolution_only"):
            # Use native pixel size
            pixel_size_degrees = ds.get("native_pixel_size_degrees", 0.004166666666666667)
        else:
            # Convert cell size from meters to degrees (approximate)
            ct = self.cell_size_combo.currentText() if hasattr(self, 'cell_size_combo') else ""
            if ct:
                try:
                    cell_size_m = float(ct)
                    # Approximate conversion: 1 degree ≈ 111320 meters at equator
                    pixel_size_degrees = cell_size_m / 111320.0
                except ValueError:
                    pixel_size_degrees = 0.004166666666666667  # Default
            else:
                pixel_size_degrees = 0.004166666666666667  # Default
        
        # Snap west/east to pixel boundaries (round down for west, round up for east)
        snapped_west = math.floor(west / pixel_size_degrees) * pixel_size_degrees
        snapped_east = math.ceil(east / pixel_size_degrees) * pixel_size_degrees
        
        # Snap south/north to pixel boundaries (round down for south, round up for north)
        snapped_south = math.floor(south / pixel_size_degrees) * pixel_size_degrees
        snapped_north = math.ceil(north / pixel_size_degrees) * pixel_size_degrees
        
        # Check if any adjustment was made
        was_adjusted = (
            abs(snapped_west - west) > 1e-10 or
            abs(snapped_south - south) > 1e-10 or
            abs(snapped_east - east) > 1e-10 or
            abs(snapped_north - north) > 1e-10
        )
        
        return snapped_west, snapped_south, snapped_east, snapped_north, was_adjusted
    
    def on_selection_completed(self, xmin, ymin, xmax, ymax):
        """Handle selection completion (when mouse is released) - zoom to selection."""
        if xmin != 0 or ymin != 0 or xmax != 0 or ymax != 0:
            # Snap bounds to cell size grid
            snapped_west, snapped_south, snapped_east, snapped_north, was_adjusted = self._snap_bounds_to_cell_size(xmin, ymin, xmax, ymax)
            
            if was_adjusted:
                self.log_message(
                    f"Selection bounds adjusted to align with cell size grid: "
                    f"({xmin:.6f}, {ymin:.6f}, {xmax:.6f}, {ymax:.6f}) → "
                    f"({snapped_west:.6f}, {snapped_south:.6f}, {snapped_east:.6f}, {snapped_north:.6f})"
                )
            
            # Store the selected bbox for download
            self.selected_bbox = (snapped_west, snapped_south, snapped_east, snapped_north)
            # Temporarily disconnect the selection changed signal to prevent clearing
            self.map_widget.selectionChanged.disconnect()
            self.zoom_to_selection(snapped_west, snapped_south, snapped_east, snapped_north)
            # Reconnect the signal
            self.map_widget.selectionChanged.connect(self.on_selection_changed)
            # Set the final bounds in the text fields after zoom (both coordinate systems)
            self.update_coordinate_display(snapped_west, snapped_south, snapped_east, snapped_north)
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
                new_extent = (padded_xmin, padded_ymin, padded_xmax, padded_ymax)
            # Set the extent FIRST, then store the selection bbox
            # This ensures the selection bbox is stored with the correct extent context
            self.map_widget.extent = new_extent
            self.map_widget._requested_extent = new_extent  # Also update _requested_extent for accurate coordinate conversion
            # Store the selected bbox in world coordinates for drawing (original selection, no modifications)
            # This is what will be shown in the yellow/green box and used for download
            self.map_widget.selected_bbox_world = (xmin, ymin, xmax, ymax)
            # Ensure service_extent is preserved
            if not hasattr(self.map_widget, 'service_extent') or self.map_widget.service_extent is None:
                self.map_widget.service_extent = self.service_extent
            # Don't clear selection - keep it visible
            self.map_widget.load_map()
            
    def start_download(self):
        """Start downloading the selected area. Bbox is always in GCS (4326)."""
        bbox = None
        if hasattr(self, 'selected_bbox') and self.selected_bbox:
            bbox = self.selected_bbox
        elif self.map_widget:
            bbox = self.map_widget.get_selection_bbox()
        else:
            try:
                west_text = self.west_edit.text().strip()
                south_text = self.south_edit.text().strip()
                east_text = self.east_edit.text().strip()
                north_text = self.north_edit.text().strip()
                if west_text and south_text and east_text and north_text:
                    bbox = (float(west_text), float(south_text), float(east_text), float(north_text))
            except ValueError:
                QMessageBox.warning(self, "Invalid Input", "Please enter valid coordinates.")
                return
        if not bbox:
            QMessageBox.warning(self, "No Selection", "Please select an area on the map.")
            return
        output_crs = "EPSG:4326"
        ds = self.data_sources.get(self.current_data_source, {})
        native_only = ds.get("native_resolution_only", False)
        if native_only:
            # Bbox is (west, south, east, north) in 4326
            bbox_4326 = bbox
            lon_min, lat_min, lon_max, lat_max = bbox
            pixel_size_degrees = ds.get("native_pixel_size_degrees", 0.004166666666666667)
            pixels_width = int((lon_max - lon_min) / pixel_size_degrees)
            pixels_height = int((lat_max - lat_min) / abs(pixel_size_degrees))
            cell_size_for_filename = "native"
        else:
            xmin, ymin, xmax, ymax = bbox
            try:
                cell_size = float(self.cell_size_combo.currentText()) if hasattr(self, 'cell_size_combo') and self.cell_size_combo.count() else 4.0
            except (ValueError, AttributeError):
                cell_size = 4.0
            width_meters = xmax - xmin
            height_meters = ymax - ymin
            pixels_width = int(width_meters / cell_size)
            pixels_height = int(height_meters / cell_size)
            cell_size_for_filename = int(cell_size)
        
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
                return
        
        current_time = datetime.now()
        date_time_str = current_time.strftime("%Y-%m-%d_%H-%M-%S")
        
        # Build list of requested outputs for GEBCO 2025 (any combination of the three)
        output_requests = []  # list of (mode, path)
        tid_url = None
        if native_only and self.current_data_source == "GEBCO 2025" and hasattr(self, 'check_combined'):
            if self.check_combined.isChecked():
                output_requests.append(("combined", None))  # path filled below
            if self.check_bathymetry_only.isChecked():
                output_requests.append(("bathymetry_only", None))
            if self.check_land_only.isChecked():
                output_requests.append(("land_only", None))
            if self.check_direct_measurements_only.isChecked():
                output_requests.append(("direct_measurements_only", None))
            if self.check_direct_unknown_measurements_only.isChecked():
                output_requests.append(("direct_unknown_measurements_only", None))
            if output_requests:
                tid_url = self.data_sources.get("GEBCO 2025 TID", {}).get("url")
            if self.current_data_source == "GEBCO 2025" and not output_requests:
                QMessageBox.warning(self, "No Output Selected", "Select at least one output: Combined Bathymetry && Land, Bathymetry Only, Land Only, Direct Measurements Only, or Direct && Unknown Measurement Only.")
                return
        
        # Resolve output path(s) for GEBCO 2025 (multiple outputs possible)
        if native_only and "TID" not in self.current_data_source and output_requests:
            if len(output_requests) > 1:
                if not self.output_directory or not os.path.isdir(self.output_directory):
                    QMessageBox.warning(self, "Output Directory Required", "Select an output directory when saving multiple grids.")
                    return
                out_dir = self.output_directory
                resolved = []
                for mode, _ in output_requests:
                    # Use shorter names for certain modes
                    if mode == "bathymetry_only":
                        mode_name = "bathymetry"
                    elif mode == "land_only":
                        mode_name = "land"
                    elif mode == "direct_measurements_only":
                        mode_name = "direct"
                    elif mode == "direct_unknown_measurements_only":
                        mode_name = "direct_unknown"
                    else:
                        mode_name = mode
                    fn = f"GEBCO_2025_{mode_name}_{date_time_str}.tif"
                    resolved.append((mode, os.path.join(out_dir, fn)))
                output_requests = resolved
            else:
                # Single output
                mode = output_requests[0][0]
                # Use shorter names for certain modes
                if mode == "bathymetry_only":
                    mode_name = "bathymetry"
                elif mode == "land_only":
                    mode_name = "land"
                elif mode == "direct_measurements_only":
                    mode_name = "direct"
                elif mode == "direct_unknown_measurements_only":
                    mode_name = "direct_unknown"
                else:
                    mode_name = mode
                default_name = f"GEBCO_2025_{mode_name}_{date_time_str}.tif"
                if self.output_directory and os.path.isdir(self.output_directory):
                    output_path = os.path.join(self.output_directory, default_name)
                else:
                    output_path, _ = QFileDialog.getSaveFileName(self, "Save GeoTIFF", default_name, "GeoTIFF Files (*.tif *.tiff);;All Files (*)")
                    if not output_path:
                        return
                output_requests = [(mode, output_path)]
        elif native_only and "TID" in self.current_data_source:
            default_filename = f"GEBCO_2025_TID_{date_time_str}.tif"
            if self.output_directory and os.path.isdir(self.output_directory):
                output_path = os.path.join(self.output_directory, default_filename)
            else:
                output_path, _ = QFileDialog.getSaveFileName(self, "Save GeoTIFF", default_filename, "GeoTIFF Files (*.tif *.tiff);;All Files (*)")
                if not output_path:
                    return
            output_requests = [("combined", output_path)]  # TID is single "combined" style
        elif native_only:
            default_filename = f"GEBCO_2025_{date_time_str}.tif"
            if self.output_directory and os.path.isdir(self.output_directory):
                output_path = os.path.join(self.output_directory, default_filename)
            else:
                output_path, _ = QFileDialog.getSaveFileName(self, "Save GeoTIFF", default_filename, "GeoTIFF Files (*.tif *.tiff);;All Files (*)")
                if not output_path:
                    return
            output_requests = [("combined", output_path)]
        else:
            default_filename = f"GEBCO_Bathy_{cell_size_for_filename}m_{date_time_str}.tif"
            if self.output_directory and os.path.isdir(self.output_directory):
                output_path = os.path.join(self.output_directory, default_filename)
            else:
                output_path, _ = QFileDialog.getSaveFileName(self, "Save GeoTIFF", default_filename, "GeoTIFF Files (*.tif *.tiff);;All Files (*)")
                if not output_path:
                    return
            output_requests = [("combined", output_path)]
        
        # Disable download button
        self.download_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting download...")
        
        # Get tile download setting
        use_tile_download = self.tile_download_checkbox.isChecked()
        
        max_size = 14000
        if native_only:
            self.downloader = BathymetryDownloader(
                self.base_url,
                bbox_4326,
                None,  # output_path unused when output_requests provided
                output_crs,
                pixel_size=None,
                max_size=max_size,
                use_tile_download=use_tile_download,
                bbox_in_4326=True,
                pixel_size_degrees=pixel_size_degrees,
                tid_url=tid_url,
                output_requests=output_requests
            )
        else:
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
        """Handle download completion. file_path may be newline-separated for multiple files."""
        paths = [p.strip() for p in file_path.splitlines() if p.strip()]
        if not paths:
            paths = [file_path]
        display = "\n".join(paths)
        self.status_label.setText(f"Download complete: {paths[0]}" if len(paths) == 1 else f"Download complete: {len(paths)} files")
        self.log_message(f"✓ Download complete: {display}")
        self.download_btn.setEnabled(True)
        # Remove bold formatting after download completes
        font = self.download_btn.font()
        font.setBold(False)
        self.download_btn.setFont(font)
        QMessageBox.information(self, "Success", f"GeoTIFF(s) saved to:\n{display}")
        
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
        
    def log_message(self, message, bold=False):
        """Add message to log. If bold is True, the message is shown in bold (HTML)."""
        if bold:
            message = f"<b>{message}</b>"
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
            "  3. You can also manually enter coordinates in the West/South/East/North (GCS) fields",
            "",
            "To download the selected area:",
            "  1. Select an area on the map (or enter coordinates)",
            "  2. For GEBCO 2025, choose Combined Bathymetry && Land, Bathymetry Only, Land Only, Direct Measurements Only, or Direct && Unknown Measurement Only if needed",
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
        
        # Always preserve the selected area when switching data sources
        saved_selection = None
        if hasattr(self, 'selected_bbox') and self.selected_bbox:
            # Keep the selection regardless of overlap with new data source
            saved_selection = self.selected_bbox
        
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
            # Update service extent in map widget
            self.map_widget.service_extent = self.service_extent
            # Don't update pixel sizes here - they will be updated in on_service_info_loaded after the new service loads
            # This ensures we get the correct pixel sizes for the new data source
        
        # Show/hide download mode options (Combined/Bathymetry Only/Land Only) for GEBCO 2025 only
        self._update_download_mode_visibility()
        
        # Update attribution text
        self._update_attribution()
        
        # Reload service info (this will update extent and reload map)
        self.load_service_info()
        
        # Store selection to restore after map loads (will zoom to it if it overlaps)
        self._pending_selection = saved_selection
    
    def _update_download_mode_visibility(self):
        """Show Output Data Types groupbox only when GEBCO 2025 (not TID) is selected."""
        if hasattr(self, 'output_data_types_group'):
            is_gebco_2025_not_tid = (
                self.current_data_source == "GEBCO 2025"
            )
            self.output_data_types_group.setVisible(is_gebco_2025_not_tid)
    
    def _update_attribution(self):
        """Update the attribution text based on the current data source."""
        if not hasattr(self, 'attribution_label'):
            return
        
        ds = self.data_sources.get(self.current_data_source, {})
        attribution_text = ds.get("attribution", "")
        attribution_url = ds.get("attribution_url", "")
        
        if attribution_text:
            self.attribution_label.setText(attribution_text)
            self.attribution_label.setToolTip(f"Click to open: {attribution_url}")
            self._current_attribution_url = attribution_url
            self.attribution_label.setVisible(True)
        else:
            self.attribution_label.setVisible(False)
            self._current_attribution_url = None
    
    def _open_attribution_url(self):
        """Open the attribution URL in the default web browser."""
        if hasattr(self, '_current_attribution_url') and self._current_attribution_url:
            QDesktopServices.openUrl(QUrl(self._current_attribution_url))
    
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
            
            # Update map widget's selected_bbox_world so the selection box is drawn
            if self.map_widget:
                self.map_widget.selected_bbox_world = bbox
                self.map_widget.set_selection_validity(True)
            
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

