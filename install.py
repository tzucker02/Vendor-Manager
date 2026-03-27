import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd, check=True):
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=check)


def command_exists(name):
    return shutil.which(name) is not None


def add_sudo_if_needed(cmd):
    if os.name != "posix":
        return cmd
    if os.geteuid() == 0:
        return cmd
    if command_exists("sudo"):
        return ["sudo"] + cmd
    return cmd


def tesseract_installed():
    if not command_exists("tesseract"):
        return False
    try:
        subprocess.run(["tesseract", "--version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.SubprocessError:
        return False


def install_tesseract_windows():
    # Prefer Winget first, then Chocolatey.
    attempts = [
        ["winget", "install", "-e", "--id", "UB-Mannheim.TesseractOCR"],
        ["choco", "install", "tesseract", "-y"],
    ]

    for cmd in attempts:
        if command_exists(cmd[0]):
            try:
                run_cmd(cmd)
                return True
            except subprocess.CalledProcessError:
                continue

    return False


def install_tesseract_macos():
    if not command_exists("brew"):
        return False
    try:
        run_cmd(["brew", "install", "tesseract"])
        return True
    except subprocess.CalledProcessError:
        return False


def install_tesseract_linux():
    package_managers = [
        (["apt-get"], ["apt-get", "update"], ["apt-get", "install", "-y", "tesseract-ocr"]),
        (["dnf"], None, ["dnf", "install", "-y", "tesseract"]),
        (["yum"], None, ["yum", "install", "-y", "tesseract"]),
        (["pacman"], None, ["pacman", "-S", "--noconfirm", "tesseract"]),
        (["zypper"], None, ["zypper", "install", "-y", "tesseract-ocr"]),
        (["apk"], None, ["apk", "add", "tesseract-ocr"]),
    ]

    for probe, pre_cmd, install_cmd in package_managers:
        if command_exists(probe[0]):
            try:
                if pre_cmd is not None:
                    run_cmd(add_sudo_if_needed(pre_cmd))
                run_cmd(add_sudo_if_needed(install_cmd))
                return True
            except subprocess.CalledProcessError:
                continue

    return False


def install_tesseract_for_current_os(skip_system):
    if tesseract_installed():
        print("Tesseract already installed.")
        return True

    if skip_system:
        print("Skipping OS-level package installation by request.")
        return False

    system_name = platform.system().lower()

    if system_name == "windows":
        ok = install_tesseract_windows()
    elif system_name == "darwin":
        ok = install_tesseract_macos()
    elif system_name == "linux":
        ok = install_tesseract_linux()
    else:
        ok = False

    if ok and tesseract_installed():
        print("Tesseract installation successful.")
        return True

    print("Could not automatically install Tesseract.")
    print("Manual install guidance:")
    if system_name == "windows":
        print("- Install from: https://github.com/UB-Mannheim/tesseract/wiki")
    elif system_name == "darwin":
        print("- Run: brew install tesseract")
    elif system_name == "linux":
        print("- Debian/Ubuntu: sudo apt-get install -y tesseract-ocr")
        print("- Fedora/RHEL: sudo dnf install -y tesseract")
    else:
        print("- Install Tesseract OCR and ensure 'tesseract' is available in PATH.")
    return False


def create_and_populate_venv(project_dir):
    venv_dir = project_dir / ".venv"
    if os.name == "nt":
        python_in_venv = venv_dir / "Scripts" / "python.exe"
    else:
        python_in_venv = venv_dir / "bin" / "python"

    if not python_in_venv.exists():
        print("Creating virtual environment...")
        run_cmd([sys.executable, "-m", "venv", str(venv_dir)])

    requirements = project_dir / "requirements.txt"
    if not requirements.exists():
        raise FileNotFoundError(f"requirements.txt not found at {requirements}")

    print("Installing Python dependencies...")
    run_cmd([str(python_in_venv), "-m", "pip", "install", "--upgrade", "pip"])
    run_cmd([str(python_in_venv), "-m", "pip", "install", "-r", str(requirements)])

    return python_in_venv


def main():
    parser = argparse.ArgumentParser(description="Cross-platform installer for Vendor Manager")
    parser.add_argument("--run-app", action="store_true", help="Run vendor_manager.py after install")
    parser.add_argument("--skip-system", action="store_true", help="Skip OS-level package installs (e.g., Tesseract)")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent

    try:
        python_in_venv = create_and_populate_venv(project_dir)
        install_tesseract_for_current_os(skip_system=args.skip_system)

        print("\nSetup complete.")
        if os.name == "nt":
            print("Run app: .\\.venv\\Scripts\\python.exe .\\vendor_manager.py")
        else:
            print("Run app: ./.venv/bin/python ./vendor_manager.py")

        if args.run_app:
            run_cmd([str(python_in_venv), str(project_dir / "vendor_manager.py")])

    except Exception as exc:
        print(f"Setup failed: {exc}")
        print("For platform-specific setup and troubleshooting, see INSTALL.md in this folder.")
        sys.exit(1)


if __name__ == "__main__":
    main()
