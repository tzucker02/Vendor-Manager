#!/bin/bash
echo "Installing Vendor Manager dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-tk tesseract-ocr libtesseract-dev

python3 -m pip install --upgrade pip
pip3 install -r requirements.txt

echo ""
echo "Dependencies installed successfully!"
echo "Run: python3 vendor_manager.py"