# Vendor Manager Installation Guide

This guide installs Vendor Manager on Windows, macOS, and Linux, including OCR support with Tesseract.

## Quick Start

Use the bootstrap script for your operating system from the project folder.

### Windows

```powershell
PowerShell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap_windows.ps1
```

### macOS

```bash
bash ./bootstrap_macos.sh
```

### Linux

```bash
bash ./bootstrap_linux.sh
```

## Optional Flags

You can pass flags through to the installer:

- `--run-app` starts the app after setup.
- `--skip-system` skips OS-level installs (Python/Tesseract package manager steps).

Examples:

### Windows with app launch

```powershell
PowerShell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap_windows.ps1 -RunApp
```

### macOS without system package installs

```bash
bash ./bootstrap_macos.sh --skip-system
```

### Linux with app launch

```bash
bash ./bootstrap_linux.sh --run-app
```

## Manual Install (Fallback)

Use this if bootstrap scripts are blocked by policy.

1. Install Python 3.10+.
2. Install Tesseract OCR using your package manager.
3. Create and use a virtual environment.
4. Install Python packages from `requirements.txt`.
5. Run `vendor_manager.py`.

### Windows manual fallback

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe .\vendor_manager.py
```

### macOS manual fallback

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r ./requirements.txt
./.venv/bin/python ./vendor_manager.py
```

### Linux manual fallback

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r ./requirements.txt
./.venv/bin/python ./vendor_manager.py
```

## Tesseract Installation Notes

If OCR scanning fails, Tesseract is usually missing or not in PATH.

### Windows

- Preferred package managers:
  - `winget install -e --id UB-Mannheim.TesseractOCR`
  - `choco install tesseract -y`
- Manual installer: https://github.com/UB-Mannheim/tesseract/wiki
- After install, open a new terminal and verify:

```powershell
tesseract --version
```

### macOS

```bash
brew install tesseract
tesseract --version
```

### Linux

Common options:

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install -y tesseract-ocr

# Fedora/RHEL
sudo dnf install -y tesseract

# Arch
sudo pacman -S --noconfirm tesseract
```

Verify:

```bash
tesseract --version
```

## Troubleshooting

### 1) "python" or "python3" not found

- Use the bootstrap scripts; they try to install Python automatically.
- If install succeeded but command still fails, restart terminal/session.

### 2) OCR button shows Tesseract not found

- Install Tesseract from your OS package manager.
- Confirm with `tesseract --version` in a fresh terminal.

### 3) Script policy blocks PowerShell script on Windows

Run with execution policy bypass for this process only:

```powershell
PowerShell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap_windows.ps1
```

### 4) Permission errors on Linux/macOS package installs

- Re-run with a user that has sudo privileges.
- Ensure `sudo` is available on the machine.

### 5) Virtual environment issues

Delete `.venv` and rerun bootstrap:

```bash
rm -rf .venv
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force .\.venv
```
