"""
Map widget for displaying bathymetry data and selecting areas of interest.
"""
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QRect, QPoint, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QPixmap, QImage
import requests
from io import BytesIO
from PIL import Image
import numpy as np
import math
import pyproj

# Web Mercator constants for tile math (EPSG:3857)
_WEB_MERCATOR_HALF = 20037508.34
_TILE_SIZE = 256


class BasemapLoader(QThread):
    """Load World Imagery basemap by fetching and compositing tiles from the tile endpoint.
    View extent is in GCS (4326); tiles are in Web Mercator (3857) scheme."""
    tileLoaded = pyqtSignal(QPixmap)
    
    def __init__(self, bbox_4326, size):
        super().__init__()
        self.bbox_4326 = bbox_4326  # (west, south, east, north) in degrees
        self.size = size  # (width, height)
        self.base_url = "https://wi.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer"
        
    def run(self):
        try:
            west, south, east, north = self.bbox_4326
            width, height = self.size
            # Clamp lat for 4326->3857 conversion (poles are infinite in 3857)
            lat_limit = 85.0511287798066
            south_c = max(south, -lat_limit)
            north_c = min(north, lat_limit)
            tr = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
            xmin, ymin = tr.transform(west, south_c)
            xmax, ymax = tr.transform(east, north_c)
            # Choose level so that we need ~width/256 tiles (one tile ≈ 256 view pixels)
            extent_merc_width = xmax - xmin
            if extent_merc_width <= 0:
                self.tileLoaded.emit(QPixmap())
                return
            # 2^level tiles span the world; we want tile_merc_width ≈ extent_merc_width / (width/256)
            # tile_merc_width = 2 * _WEB_MERCATOR_HALF / 2^level  => 2^level = 2*_WEB_MERCATOR_HALF / tile_merc_width
            tiles_wide = max(1, width / _TILE_SIZE)
            tile_merc_width = extent_merc_width / tiles_wide
            level = max(0, min(23, int(round(math.log2(2 * _WEB_MERCATOR_HALF / tile_merc_width)))))
            n = 2 ** level
            tile_merc_size = (2 * _WEB_MERCATOR_HALF) / n
            col_min = int((xmin + _WEB_MERCATOR_HALF) / tile_merc_size)
            col_max = int((xmax + _WEB_MERCATOR_HALF) / tile_merc_size)
            row_min = int((_WEB_MERCATOR_HALF - ymax) / tile_merc_size)
            row_max = int((_WEB_MERCATOR_HALF - ymin) / tile_merc_size)
            col_min = max(0, min(col_min, n - 1))
            col_max = max(0, min(col_max, n - 1))
            row_min = max(0, min(row_min, n - 1))
            row_max = max(0, min(row_max, n - 1))
            cols = col_max - col_min + 1
            rows = row_max - row_min + 1
            composite = Image.new("RGB", (int(cols * _TILE_SIZE), int(rows * _TILE_SIZE)), (128, 128, 128))
            for r in range(row_min, row_max + 1):
                for c in range(col_min, col_max + 1):
                    url = f"{self.base_url}/tile/{level}/{r}/{c}"
                    try:
                        resp = requests.get(url, timeout=15)
                        resp.raise_for_status()
                        tile_img = Image.open(BytesIO(resp.content)).convert("RGB")
                        composite.paste(tile_img, ((c - col_min) * _TILE_SIZE, (r - row_min) * _TILE_SIZE))
                    except Exception:
                        pass
            composite = composite.resize((width, height), Image.Resampling.LANCZOS)
            img_bytes = BytesIO()
            composite.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes.getvalue(), "PNG")
            self.tileLoaded.emit(pixmap)
        except Exception as e:
            print(f"Error loading basemap tiles: {e}")
            self.tileLoaded.emit(QPixmap())


class MapTileLoader(QThread):
    """Thread for loading map tiles asynchronously."""
    tileLoaded = pyqtSignal(QPixmap, float, float, float, float)  # pixmap, xmin, ymin, xmax, ymax
    
    def __init__(self, base_url, bbox, size, raster_function="Haxby Percent Clip DRA"):
        super().__init__()
        self.base_url = base_url
        self.bbox = bbox  # (xmin, ymin, xmax, ymax)
        self.size = size  # (width, height)
        self.raster_function = raster_function
        
    def run(self):
        """Load tile from ArcGIS ImageServer."""
        try:
            xmin, ymin, xmax, ymax = self.bbox
            width, height = self.size
            
            print(f"Loading map tile: bbox=({xmin:.2f}, {ymin:.2f}, {xmax:.2f}, {ymax:.2f}), size={width}x{height}")
            
            # Build export URL
            url = f"{self.base_url}/exportImage"
            params = {
                "bbox": f"{xmin},{ymin},{xmax},{ymax}",
                "size": f"{width},{height}",
                "format": "png",
                "f": "image"
            }
            
            # Add raster function as renderingRule if specified
            if self.raster_function and self.raster_function != "None":
                import json
                rendering_rule = {"rasterFunction": self.raster_function}
                params["renderingRule"] = json.dumps(rendering_rule)
                print(f"Using raster function: {self.raster_function}")
            
            # Build full URL for debugging
            from urllib.parse import urlencode
            full_url = f"{url}?{urlencode(params)}"
            print(f"Full URL: {full_url}")
            print(f"Requesting: {url} with params: {params}")
            
            # Request image
            response = requests.get(url, params=params, timeout=30)
            print(f"Response status: {response.status_code}")
            response.raise_for_status()
            
            print(f"Response content length: {len(response.content)} bytes")
            print(f"Response content type: {response.headers.get('Content-Type', 'unknown')}")
            
            # Convert to QPixmap - use a more reliable method
            img = Image.open(BytesIO(response.content))
            print(f"Image opened: {img.size}, mode: {img.mode}")
            
            # Save to bytes and load directly into QPixmap
            img_bytes = BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            # Load directly into QPixmap from bytes
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes.getvalue(), 'PNG')
            
            if pixmap.isNull():
                # Fallback: convert via RGB array
                print("Direct load failed, trying array conversion...")
                img_rgb = img.convert("RGB")
                img_array = np.array(img_rgb, dtype=np.uint8)
                height, width, channel = img_array.shape
                
                # Ensure array is contiguous and copy the data
                if not img_array.flags['C_CONTIGUOUS']:
                    img_array = np.ascontiguousarray(img_array)
                
                # Create QImage - need to keep array in scope
                bytes_per_line = 3 * width
                q_image = QImage(img_array.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
                # Copy the image to ensure data persists
                q_image = q_image.copy()
                pixmap = QPixmap.fromImage(q_image)
            
            # Verify pixmap has content
            if not pixmap.isNull():
                test_img = pixmap.toImage()
                if not test_img.isNull():
                    test_color = test_img.pixelColor(pixmap.width()//2, pixmap.height()//2)
                    print(f"Pixmap center pixel: R={test_color.red()}, G={test_color.green()}, B={test_color.blue()}")
            
            print(f"Created pixmap: {pixmap.width()}x{pixmap.height()}, isNull: {pixmap.isNull()}")
            
            print("Emitting tileLoaded signal...")
            self.tileLoaded.emit(pixmap, xmin, ymin, xmax, ymax)
            print("tileLoaded signal emitted")
            
        except Exception as e:
            print(f"Error loading tile: {e}")
            import traceback
            traceback.print_exc()
            # Emit empty pixmap on error
            self.tileLoaded.emit(QPixmap(), *self.bbox)


class MapServerLoader(QThread):
    """Load a single image from an ArcGIS MapServer (e.g. GEBCO Haxby). Bbox in GCS (4326)."""
    tileLoaded = pyqtSignal(QPixmap, float, float, float, float)  # pixmap, west, south, east, north

    def __init__(self, map_server_url, bbox_4326, size, transparent=False):
        super().__init__()
        self.map_server_url = map_server_url.rstrip("/")
        self.bbox_4326 = bbox_4326  # (west, south, east, north) in degrees
        self.size = size
        self.transparent = transparent  # Whether to request transparent PNG

    def run(self):
        try:
            west, south, east, north = self.bbox_4326
            width, height = self.size
            max_side = 4096
            if width > max_side or height > max_side:
                scale = min(max_side / width, max_side / height)
                width = int(width * scale)
                height = int(height * scale)
            url = f"{self.map_server_url}/export"
            params = {
                "bbox": f"{west},{south},{east},{north}",
                "bboxSR": "4326",
                "size": f"{width},{height}",
                "format": "png",
                "f": "image",
                "transparent": "true" if self.transparent else "false",
            }
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            img_bytes = BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes.getvalue(), "PNG")
            if pixmap.isNull():
                img_rgb = img.convert("RGB")
                img_array = np.array(img_rgb, dtype=np.uint8)
                h, w = img_array.shape[:2]
                bytes_per_line = 3 * w
                q_image = QImage(img_array.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(q_image.copy())
            self.tileLoaded.emit(pixmap, west, south, east, north)
        except Exception as e:
            print(f"MapServerLoader error: {e}")
            self.tileLoaded.emit(QPixmap(), *self.bbox_4326)


class MapWidget(QWidget):
    """Interactive map widget for displaying bathymetry and selecting areas."""
    
    selectionChanged = pyqtSignal(float, float, float, float)  # xmin, ymin, xmax, ymax
    selectionCompleted = pyqtSignal(float, float, float, float)  # xmin, ymin, xmax, ymax - emitted when selection is finished
    mapFirstLoaded = pyqtSignal()  # Emitted when map is successfully loaded for the first time
    statusMessage = pyqtSignal(str)  # Emit status/log messages
    
    def set_selection_validity(self, is_valid):
        """Set whether the current selection is within size limits."""
        if self.selection_is_valid != is_valid:
            self.selection_is_valid = is_valid
            self.update()  # Trigger repaint to update color
    
    def __init__(self, base_url, initial_extent, parent=None, raster_function="Shaded Relief - Haxby - MD Hillshade 2", show_basemap=True, show_hillshade=True, use_blend=False, hillshade_raster_function="Multidirectional Hillshade 3x", display_url=None, land_display_url=None):
        super().__init__(parent)
        self.base_url = base_url
        self.display_url = display_url  # When set, map is drawn from this MapServer (e.g. GEBCO Haxby) instead of ImageServer layers
        self.land_display_url = land_display_url  # Land layer MapServer (e.g. GEBCO Land Grey) shown as basemap
        self.extent = initial_extent  # (west, south, east, north) in GCS (4326)
        self.current_pixmap = QPixmap()
        self.basemap_pixmap = QPixmap()
        self.hillshade_pixmap = QPixmap()
        self.show_basemap = show_basemap
        self.show_hillshade = show_hillshade
        self.show_legend = False  # Legend visibility (off by default)
        self.use_blend = use_blend  # Use Multiply blend mode for top layer
        self.bathymetry_opacity = 1.0  # Opacity for bathymetry layer (0.0 to 1.0) - default 100%
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.is_panning = False
        self.pan_start = None
        self.pan_origin = None  # Track original pan start position for drawing pan line
        self.pan_end = None  # Track current pan position for drawing pan line
        self.raster_function = raster_function
        self.hillshade_raster_function = hillshade_raster_function  # Raster function for hillshade layer
        self.pixel_size_x = None  # Pixel size in X direction from service (meters)
        self.pixel_size_y = None  # Pixel size in Y direction from service (meters)
        self.map_loaded = False
        self._first_load_complete = False  # Track if first load has completed
        self._loading = False  # Flag to prevent multiple simultaneous loads
        self._active_loaders = []  # Track active loaders
        self._load_timer = None  # Timer for debouncing zoom operations
        self.selected_bbox_world = None  # (west, south, east, north) in GCS (4326)
        self.selection_is_valid = True  # Track if selection is within size limits (True = valid/green, False = too large/red)
        self.service_extent = None  # Store service extent to distinguish dataset bounds from user selection
        self._extent_locked = False  # Flag to prevent extent changes during resize
        self._original_pixmap_size = None  # Store original pixmap size before scaling for coordinate conversion
        self._scaled_pixmap_size = None  # Store scaled pixmap size (what's actually drawn)
        self._requested_extent = initial_extent  # (west, south, east, north) GCS
        print(f"MapWidget initialized with raster function: {self.raster_function}, show_basemap: {self.show_basemap}, show_hillshade: {self.show_hillshade}, use_blend: {self.use_blend}")
        
        # Set a smaller minimum size to allow 60/40 split (60% of 1200 = 720px)
        self.setMinimumSize(600, 400)
        self.setMouseTracking(True)
        
        # Don't load map immediately - wait for widget to be shown and sized
        # The load will be triggered by showEvent or when explicitly called
        
    def set_raster_function(self, raster_function):
        """Set the raster function for map display."""
        self.raster_function = raster_function
        self.load_map()
        
    def showEvent(self, event):
        """Handle widget being shown - trigger map load if not already loaded."""
        super().showEvent(event)
        print(f"MapWidget showEvent called, map_loaded={self.map_loaded}, size={self.width()}x{self.height()}")
        # Don't auto-load here - let MainWindow control when to load
        # This ensures the REST endpoint extent is available before loading
        # The map will be loaded explicitly by MainWindow after service info loads
        if not self.map_loaded:
            print("MapWidget showEvent: Waiting for MainWindow to trigger map load after service info loads")
            
    def _stop_all_loaders(self):
        """Stop all active loaders."""
        loaders_to_stop = []
        if hasattr(self, 'loader') and self.loader:
            loaders_to_stop.append(self.loader)
        if hasattr(self, 'basemap_loader') and self.basemap_loader:
            loaders_to_stop.append(self.basemap_loader)
        if hasattr(self, 'hillshade_loader') and self.hillshade_loader:
            loaders_to_stop.append(self.hillshade_loader)
        
        for loader in loaders_to_stop:
            if loader.isRunning():
                loader.terminate()
                loader.wait(500)  # Wait up to 500ms
                if loader.isRunning():
                    # Force kill if still running
                    loader.terminate()
                    loader.wait(500)
        
        # Disconnect all signals to prevent callbacks from dead threads
        for loader in loaders_to_stop:
            try:
                loader.tileLoaded.disconnect()
                loader.finished.disconnect()
            except:
                pass
        
        self._active_loaders = []
    
    def _check_all_loaders_finished(self):
        """Check if all loaders are finished and reset loading flag."""
        if not self._loading:
            return
        
        all_finished = True
        if hasattr(self, 'loader') and self.loader and self.loader.isRunning():
            all_finished = False
        if hasattr(self, 'basemap_loader') and self.basemap_loader and self.basemap_loader.isRunning():
            all_finished = False
        if hasattr(self, 'hillshade_loader') and self.hillshade_loader and self.hillshade_loader.isRunning():
            all_finished = False
        
        if all_finished:
            self._loading = False
    
    def load_map(self):
        """Load map for current extent."""
        # Cancel any pending load timer
        if self._load_timer:
            self._load_timer.stop()
            self._load_timer = None
        
        # Prevent multiple simultaneous loads
        if self._loading:
            print("load_map() already in progress, skipping...")
            return
            
        # Stop all existing loaders first
        self._stop_all_loaders()
        
        self._loading = True
        
        # Preserve the current extent - we'll use this for the request
        # and restore it after loading to prevent the selection from moving
        requested_extent = self.extent
        
        print("=" * 50)
        print("load_map() called!")
        print(f"Widget visible: {self.isVisible()}")
        print(f"Widget size: {self.width()}x{self.height()}")
        print(f"Extent: {self.extent}")
        print(f"Base URL: {self.base_url}")
        
        # Ensure widget has a valid size
        widget_width = self.width()
        widget_height = self.height()
        
        # If widget has no size yet, use minimum size
        if widget_width <= 0 or widget_height <= 0:
            widget_width = 800
            widget_height = 600
            print(f"Widget has no size yet, using default: {widget_width}x{widget_height}")
        else:
            print(f"Widget size: {widget_width}x{widget_height}")
        
        # Use widget size to fill the window completely
        size = (widget_width, widget_height)
        
        # Determine raster function based on area of interest pixel dimensions in source data
        # Check if this is the Hi Resolution or Regional service by checking the base_url
        is_hi_resolution = "WGOM_LI_SNE_BTY_4m" in self.base_url
        is_regional = "WGOM_LI_SNE_BTY" in self.base_url and "16m" in self.base_url
        uses_dynamic_raster_function = is_hi_resolution or is_regional
        
        if uses_dynamic_raster_function:
            # Get the area of interest (selected bbox) or use current extent if no selection
            area_bbox = self.selected_bbox_world if self.selected_bbox_world else requested_extent
            
            # Get pixel size from service (default based on service type if not available)
            # IMPORTANT: Use actual pixel sizes from service, not defaults, unless they're None
            if is_hi_resolution:
                default_pixel_size = 4.0
            else:  # Regional
                default_pixel_size = 16.0
            
            # Use actual pixel sizes from service if available, otherwise use service-specific default
            pixel_size_x = self.pixel_size_x if self.pixel_size_x is not None else default_pixel_size
            pixel_size_y = self.pixel_size_y if self.pixel_size_y is not None else default_pixel_size
            
            # Calculate pixel dimensions in source data
            xmin, ymin, xmax, ymax = area_bbox
            pixels_x = int((xmax - xmin) / abs(pixel_size_x))
            pixels_y = int((ymax - ymin) / abs(pixel_size_y))
            
            # Use "StdDev - BlueGreen" for areas > 4000 pixels in either dimension
            # Use "DAR - StdDev - BlueGreen" for areas <= 4000 pixels in both dimensions
            if pixels_x > 4000 or pixels_y > 4000:
                new_raster_function = "StdDev - BlueGreen"
            else:
                new_raster_function = "DAR - StdDev - BlueGreen"
            
            # Update raster function if it changed
            if self.raster_function != new_raster_function:
                msg = f"Updating raster function based on area of interest size ({pixels_x}x{pixels_y} source pixels): {self.raster_function} -> {new_raster_function}"
                print(msg)
                # Format message with green color for raster function info
                green_msg = f'<span style="color: green;">{msg}</span>'
                self.statusMessage.emit(green_msg)
                self.raster_function = new_raster_function
        
        # Always log which raster function is being used
        if uses_dynamic_raster_function and self.selected_bbox_world:
            area_bbox = self.selected_bbox_world
            # Get pixel size from service (default based on service type if not available)
            if is_hi_resolution:
                default_pixel_size = 4.0
            else:  # Regional
                default_pixel_size = 16.0
            pixel_size_x = self.pixel_size_x if self.pixel_size_x is not None else default_pixel_size
            pixel_size_y = self.pixel_size_y if self.pixel_size_y is not None else default_pixel_size
            xmin, ymin, xmax, ymax = area_bbox
            pixels_x = int((xmax - xmin) / abs(pixel_size_x))
            pixels_y = int((ymax - ymin) / abs(pixel_size_y))
            raster_info_msg = f"Map display using raster function: {self.raster_function} (area of interest: {pixels_x}x{pixels_y} source pixels)"
        else:
            raster_info_msg = f"Map display using raster function: {self.raster_function}"
        print(raster_info_msg)
        # Format message with green color for raster function info
        green_raster_info_msg = f'<span style="color: green;">{raster_info_msg}</span>'
        self.statusMessage.emit(green_raster_info_msg)
        
        print(f"Starting map load with extent: {requested_extent}, size: {size}")
        print(f"Using raster function: {self.raster_function}")
        
        # Store the requested extent so we can restore it after loading
        self._requested_extent = requested_extent
        
        # When display_url is set (e.g. GEBCO MapServer), use GCS extent: land basemap + display layer
        if self.display_url:
            if self.land_display_url:
                print("Loading land basemap (GCS)...")
                # Land layer: opaque (transparent=False) so it's always visible
                self.basemap_loader = MapServerLoader(self.land_display_url, requested_extent, size, transparent=False)
                # MapServerLoader emits (pixmap, west, south, east, north); extract just pixmap
                self.basemap_loader.tileLoaded.connect(lambda pixmap, *args: self.on_basemap_loaded(pixmap))
                self.basemap_loader.finished.connect(self._check_all_loaders_finished)
                self._active_loaders.append(self.basemap_loader)
                self.basemap_loader.start()
            print("Loading display layer (GCS)...")
            # Bathymetry layer: transparent (transparent=True) so land shows through
            self.loader = MapServerLoader(self.display_url, requested_extent, size, transparent=True)
            self.loader.tileLoaded.connect(self.on_tile_loaded)
            self.loader.finished.connect(self.on_loader_finished)
            self.loader.finished.connect(self._check_all_loaders_finished)
            self._active_loaders.append(self.loader)
            self.loader.start()
            self.map_loaded = True
            print("=" * 50)
            return
        
        # Load basemap if enabled (non-display_url path)
        if self.show_basemap:
            print("Loading basemap...")
            self.basemap_loader = BasemapLoader(requested_extent, size)
            self.basemap_loader.tileLoaded.connect(self.on_basemap_loaded)
            self.basemap_loader.finished.connect(self._check_all_loaders_finished)
            self._active_loaders.append(self.basemap_loader)
            self.basemap_loader.start()
        
        # Load hillshade layer if enabled (as underlay)
        if self.show_hillshade:
            print("Loading hillshade layer...")
            self.hillshade_loader = MapTileLoader(self.base_url, requested_extent, size, self.hillshade_raster_function)
            self.hillshade_loader.tileLoaded.connect(self.on_hillshade_loaded)
            self.hillshade_loader.finished.connect(self._check_all_loaders_finished)
            self._active_loaders.append(self.hillshade_loader)
            self.hillshade_loader.start()
        
        # Load bathymetry layer (main layer)
        print("Creating MapTileLoader...")
        self.loader = MapTileLoader(self.base_url, requested_extent, size, self.raster_function)
        print("Connecting signals...")
        self.loader.tileLoaded.connect(self.on_tile_loaded)
        self.loader.finished.connect(self.on_loader_finished)
        self.loader.finished.connect(self._check_all_loaders_finished)
        self._active_loaders.append(self.loader)
        print("Starting loader thread...")
        self.loader.start()
        print(f"Loader thread started, isRunning: {self.loader.isRunning()}")
        self.map_loaded = True
        print("=" * 50)
        
    def on_basemap_loaded(self, pixmap):
        """Handle basemap tile loaded."""
        if not pixmap.isNull():
            # Ensure basemap is fully opaque (remove alpha channel if present)
            # Convert to QImage, then to RGB format to remove transparency
            qimage = pixmap.toImage()
            if qimage.hasAlphaChannel():
                # Convert to RGB888 format (removes alpha channel, truly opaque)
                qimage = qimage.convertToFormat(QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(qimage)
            
            widget_size = self.size()
            if widget_size.width() > 0 and widget_size.height() > 0:
                if widget_size.width() == pixmap.width() and widget_size.height() == pixmap.height():
                    self.basemap_pixmap = pixmap
                else:
                    self.basemap_pixmap = pixmap.scaled(
                        widget_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
            else:
                self.basemap_pixmap = pixmap
            print(f"Basemap loaded: {self.basemap_pixmap.width()}x{self.basemap_pixmap.height()}")
            self.update()  # Trigger repaint
            
    def on_hillshade_loaded(self, pixmap, xmin, ymin, xmax, ymax):
        """Handle hillshade tile loaded."""
        if not pixmap.isNull():
            widget_size = self.size()
            if widget_size.width() > 0 and widget_size.height() > 0:
                if widget_size.width() == pixmap.width() and widget_size.height() == pixmap.height():
                    self.hillshade_pixmap = pixmap
                else:
                    self.hillshade_pixmap = pixmap.scaled(
                        widget_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
            else:
                self.hillshade_pixmap = pixmap
            print(f"Hillshade loaded: {self.hillshade_pixmap.width()}x{self.hillshade_pixmap.height()}")
            self.update()  # Trigger repaint
        
    def on_loader_finished(self):
        """Handle loader thread finishing."""
        # If we still have an empty pixmap, the load might have failed
        if self.current_pixmap.isNull():
            print("Warning: Map tile loader finished but no pixmap was loaded")
        
    def on_tile_loaded(self, pixmap, xmin, ymin, xmax, ymax):
        """Handle loaded tile."""
        print(f"on_tile_loaded called! pixmap.isNull: {pixmap.isNull()}, size: {pixmap.width()}x{pixmap.height()}")
        if not pixmap.isNull():
            # Check if pixmap has actual content (not all white/transparent)
            # Sample a few pixels to verify
            sample_image = pixmap.toImage()
            if not sample_image.isNull():
                # Sample a few pixels
                colors = []
                for x in [10, pixmap.width()//2, pixmap.width()-10]:
                    for y in [10, pixmap.height()//2, pixmap.height()-10]:
                        if x < pixmap.width() and y < pixmap.height():
                            color = sample_image.pixelColor(x, y)
                            colors.append((color.red(), color.green(), color.blue()))
                print(f"Sample pixel colors: {colors[:3]}...")  # Print first 3
            
            widget_size = self.size()
            print(f"Widget size in on_tile_loaded: {widget_size.width()}x{widget_size.height()}")
            
            # Store original pixmap size before any scaling
            # This is needed for accurate world-to-screen coordinate conversion
            # The original pixmap size represents the actual pixel dimensions requested from the server
            # which directly correspond to the geographic extent
            self._original_pixmap_size = (pixmap.width(), pixmap.height())
            
            # CRITICAL: For coordinate conversion, we need to use a consistent reference size
            # When the pixmap matches the widget size, we should still use the widget size
            # for coordinate conversion to maintain consistent visual size of the selection box
            # When the pixmap is scaled, we use the scaled size
            
            # Don't scale if sizes match - use pixmap directly
            if widget_size.width() == pixmap.width() and widget_size.height() == pixmap.height():
                print("Pixmap size matches widget, using directly")
                self.current_pixmap = pixmap
                # Use widget size for coordinate conversion to maintain consistent visual size
                # This ensures the selection box doesn't change size when pixmap pixel size changes
                self._scaled_pixmap_size = (widget_size.width(), widget_size.height())
            elif widget_size.width() > 0 and widget_size.height() > 0:
                # Scale to fit widget while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(
                    widget_size, 
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                print(f"Scaled pixmap: {scaled_pixmap.width()}x{scaled_pixmap.height()}")
                self.current_pixmap = scaled_pixmap
                # Use the scaled size (what's actually drawn) for coordinate conversion
                self._scaled_pixmap_size = (scaled_pixmap.width(), scaled_pixmap.height())
            else:
                # Widget not sized yet, use pixmap as-is
                print("Widget not sized, using pixmap as-is")
                self.current_pixmap = pixmap
                self._scaled_pixmap_size = (pixmap.width(), pixmap.height())  # No scaling
                
            # ALWAYS preserve the requested extent instead of using the server's response
            # This prevents the selection from moving when the window is resized
            # The _requested_extent is set in load_map() and should be preserved
            # until the user explicitly changes the extent (via pan/zoom)
            if self._extent_locked:
                # Extent is locked (during resize) - never change it
                pass  # Keep current extent unchanged
            elif hasattr(self, '_requested_extent') and self._requested_extent is not None:
                # Restore the extent we requested, not what the server returned
                # This ensures coordinate conversion uses the correct extent
                self.extent = self._requested_extent
                # Keep _requested_extent so it persists across multiple loads during resize
            else:
                # First load - use server response for accurate coordinate conversion
                # The server's returned extent matches what's actually displayed
                # However, if we have a _requested_extent set (from initial load), use that instead
                # to ensure coordinate conversion matches what we intended to display
                if hasattr(self, '_requested_extent') and self._requested_extent is not None:
                    # Use the requested extent (which should be the service extent)
                    self.extent = self._requested_extent
                    # Keep _requested_extent for consistency
                else:
                    # Fallback to server response if no requested extent
                    server_extent = (xmin, ymin, xmax, ymax)
                    self.extent = server_extent
                    self._requested_extent = server_extent
            print(f"Setting current_pixmap, isNull: {self.current_pixmap.isNull()}, size: {self.current_pixmap.width()}x{self.current_pixmap.height()}")
            print(f"Calling update() to repaint widget")
            
            # CRITICAL: Force immediate repaint to ensure selection box is redrawn with new pixmap size
            # This is especially important during window resize when pixmap size changes
            # The selection box will be recalculated in paintEvent using the new pixmap size
            self.update()  # Trigger repaint immediately
            self.repaint()  # Force immediate repaint
            
            # Also schedule a delayed repaint to ensure box is visible after map loads
            # This is especially important after zoom operations
            if self.selected_bbox_world:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(100, lambda: self.update())
            
            print(f"Map tile loaded successfully: {pixmap.width()}x{pixmap.height()}")
            if self.selected_bbox_world:
                print(f"Selected bbox exists: {self.selected_bbox_world}, will be repainted")
            
            # Emit signal on first successful load
            if not self._first_load_complete:
                self._first_load_complete = True
                # Don't set default bounds here - let MainWindow handle it after extent is confirmed
                # The extent at this point matches what's displayed, so coordinate conversion will be accurate
                self.mapFirstLoaded.emit()
        else:
            print("Error: Received null pixmap from tile loader")
            
    def screen_to_world(self, point):
        """Convert screen coordinates to world coordinates."""
        if self.current_pixmap.isNull():
            return None
            
        pixmap_rect = self.current_pixmap.rect()
        pixmap_rect.moveCenter(self.rect().center())
        
        if not pixmap_rect.contains(point):
            return None
            
        # Calculate relative position in pixmap
        rel_x = (point.x() - pixmap_rect.left()) / pixmap_rect.width()
        rel_y = (point.y() - pixmap_rect.top()) / pixmap_rect.height()
        
        # CRITICAL: Always use _requested_extent if available, as it matches what was actually requested and displayed
        # This ensures coordinate conversion is accurate, especially on first load
        # If _requested_extent is not set, use self.extent, but this should only happen before first map load
        if hasattr(self, '_requested_extent') and self._requested_extent is not None:
            xmin, ymin, xmax, ymax = self._requested_extent
        elif self.extent:
            # Fallback to current extent if _requested_extent not set yet
            xmin, ymin, xmax, ymax = self.extent
        else:
            # No extent available - cannot convert
            return None
        
        world_x = xmin + rel_x * (xmax - xmin)
        world_y = ymax - rel_y * (ymax - ymin)  # Y is inverted in screen coordinates
        
        return (world_x, world_y)
        
    def world_to_screen(self, world_x, world_y):
        """Convert world coordinates to screen coordinates."""
        if self.current_pixmap.isNull():
            return None
        
        widget_rect = self.rect()
        widget_width = widget_rect.width()
        widget_height = widget_rect.height()
        
        # CRITICAL FIX: Use widget size for coordinate conversion when pixmap size doesn't match
        # This ensures the selection box is drawn correctly even when the pixmap hasn't been updated yet
        # Get the actual pixmap rect (what's actually drawn)
        pixmap_rect = self.current_pixmap.rect()
        pixmap_width = pixmap_rect.width()
        pixmap_height = pixmap_rect.height()
        
        # If pixmap size matches widget size, use pixmap size
        # Otherwise, use widget size (pixmap will be scaled to fit widget)
        if pixmap_width == widget_width and pixmap_height == widget_height:
            # Pixmap matches widget - use pixmap size
            target_width = pixmap_width
            target_height = pixmap_height
            x = 0
            y = 0
        else:
            # Pixmap doesn't match widget - use widget size (pixmap will be centered/scaled)
            # Center the pixmap in the widget (EXACT same logic as in paintEvent)
            x = (widget_width - pixmap_width) // 2
            y = (widget_height - pixmap_height) // 2
            # Use widget size for coordinate conversion (pixmap will be scaled to fit)
            target_width = widget_width
            target_height = widget_height
            x = 0
            y = 0
        
        # Create the target rect that matches paintEvent exactly
        target_rect = QRect(x, y, target_width, target_height)
        
        # Use _requested_extent if available, as it matches what was actually requested and displayed
        # This ensures coordinate conversion is accurate and consistent with screen_to_world
        if hasattr(self, '_requested_extent') and self._requested_extent is not None:
            xmin, ymin, xmax, ymax = self._requested_extent
        elif self.extent:
            # Fallback to current extent if _requested_extent not set yet
            xmin, ymin, xmax, ymax = self.extent
        else:
            # No extent available - cannot convert
            return None
        
        # Calculate relative position within the extent (0.0 to 1.0)
        # This is independent of pixmap size - it's purely based on geographic extent
        rel_x = (world_x - xmin) / (xmax - xmin) if (xmax - xmin) != 0 else 0
        rel_y = (ymax - world_y) / (ymax - ymin) if (ymax - ymin) != 0 else 0  # Y is inverted
        
        # Convert to screen coordinates using the target rect (same as paintEvent)
        # The target rect represents where the geographic extent is drawn on screen
        # CRITICAL: This must use the same rect calculation as paintEvent
        screen_x = target_rect.left() + rel_x * target_rect.width()
        screen_y = target_rect.top() + rel_y * target_rect.height()
        
        # Clamp coordinates to widget bounds to prevent drawing outside the widget
        widget_rect = self.rect()
        clamped_x = max(0, min(int(screen_x), widget_rect.width() - 1))
        clamped_y = max(0, min(int(screen_y), widget_rect.height() - 1))
        result = QPoint(clamped_x, clamped_y)
        return result
        
    def get_selection_bbox(self):
        """Get the bounding box of the current selection in world coordinates."""
        if not self.selection_start or not self.selection_end:
            return None
            
        start_world = self.screen_to_world(self.selection_start)
        end_world = self.screen_to_world(self.selection_end)
        
        if not start_world or not end_world:
            return None
            
        xmin = min(start_world[0], end_world[0])
        xmax = max(start_world[0], end_world[0])
        ymin = min(start_world[1], end_world[1])
        ymax = max(start_world[1], end_world[1])
        
        return (xmin, ymin, xmax, ymax)
        
    def clear_selection(self):
        """Clear the current selection."""
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.selected_bbox_world = None  # Also clear persistent selection
        self.update()
        self.selectionChanged.emit(0, 0, 0, 0)
        
    def world_bbox_to_screen_rect(self, bbox_world):
        """Convert world bbox to screen rectangle for drawing."""
        if bbox_world is None:
            return None
        
        # CRITICAL: Ensure pixmap is valid before converting
        if self.current_pixmap.isNull() or not self.map_loaded:
            return None
            
        xmin, ymin, xmax, ymax = bbox_world
        
        # Use _requested_extent if available (matches what's displayed), otherwise use extent
        # This ensures coordinate conversion uses the correct extent
        conversion_extent = self._requested_extent if (hasattr(self, '_requested_extent') and self._requested_extent is not None) else self.extent
        
        # Use conversion_extent directly for coordinate conversion
        # Store original values but don't modify self.extent (world_to_screen will use conversion_extent via parameter)
        original_extent = self.extent
        original_requested = getattr(self, '_requested_extent', None)
        
        # Temporarily set extent for world_to_screen to use
        self.extent = conversion_extent
        if not hasattr(self, '_requested_extent'):
            self._requested_extent = None
        self._requested_extent = conversion_extent
        
        try:
            # Convert corners to screen coordinates
            # world_to_screen will use self._requested_extent which we just set to conversion_extent
            top_left = self.world_to_screen(xmin, ymax)
            bottom_right = self.world_to_screen(xmax, ymin)
            
            if top_left is not None and bottom_right is not None:
                screen_rect = QRect(top_left, bottom_right)
                return screen_rect
        finally:
            # Restore original extent
            self.extent = original_extent
            if hasattr(self, '_requested_extent'):
                self._requested_extent = original_requested
        
        return None
        
    def mousePressEvent(self, event):
        """Handle mouse press for selection or panning."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Left button for selection only
            # Clear previous selection when starting a new one
            self.clear_selection()
            self.selection_start = event.position().toPoint()
            self.selection_end = self.selection_start
            self.is_selecting = True
            self.update()
        elif event.button() == Qt.MouseButton.MiddleButton:
            # Middle button for panning
            self.is_panning = True
            self.pan_start = event.position().toPoint()
            self.pan_origin = event.position().toPoint()  # Store original position for pan line
            self.pan_end = event.position().toPoint()  # Initialize pan_end
            self.update()
            
    def mouseMoveEvent(self, event):
        """Handle mouse move for selection or panning."""
        if self.is_selecting:
            self.selection_end = event.position().toPoint()
            bbox = self.get_selection_bbox()
            if bbox:
                self.selectionChanged.emit(*bbox)
            self.update()
        elif self.is_panning and self.pan_start:
            # Calculate pan delta
            current_pos = event.position().toPoint()
            self.pan_end = current_pos  # Track current position for pan line
            delta = current_pos - self.pan_start
            
            # Convert screen delta to world delta
            pixmap_rect = self.current_pixmap.rect()
            pixmap_rect.moveCenter(self.rect().center())
            
            if not pixmap_rect.isNull():
                xmin, ymin, xmax, ymax = self.extent
                world_width = xmax - xmin
                world_height = ymax - ymin
                
                rel_delta_x = -delta.x() / pixmap_rect.width() * world_width
                rel_delta_y = delta.y() / pixmap_rect.height() * world_height
                
                # Update extent
                self.extent = (
                    xmin + rel_delta_x,
                    ymin + rel_delta_y,
                    xmax + rel_delta_x,
                    ymax + rel_delta_y
                )
                # Update _requested_extent to match the new extent for accurate coordinate conversion
                self._requested_extent = self.extent
                self.pan_start = current_pos
                self.clear_selection()
                
                # Update display to show pan line
                self.update()
                
                # Debounce: Cancel any pending load and schedule a new one after a delay
                if self._load_timer:
                    self._load_timer.stop()
                
                from PyQt6.QtCore import QTimer
                self._load_timer = QTimer()
                self._load_timer.setSingleShot(True)
                self._load_timer.timeout.connect(self.load_map)
                self._load_timer.start(300)  # Wait 300ms before loading (debounce)
            
    def mouseReleaseEvent(self, event):
        """Handle mouse release for selection or panning."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_selecting:
                self.selection_end = event.position().toPoint()
                self.is_selecting = False
                bbox = self.get_selection_bbox()
                if bbox:
                    # Store the selected bbox in world coordinates for persistent display
                    self.selected_bbox_world = bbox
                    self.selectionChanged.emit(*bbox)
                    # Emit selection completed signal for zooming
                    self.selectionCompleted.emit(*bbox)
                # Clear the active selection rectangle (red dashed line)
                self.selection_start = None
                self.selection_end = None
                self.update()
            elif self.is_panning:
                self.is_panning = False
                self.pan_start = None
                self.pan_origin = None
                self.pan_end = None
                self.update()  # Clear pan line
        elif event.button() == Qt.MouseButton.MiddleButton and self.is_panning:
            self.is_panning = False
            self.pan_start = None
            self.pan_origin = None
            self.pan_end = None
            self.update()  # Clear pan line
            
    def wheelEvent(self, event):
        """Handle mouse wheel for zooming."""
        if self.current_pixmap.isNull():
            return
            
        # Get center of widget in world coordinates
        widget_center = QPoint(self.width() // 2, self.height() // 2)
        world_pos = self.screen_to_world(widget_center)
        
        if not world_pos:
            # Fallback: use center of extent if screen_to_world fails
            xmin, ymin, xmax, ymax = self.extent
            center_x = (xmin + xmax) / 2
            center_y = (ymin + ymax) / 2
            world_pos = (center_x, center_y)
            
        # Calculate zoom factor
        zoom_factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        
        # Calculate new extent centered on window center
        xmin, ymin, xmax, ymax = self.extent
        width = (xmax - xmin) / zoom_factor
        height = (ymax - ymin) / zoom_factor
        
        center_x, center_y = world_pos
        new_xmin = center_x - width / 2
        new_xmax = center_x + width / 2
        new_ymin = center_y - height / 2
        new_ymax = center_y + height / 2
        
        self.extent = (new_xmin, new_ymin, new_xmax, new_ymax)
        # Update _requested_extent to match the new extent for accurate coordinate conversion
        self._requested_extent = self.extent
        self.clear_selection()
        
        # Debounce: Cancel any pending load and schedule a new one after a delay
        if self._load_timer:
            self._load_timer.stop()
        
        from PyQt6.QtCore import QTimer
        self._load_timer = QTimer()
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(self.load_map)
        self._load_timer.start(300)  # Wait 300ms before loading (debounce)
        
    def resizeEvent(self, event):
        """Handle widget resize."""
        super().resizeEvent(event)
        # Don't scale pixmap here - let the map loading handle it properly
        # Scaling here interferes with coordinate conversion and causes selection box size issues
        # The map will be reloaded by _refresh_map_on_resize in main.py
            
    def paintEvent(self, event):
        """Paint the map and selection rectangle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        widget_rect = self.rect()
        
        # Draw basemap first (if available) - bottom layer
        # Draw if show_basemap is True OR if land_display_url is set (land layer for GEBCO)
        should_draw_basemap = (self.show_basemap or self.land_display_url) and not self.basemap_pixmap.isNull()
        if should_draw_basemap:
            basemap_rect = self.basemap_pixmap.rect()
            x = (widget_rect.width() - basemap_rect.width()) // 2
            y = (widget_rect.height() - basemap_rect.height()) // 2
            target_rect = QRect(x, y, basemap_rect.width(), basemap_rect.height())
            painter.drawPixmap(target_rect, self.basemap_pixmap)
        else:
            # Fill background with black if no basemap (nodata areas will show as black)
            painter.fillRect(self.rect(), QColor(0, 0, 0))
        
        # Draw hillshade layer (if available) - middle layer (underlay) at full opacity
        if self.show_hillshade and not self.hillshade_pixmap.isNull():
            hillshade_rect = self.hillshade_pixmap.rect()
            x = (widget_rect.width() - hillshade_rect.width()) // 2
            y = (widget_rect.height() - hillshade_rect.height()) // 2
            target_rect = QRect(x, y, hillshade_rect.width(), hillshade_rect.height())
            # Ensure full opacity for hillshade (opacity only affects top layer)
            painter.setOpacity(1.0)
            painter.drawPixmap(target_rect, self.hillshade_pixmap)
        
        # Draw bathymetry layer on top (with opacity and/or blend mode) - top layer
        # Only this layer uses the opacity setting and blend mode
        if not self.current_pixmap.isNull():
            pixmap_rect = self.current_pixmap.rect()
            
            # Center the pixmap in the widget
            x = (widget_rect.width() - pixmap_rect.width()) // 2
            y = (widget_rect.height() - pixmap_rect.height()) // 2
            target_rect = QRect(x, y, pixmap_rect.width(), pixmap_rect.height())
            
            # Set blend mode if enabled (Multiply mode for natural blending with hillshade)
            # Multiply darkens the colors while preserving hillshade detail, better than Overlay for cartography
            if self.use_blend:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            
            # Draw with opacity (only the top layer uses opacity)
            painter.setOpacity(self.bathymetry_opacity)
            painter.drawPixmap(target_rect, self.current_pixmap)
            
            # Reset opacity and composition mode for subsequent drawing
            painter.setOpacity(1.0)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        elif not self.show_basemap:
            # Draw placeholder only if basemap is not shown
            painter.fillRect(self.rect(), QColor(0, 0, 0))  # Black background
            status_text = "Loading map..."
            if hasattr(self, 'loader') and self.loader and self.loader.isRunning():
                status_text = "Loading map..."
            else:
                status_text = "No map data available"
            painter.setPen(QColor(255, 255, 255))  # White text on black background
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, status_text)
            
        # Draw selection rectangle (always on top)
        # First draw the persistent selected bbox if it exists
        # CRITICAL: Only draw if pixmap is loaded and valid to avoid drawing with stale data during resize
        # Also ensure pixmap size matches widget size (or is being scaled correctly)
        if self.selected_bbox_world and self.map_loaded and not self.current_pixmap.isNull():
            # Only draw if pixmap is valid and has been loaded
            # Check that pixmap size is reasonable (not stale)
            pixmap_width = self.current_pixmap.width()
            pixmap_height = self.current_pixmap.height()
            widget_width = self.width()
            widget_height = self.height()
            
            # Only draw if pixmap dimensions are valid (greater than 0)
            if pixmap_width > 0 and pixmap_height > 0:
                bbox_screen = self.world_bbox_to_screen_rect(self.selected_bbox_world)
                if bbox_screen:
                    # Determine if this is the dataset bounds (service extent) or a user selection
                    is_dataset_bounds = False
                    if hasattr(self, 'service_extent') and self.service_extent is not None:
                        # Compare with tolerance (degrees for GCS)
                        tol = 1e-5
                        se = self.service_extent
                        sb = self.selected_bbox_world
                        if (abs(se[0] - sb[0]) < tol and abs(se[1] - sb[1]) < tol and
                            abs(se[2] - sb[2]) < tol and abs(se[3] - sb[3]) < tol):
                            is_dataset_bounds = True
                    
                    if is_dataset_bounds:
                        # Dataset bounds - use yellow dashed line (no fill)
                        pen = QPen(QColor(255, 255, 0), 2, Qt.PenStyle.DashLine)  # Yellow dashed line
                    elif self.selection_is_valid:
                        # User selection - use green dashed line (no fill)
                        pen = QPen(QColor(0, 255, 0), 2, Qt.PenStyle.DashLine)  # Green dashed line
                    else:
                        # Selection too large - use red dashed line (no fill)
                        pen = QPen(QColor(255, 0, 0), 2, Qt.PenStyle.DashLine)  # Red dashed line
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)  # No fill - outline only
                    painter.drawRect(bbox_screen)
        
        # Draw active selection rectangle (while dragging)
        if self.selection_start and self.selection_end:
            selection_rect = QRect(self.selection_start, self.selection_end).normalized()
            pen = QPen(QColor(0, 255, 0), 2, Qt.PenStyle.DashLine)  # Green dashed line
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)  # No fill - outline only
            painter.drawRect(selection_rect)
        
        # Draw pan line (red line showing pan direction and distance)
        if self.is_panning and self.pan_origin and self.pan_end:
            pen = QPen(QColor(255, 0, 0), 2, Qt.PenStyle.DashLine)  # Red dashed line
            painter.setPen(pen)
            painter.drawLine(self.pan_origin, self.pan_end)
        
        # Draw legend in upper left corner
        self._draw_legend(painter)
    
    def _draw_legend(self, painter):
        """Draw a legend in the upper left corner showing box color meanings."""
        if not self.map_loaded or not self.show_legend:
            return  # Don't draw legend until map is loaded or if legend is disabled
        
        # Legend configuration
        margin = 10
        padding = 8
        line_height = 20
        line_width = 30
        legend_width = 150
        # Height calculation:
        # - Top padding: padding
        # - Item 1: line_height
        # - Item 2: line_height (text drawn at item_y + line_height - 4)
        # - Bottom padding: padding + 4 (extra space for text)
        # Total: 2*padding + 2*line_height + 4
        legend_height = padding * 2 + line_height * 2 + 4
        
        # Position in upper left corner
        x = margin
        y = margin
        
        # Draw semi-transparent background
        legend_rect = QRect(x, y, legend_width, legend_height)
        bg_color = QColor(0, 0, 0, 140)  # Black with 140/255 opacity (~55% opaque)
        painter.fillRect(legend_rect, bg_color)
        
        # Draw border
        border_pen = QPen(QColor(255, 255, 255), 1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(legend_rect)
        
        # Draw legend items (only Dataset Bounds and Area of Interest)
        items = [
            (QColor(255, 255, 0), "Dataset Bounds"),
            (QColor(0, 255, 0), "Area of Interest")
        ]
        
        start_y = y + padding
        for i, (color, label) in enumerate(items):
            item_y = start_y + i * line_height
            
            # Draw colored line sample (dashed)
            line_x = x + padding
            line_y = item_y + line_height // 2
            pen = QPen(color, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(line_x, line_y, line_x + line_width, line_y)
            
            # Draw label (text baseline at item_y + line_height - 4 to account for text height)
            painter.setPen(QColor(255, 255, 255))
            text_x = line_x + line_width + 8
            painter.drawText(text_x, item_y + line_height - 4, label)

