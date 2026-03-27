# Vendor Management System

A desktop application for managing vendors, bills, and payments with OCR receipt scanning capabilities.

## Features
- User authentication with bcrypt encryption
- Vendor management with billing cycles and payment methods
- Bill tracking with status management (Pending, Paid, Overdue)
- OCR receipt scanning using Tesseract
- Dark mode interface with CustomTkinter
- SQLite database for local storage

## Requirements
- Python 3.8+
- Tesseract OCR (required for scanning feature)

## Installation

### Windows
1. Download and install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
2. Add Tesseract to your system PATH
3. Run `install.bat`
4. Launch with `python vendor_manager.py` or double-click the generated `.exe`

### macOS
1. Install Homebrew if not present: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
2. Run `chmod +x install.sh && ./install.sh`
3. Launch with `python3 vendor_manager.py`

### Linux (Ubuntu/Debian)
1. Run `chmod +x install.sh && sudo ./install.sh`
2. Launch with `python3 vendor_manager.py`

## Building Executables
```bash
pip install pyinstaller
pyinstaller --onefile --windowed vendor_manager.spec-*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['vendor_manager.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['PIL', 'cv2', 'pytesseract'],
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
    name='VendorManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)