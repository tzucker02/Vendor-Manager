#!/bin/bash
echo "Installing Vendor Manager dependencies..."
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt

echo ""
echo "Checking for Tesseract OCR..."
if ! command -v tesseract &> /dev/null; then
    echo "Tesseract not found. Installing via Homebrew..."
    if ! command -v brew &> /dev/null; then
        echo "Homebrew not found. Install from: https://brew.sh"
        echo "Then run: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi
    brew install tesseract
fi

echo ""
echo "Dependencies installed successfully!"
echo "Run: python3 vendor_manager.py"