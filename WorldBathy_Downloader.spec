# -*- mode: python ; coding: utf-8 -*-

# Extract version from main.py
import re
import os

# Bundle pyproj data (proj.db etc.) so the frozen exe can find CRS data
try:
    import pyproj
    _proj_data_dir = pyproj.datadir.get_data_dir()
    if _proj_data_dir and os.path.isdir(_proj_data_dir):
        _proj_datas = [(_proj_data_dir, 'proj')]
    else:
        _proj_datas = []
except Exception:
    _proj_datas = []

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()
    # Find uncommented __version__ line (not starting with #)
    lines = content.split('\n')
    version = "unknown"
    for line in lines:
        stripped = line.strip()
        # Skip commented lines
        if stripped.startswith('#'):
            continue
        # Match __version__ = "version"
        version_match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", stripped)
        if version_match:
            version = version_match.group(1)
            break

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=_proj_datas,
    hiddenimports=[
        'rasterio',
        'rasterio.sample',
        'rasterio.vrt',
        'rasterio.warp',
        'rasterio.crs',
        'rasterio.transform',
        'rasterio.windows',
        'rasterio.env',
        'rasterio.io',
        'rasterio.session',
        'rasterio.dtypes',
        'rasterio.profiles',
        'rasterio.coords',
        'rasterio.errors',
        'rasterio.enums',
        'rasterio.drivers',
        'rasterio._path',
        'rasterio._base',
        'rasterio._err',
        'rasterio._io',
        'rasterio._version',
        'rasterio._vsiopener',
        'rasterio._features',
        'rasterio._warp',
        'numpy',
        'requests',
        'pyproj',
        'pyproj.datadir',
        'PIL',
        'PIL.Image',
        'json',
        'datetime',
        'io',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=f'WorldBathy_Downloader_v{version}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window (GUI application)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='media/CCOM.ico',  # Use the CCOM.ico icon
)
