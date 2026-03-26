#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Installing Python via Homebrew..."
    brew install python
  else
    echo "Python 3 is not installed and Homebrew is unavailable."
    echo "Install Homebrew from https://brew.sh or install Python 3.10+ manually, then re-run."
    exit 1
  fi
fi

echo "Running installer with python3 install.py $*"
python3 install.py "$@"
