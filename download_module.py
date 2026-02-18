"""
Module for downloading bathymetry data from ArcGIS ImageServer and creating GeoTIFF files.
"""
import requests
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from io import BytesIO
from PIL import Image
import pyproj
from PyQt6.QtCore import QThread, pyqtSignal


class BathymetryDownloader(QThread):
    """Thread for downloading bathymetry data and creating GeoTIFF."""
    
    progress = pyqtSignal(int)  # Progress percentage
    status = pyqtSignal(str)  # Status message
    finished = pyqtSignal(str)  # Output file path
    error = pyqtSignal(str)  # Error message
    
    def __init__(self, base_url, bbox, output_path, output_crs="EPSG:3857", 
                 pixel_size=None, max_size=14000, use_tile_download=False,
                 bbox_in_4326=False, pixel_size_degrees=None):
        super().__init__()
        self.base_url = base_url
        self.bbox = bbox  # (xmin, ymin, xmax, ymax) in EPSG:3857 or 4326 when bbox_in_4326
        self.output_path = output_path
        self.output_crs = output_crs
        self.pixel_size = pixel_size  # meters, or None; ignored when pixel_size_degrees is set
        self.bbox_in_4326 = bbox_in_4326
        self.pixel_size_degrees = pixel_size_degrees  # for services in 4326 (e.g. GEBCO)
        self.max_size = max_size
        self.use_tile_download = use_tile_download
        self.tile_overlap = 5
        self.tile_max_size = 2000
        self.cancelled = False
        
    def cancel(self):
        """Cancel the download."""
        self.cancelled = True
        
    def run(self):
        """Download data and create GeoTIFF."""
        try:
            xmin, ymin, xmax, ymax = self.bbox
            
            # Determine output size
            if self.bbox_in_4326 and self.pixel_size_degrees is not None:
                # Bbox is (lon_min, lat_min, lon_max, lat_max) in degrees
                width = int((xmax - xmin) / self.pixel_size_degrees)
                height = int((ymax - ymin) / abs(self.pixel_size_degrees))
            elif self.pixel_size:
                width = int((xmax - xmin) / self.pixel_size)
                height = int((ymax - ymin) / self.pixel_size)
            else:
                width = int((xmax - xmin) / 4.0)
                height = int((ymax - ymin) / 4.0)
                
            # Check if size exceeds maximum only if tiling is disabled
            # If tiling is enabled, we can handle any size
            if not self.use_tile_download and (width > self.max_size or height > self.max_size):
                error_msg = (
                    f"Selected area exceeds maximum download size ({self.max_size} x {self.max_size} pixels).\n"
                    f"Requested size: {width} x {height} pixels.\n\n"
                    f"Please either:\n"
                    f"1. Enable Tile Download option, or\n"
                    f"2. Select a smaller area, or\n"
                    f"3. Increase the cell size (currently {self.pixel_size if self.pixel_size else 4}m)"
                )
                self.error.emit(error_msg)
                return
            
            # Check if tiling is needed
            needs_tiling = self.use_tile_download and (width > self.tile_max_size or height > self.tile_max_size)
            
            if needs_tiling:
                # Use tiled download
                result = self._download_tiled(xmin, ymin, xmax, ymax, width, height)
                if result is None or result[0] is None:
                    return  # Error already emitted
                img_array, source_nodata, transform, downloaded_crs = result
            else:
                # Single download
                self.status.emit(f"Requesting data: {width}x{height} pixels...")
                self.progress.emit(10)
                
                if self.cancelled:
                    return
                    
                # Download raw data (no raster function for raw values)
                # Try multiple approaches to get raw data
                
                url = f"{self.base_url}/exportImage"
                
                # First, try to get raw TIFF data
                params = {
                    "bbox": f"{xmin},{ymin},{xmax},{ymax}",
                    "size": f"{width},{height}",
                    "format": "tiff",
                    "f": "image",
                    "noData": "true",
                    "interpolation": "RSP_BilinearInterpolation"
                }
                
                # Don't specify rasterFunction to get raw values
                # The service should return raw F32 values
                
                self.progress.emit(30)
                self.status.emit("Downloading data...")
                
                if self.cancelled:
                    return
                    
                img_array = None
                source_nodata = None
                transform = None
                downloaded_crs = None
                
                try:
                    response = requests.get(url, params=params, timeout=300, stream=True)
                    
                    # Check for HTTP errors before processing
                    if response.status_code == 500:
                        # Server error - provide helpful message
                        error_msg = (
                            f"Server error (500) from REST endpoint.\n\n"
                            f"The server is unable to process this request. This may be due to:\n"
                            f"  - Requested area is too large\n"
                            f"  - Server is temporarily unavailable\n"
                            f"  - Request parameters are invalid\n\n"
                            f"Try:\n"
                            f"  - Selecting a smaller area\n"
                            f"  - Using a larger cell size (8m or 16m)\n"
                            f"  - Waiting a few moments and trying again\n\n"
                            f"Requested size: {width}x{height} pixels"
                        )
                        self.error.emit(error_msg)
                        return
                    
                    response.raise_for_status()
                    
                    # Check if we got a TIFF
                    content_type = response.headers.get('Content-Type', '')
                    if 'tiff' in content_type.lower() or response.content[:4] == b'II*\x00' or response.content[:4] == b'MM\x00*':
                        # We got a TIFF, try to read it with rasterio
                        try:
                            with rasterio.open(BytesIO(response.content)) as src:
                                img_array = src.read(1).astype(np.float32)
                                # Preserve NoData value from source
                                if src.nodata is not None:
                                    source_nodata = float(src.nodata)
                                    # Mask NoData values
                                    img_array = np.where(img_array == source_nodata, np.nan, img_array)
                                # Use the transform and CRS from the downloaded TIFF if available
                                if hasattr(src, 'transform') and src.transform:
                                    transform = src.transform
                                if hasattr(src, 'crs') and src.crs:
                                    downloaded_crs = src.crs
                        except Exception as e:
                            self.status.emit(f"Could not read TIFF with rasterio: {e}. Trying PIL...")
                            # Fall back to PIL
                            img = Image.open(BytesIO(response.content))
                            img_array = np.array(img, dtype=np.float32)
                    else:
                        # Not a TIFF, try as image
                        img = Image.open(BytesIO(response.content))
                        if img.mode in ('RGB', 'RGBA'):
                            # If we got a colored image, we might need to use pixelBlock
                            # For now, convert to grayscale and warn
                            self.status.emit("Warning: Received RGB image. Using grayscale conversion.")
                            img_array = np.array(img.convert('L'), dtype=np.float32)
                        else:
                            img_array = np.array(img, dtype=np.float32)
                        
                except requests.exceptions.HTTPError as e:
                    # HTTP error (4xx, 5xx)
                    if hasattr(e.response, 'status_code'):
                        if e.response.status_code == 500:
                            error_msg = (
                                f"Server error (500) from REST endpoint.\n\n"
                                f"The server is unable to process this request. This may be due to:\n"
                                f"  - Requested area is too large\n"
                                f"  - Server is temporarily unavailable\n"
                                f"  - Request parameters are invalid\n\n"
                                f"Try:\n"
                                f"  - Selecting a smaller area\n"
                                f"  - Using a larger cell size (8m or 16m)\n"
                                f"  - Waiting a few moments and trying again\n\n"
                                f"Requested size: {width}x{height} pixels"
                            )
                        else:
                            error_msg = f"HTTP error {e.response.status_code} from REST endpoint: {str(e)}"
                    else:
                        error_msg = f"HTTP error from REST endpoint: {str(e)}"
                    self.error.emit(error_msg)
                    return
                except requests.exceptions.RequestException as e:
                    # Connection or network error
                    error_msg = f"Network error connecting to REST endpoint: {str(e)}"
                    self.error.emit(error_msg)
                    return
                except Exception as e:
                    self.status.emit(f"Error with TIFF format: {e}. Trying PNG format...")
                    # Fall back to PNG
                    try:
                        params["format"] = "png"
                        response = requests.get(url, params=params, timeout=300, stream=True)
                        response.raise_for_status()
                        
                        img = Image.open(BytesIO(response.content))
                        if img.mode in ('RGB', 'RGBA'):
                            self.status.emit("Warning: Received RGB PNG. Using grayscale conversion.")
                            img_array = np.array(img.convert('L'), dtype=np.float32)
                        else:
                            img_array = np.array(img, dtype=np.float32)
                    except Exception as e2:
                        error_msg = f"Failed to download data: {str(e2)}"
                        self.error.emit(error_msg)
                        return
                
            # For now, if we got a PNG, we don't have the actual bathymetry values
            # We need to use the pixelBlock operation or exportImage with proper format
            # Let's try a different approach - use exportImage with pixelType and no raster function
            
            self.progress.emit(50)
            self.status.emit("Processing data...")
            
            if self.cancelled:
                return
                
            # Try to get actual pixel values using pixelBlock or different export parameters
            # For now, we'll create the GeoTIFF with what we have
            # In a production version, you'd want to use the pixelBlock operation
            
            # Ensure img_array is defined and not None
            if img_array is None:
                error_msg = "Failed to load image data from server response"
                self.error.emit(error_msg)
                return
            
            # Determine CRS and bbox
            transform = None
            if self.bbox_in_4326 and self.output_crs == "EPSG:4326":
                # Data and bbox already in WGS84; no reprojection
                crs = CRS.from_epsg(4326)
                output_bbox = self.bbox
            else:
                source_crs = CRS.from_epsg(3857)
                if self.output_crs == "EPSG:3857":
                    crs = CRS.from_epsg(3857)
                    output_bbox = self.bbox
                elif self.output_crs == "EPSG:4326":
                    transformer = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
                    lon_min, lat_min = transformer.transform(xmin, ymin)
                    lon_max, lat_max = transformer.transform(xmax, ymax)
                    output_bbox = (lon_min, lat_min, lon_max, lat_max)
                    crs = CRS.from_epsg(4326)
                    self.status.emit("Reprojecting to WGS84...")
                    from rasterio.warp import reproject, Resampling, calculate_default_transform
                    transform, output_width, output_height = calculate_default_transform(
                        source_crs, crs, width, height, *self.bbox
                    )
                    reprojected_array = np.zeros((output_height, output_width), dtype=img_array.dtype)
                    source_transform = from_bounds(*self.bbox, width, height)
                    reproject(
                        source=img_array,
                        destination=reprojected_array,
                        src_transform=source_transform,
                        src_crs=source_crs,
                        dst_transform=transform,
                        dst_crs=crs,
                        resampling=Resampling.bilinear
                    )
                    img_array = reprojected_array
                    width = output_width
                    height = output_height
                else:
                    crs = CRS.from_string(self.output_crs)
                    output_bbox = self.bbox
                
            self.progress.emit(70)
            self.status.emit("Creating GeoTIFF...")
            
            if self.cancelled:
                return
                
            # Create transform if not already set from reprojection
            if transform is None:
                transform = from_bounds(*output_bbox, width, height)
            
            # Ensure array is 2D
            if len(img_array.shape) == 3:
                img_array = img_array[:, :, 0]
            elif len(img_array.shape) == 2:
                pass
            else:
                raise ValueError(f"Unexpected array shape: {img_array.shape}")
            
            # Handle NoData values
            # Determine appropriate NoData value
            nodata_value = -9999.0  # Default for bathymetry
            
            # Use source nodata if available
            if 'source_nodata' in locals() and source_nodata is not None:
                nodata_value = source_nodata
            else:
                # Check if we have actual data or if this is a visualization image
                # If the array has values that look like visualization (0-255 range), we might need different handling
                if img_array.dtype == np.uint8 or (img_array.max() <= 255 and img_array.min() >= 0):
                    # This might be a visualization image, not raw bathymetry
                    self.status.emit("Warning: Received visualization image. NoData may not be accurate.")
                    nodata_value = 0.0
                # else: nodata_value already set to -9999.0 above (default for bathymetry)
            
            # Convert NaN values to the nodata value for writing
            # But keep them as NaN in memory for now
            img_array_for_write = img_array.copy()
            if np.any(np.isnan(img_array_for_write)):
                img_array_for_write = np.nan_to_num(img_array_for_write, nan=nodata_value)
            
            # Ensure we're using float32 for bathymetry data
            if img_array_for_write.dtype != np.float32:
                img_array_for_write = img_array_for_write.astype(np.float32)
                
            # Write GeoTIFF with NoData value
            with rasterio.open(
                self.output_path,
                'w',
                driver='GTiff',
                height=height,
                width=width,
                count=1,
                dtype=img_array_for_write.dtype,
                crs=crs,
                transform=transform,
                compress='lzw',
                nodata=nodata_value
            ) as dst:
                dst.write(img_array_for_write, 1)
                self.status.emit(f"GeoTIFF written with NoData value: {nodata_value}")
                
            self.progress.emit(100)
            self.status.emit(f"GeoTIFF saved to: {self.output_path}")
            self.finished.emit(self.output_path)
            
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _download_tiled(self, xmin, ymin, xmax, ymax, total_width, total_height):
        """Download data in tiles and reassemble.
        
        Returns:
            tuple: (img_array, source_nodata, transform, downloaded_crs)
        """
        # Calculate tile grid
        tiles_x = int(np.ceil(total_width / self.tile_max_size))
        tiles_y = int(np.ceil(total_height / self.tile_max_size))
        total_tiles = tiles_x * tiles_y
        
        self.status.emit(f"Downloading {total_tiles} tiles ({tiles_x}x{tiles_y})...")
        self.progress.emit(10)
        
        # Calculate pixel size in world coordinates
        pixel_size_x = (xmax - xmin) / total_width
        pixel_size_y = (ymax - ymin) / total_height
        
        # Initialize output array
        img_array = np.full((total_height, total_width), np.nan, dtype=np.float32)
        source_nodata = None
        transform = None
        downloaded_crs = None
        
        tile_num = 0
        
        for tile_y in range(tiles_y):
            for tile_x in range(tiles_x):
                if self.cancelled:
                    return None, None, None, None
                
                tile_num += 1
                progress = 10 + int(80 * tile_num / total_tiles)
                self.progress.emit(progress)
                self.status.emit(f"Downloading tile {tile_num}/{total_tiles}...")
                
                # Calculate tile bounds in pixels
                # Add overlap to ensure no gaps
                tile_start_x = tile_x * self.tile_max_size
                tile_start_y = tile_y * self.tile_max_size
                tile_end_x = min(tile_start_x + self.tile_max_size, total_width)
                tile_end_y = min(tile_start_y + self.tile_max_size, total_height)
                
                # Add overlap (extend bounds)
                overlap_start_x = max(0, tile_start_x - self.tile_overlap)
                overlap_start_y = max(0, tile_start_y - self.tile_overlap)
                overlap_end_x = min(total_width, tile_end_x + self.tile_overlap)
                overlap_end_y = min(total_height, tile_end_y + self.tile_overlap)
                
                # Calculate world bounds for this tile
                tile_xmin = xmin + overlap_start_x * pixel_size_x
                tile_ymin = ymin + (total_height - overlap_end_y) * pixel_size_y  # Y is inverted
                tile_xmax = xmin + overlap_end_x * pixel_size_x
                tile_ymax = ymin + (total_height - overlap_start_y) * pixel_size_y
                
                tile_width = overlap_end_x - overlap_start_x
                tile_height = overlap_end_y - overlap_start_y
                
                # Download this tile
                url = f"{self.base_url}/exportImage"
                params = {
                    "bbox": f"{tile_xmin},{tile_ymin},{tile_xmax},{tile_ymax}",
                    "size": f"{tile_width},{tile_height}",
                    "format": "tiff",
                    "f": "image",
                    "noData": "true",
                    "interpolation": "RSP_BilinearInterpolation"
                }
                
                try:
                    response = requests.get(url, params=params, timeout=300, stream=True)
                    
                    if response.status_code == 500:
                        error_msg = f"Server error (500) downloading tile {tile_num}/{total_tiles}"
                        self.error.emit(error_msg)
                        return None, None, None, None
                    
                    response.raise_for_status()
                    
                    # Read tile data
                    tile_array = None
                    content_type = response.headers.get('Content-Type', '')
                    
                    if 'tiff' in content_type.lower() or response.content[:4] == b'II*\x00' or response.content[:4] == b'MM\x00*':
                        try:
                            with rasterio.open(BytesIO(response.content)) as src:
                                tile_array = src.read(1).astype(np.float32)
                                if src.nodata is not None and source_nodata is None:
                                    source_nodata = float(src.nodata)
                                tile_array = np.where(tile_array == src.nodata, np.nan, tile_array)
                                if transform is None and hasattr(src, 'transform') and src.transform:
                                    transform = src.transform
                                if downloaded_crs is None and hasattr(src, 'crs') and src.crs:
                                    downloaded_crs = src.crs
                        except Exception:
                            img = Image.open(BytesIO(response.content))
                            tile_array = np.array(img, dtype=np.float32)
                    else:
                        img = Image.open(BytesIO(response.content))
                        if img.mode in ('RGB', 'RGBA'):
                            tile_array = np.array(img.convert('L'), dtype=np.float32)
                        else:
                            tile_array = np.array(img, dtype=np.float32)
                    
                    # Determine where to place this tile in the output array
                    # Account for overlap - use the non-overlap region for placement
                    output_start_x = tile_start_x
                    output_start_y = tile_start_y
                    output_end_x = tile_end_x
                    output_end_y = tile_end_y
                    
                    # Extract the non-overlap region from the tile
                    tile_offset_x = tile_start_x - overlap_start_x
                    tile_offset_y = tile_start_y - overlap_start_y
                    tile_region_x = tile_offset_x
                    tile_region_y = tile_offset_y
                    tile_region_width = output_end_x - output_start_x
                    tile_region_height = output_end_y - output_start_y
                    
                    # Place tile data into output array
                    tile_data = tile_array[tile_region_y:tile_region_y + tile_region_height,
                                          tile_region_x:tile_region_x + tile_region_width]
                    
                    # Handle overlap regions - use average or prefer non-NaN values
                    output_region = img_array[output_start_y:output_end_y, output_start_x:output_end_x]
                    
                    # Combine: prefer non-NaN values, average if both have values
                    mask_both = ~np.isnan(output_region) & ~np.isnan(tile_data)
                    mask_new_only = np.isnan(output_region) & ~np.isnan(tile_data)
                    mask_old_only = ~np.isnan(output_region) & np.isnan(tile_data)
                    
                    # Average overlapping regions
                    combined = output_region.copy()
                    combined[mask_both] = (output_region[mask_both] + tile_data[mask_both]) / 2.0
                    combined[mask_new_only] = tile_data[mask_new_only]
                    # mask_old_only: keep existing values
                    
                    img_array[output_start_y:output_end_y, output_start_x:output_end_x] = combined
                    
                except Exception as e:
                    error_msg = f"Error downloading tile {tile_num}/{total_tiles}: {str(e)}"
                    self.error.emit(error_msg)
                    return None, None, None, None
        
        self.progress.emit(90)
        self.status.emit("Reassembling tiles...")
        
        return img_array, source_nodata, transform, downloaded_crs

