@echo off
echo Installing Vendor Manager dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Checking for Tesseract OCR...
where tesseract >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Tesseract not found. Download from: https://github.com/UB-Mannheim/tesseract/wiki
    echo After installation, add Tesseract to your PATH and restart this script.
    pause
    exit /b 1
)

echo.
echo Dependencies installed successfully!
echo Run: python vendor_manager.py
pause