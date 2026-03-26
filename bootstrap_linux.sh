#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

run_root_cmd() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif have_cmd sudo; then
    sudo "$@"
  else
    echo "Root privileges are required to install Python. Re-run as root or install sudo." >&2
    exit 1
  fi
}

if ! have_cmd python3; then
  echo "Python 3 not found. Attempting install..."
  if have_cmd apt-get; then
    run_root_cmd apt-get update
    run_root_cmd apt-get install -y python3 python3-venv python3-pip
  elif have_cmd dnf; then
    run_root_cmd dnf install -y python3 python3-pip
  elif have_cmd yum; then
    run_root_cmd yum install -y python3 python3-pip
  elif have_cmd pacman; then
    run_root_cmd pacman -Sy --noconfirm python python-pip
  elif have_cmd zypper; then
    run_root_cmd zypper install -y python3 python3-pip
  elif have_cmd apk; then
    run_root_cmd apk add python3 py3-pip
  else
    echo "No supported package manager found. Install Python 3.10+ manually and re-run." >&2
    exit 1
  fi
fi

echo "Running installer with python3 install.py $*"
python3 install.py "$@"
