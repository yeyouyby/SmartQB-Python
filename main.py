import requests  # type: ignore
from db_adapter import LanceDBAdapter
from utils import logger


import os
import sys
import subprocess

MIKTEX_INSTALLER_URL = "https://mirrors.rit.edu/CTAN/systems/win32/miktex/setup/windows-x64/basic-miktex-24.1-x64.exe"
MIKTEX_EXPECTED_SHA256 = (
    "3f2fb7c34606117bdc03ea3d2fce1d0ebbbfe1da584da25eb488a75e3f3ab8b2"
)


def check_and_install_miktex(raise_errors=False):
    logger.info("Checking MiKTeX/TeX Live environment...")
    try:
        res = subprocess.run(  # nosec
            ["xelatex", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            logger.info("xelatex found. MiKTeX/TeX Live is installed.")
            return
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Error checking xelatex: {e}")

    logger.info(
        "xelatex not found. Attempting to install MiKTeX (this may take a few minutes)..."
    )
    if sys.platform != "win32":
        logger.warning(
            "Auto-install of MiKTeX is only supported on Windows. Please install it manually."
        )
        return

    import tempfile

    installer_url = MIKTEX_INSTALLER_URL
    temp_dir = tempfile.gettempdir()
    installer_path = os.path.join(temp_dir, "miktex-setup.exe")

    try:
        logger.info(f"Downloading MiKTeX installer from {installer_url}...")
        response = requests.get(installer_url, stream=True, timeout=30)
        response.raise_for_status()
        with open(installer_path, "wb") as f_out:
            for chunk in response.iter_content(chunk_size=8192):
                f_out.write(chunk)
        logger.info("Download complete. Running silent installation...")
        expected_sha256 = os.environ.get(
            "MIKTEX_INSTALLER_SHA256",
            MIKTEX_EXPECTED_SHA256,
        )
        if expected_sha256:
            import hashlib

            with open(installer_path, "rb") as f_sha:
                sha256_hash = hashlib.sha256()
                for chunk in iter(lambda: f_sha.read(8192), b""):
                    sha256_hash.update(chunk)
                actual_sha256 = sha256_hash.hexdigest()
            if actual_sha256.lower() != expected_sha256.lower():
                raise RuntimeError(
                    "MiKTeX installer checksum mismatch; aborting installation."
                )
            logger.info("Checksum verified.")
        subprocess.run([installer_path, "--unattended", "--private"], check=True)  # nosec B603
        logger.info("MiKTeX installed successfully.")

        # Add to PATH for current session if possible
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        miktex_bin = os.path.join(
            local_app_data, "Programs", "MiKTeX", "miktex", "bin", "x64"
        )
        if miktex_bin not in os.environ["PATH"]:
            os.environ["PATH"] = f"{miktex_bin};{os.environ['PATH']}"

        logger.info("Checking and installing LaTeX packages...")
        packages = [
            "ctex",
            "amsmath",
            "amsfonts",
            "geometry",
            "graphicx",
            "xecjk",
            "cjk",
            "zhnumber",
        ]
        for pkg in packages:
            result = subprocess.run(  # nosec
                ["mpm", f"--install={pkg}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                logger.warning(
                    f"Failed to install LaTeX package '{pkg}'. stdout: {result.stdout}, stderr: {result.stderr}"
                )
        logger.info("LaTeX packages installation attempt finished.")

    except Exception as e:
        logger.error(f"Failed to install MiKTeX: {e}")
        if raise_errors:
            raise
    finally:
        if os.path.exists(installer_path):
            try:
                os.remove(installer_path)
            except Exception as e:
                logger.debug(f"Cleanup failed: {e}")


def ensure_lancedb_tables():
    logger.info("Initializing LanceDB database and verifying core tables...")
    try:
        # The LanceDBAdapter __init__ handles checking, backing up, and creating the tables
        LanceDBAdapter()
        logger.info("LanceDB initialization complete.")
    except Exception as e:
        logger.error(f"Failed to initialize LanceDB tables: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="Run model downloads and env setup without launching GUI",
    )
    args, unknown = parser.parse_known_args()

    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    model_dir = os.path.join(base_dir, "model")

    if args.setup_only:
        try:
            check_and_install_miktex(raise_errors=True)
        except Exception as e:
            logger.error(f"Setup failed: {e}", exc_info=True)
            sys.exit(1)
        sys.exit(0)

    # 启动 GUI 主程序

    ensure_lancedb_tables()

    from gui_pyside import main as start_pyside_gui

    logger.info("Starting PySide GUI main loop...")
    start_pyside_gui()
    logger.info("SmartQB Pro V3 stopped.")
