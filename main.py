import pyarrow as pa
from db_adapter import LanceDBAdapter
from utils import logger
from gui_app import SmartQBApp

from settings_manager import SettingsManager


import os
import sys
import subprocess
import threading
from tkinter import messagebox

def download_models():
    logger.info("Checking and downloading models...")
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    model_dir = os.path.join(base_dir, "model")

    p2t_dir = os.path.join(model_dir, "pix2text")
    yolo_dir = os.path.join(model_dir, "doclayoutyolo")

    os.makedirs(p2t_dir, exist_ok=True)
    os.makedirs(yolo_dir, exist_ok=True)

    # Set home directories so that pix2text loads from our bundled models directory
    os.environ["PIX2TEXT_HOME"] = p2t_dir
    os.environ["CNSTD_HOME"] = os.path.join(p2t_dir, "cnstd-cnocr-models")
    os.environ["CNOCR_HOME"] = os.path.join(p2t_dir, "cnstd-cnocr-models")


    try:
        from huggingface_hub import snapshot_download
        logger.info("Checking Pix2Text Layout Model...")
        snapshot_download(repo_id="breezedeus/pix2text-layout", local_dir=os.path.join(p2t_dir, "layout-parser"), revision="main")  # nosec B615
        logger.info("Checking Pix2Text Table-Rec Model...")
        snapshot_download(repo_id="breezedeus/pix2text-table-rec", local_dir=os.path.join(p2t_dir, "table-rec"), revision="main")  # nosec B615
        logger.info("Checking Pix2Text MFD Model...")
        snapshot_download(repo_id="breezedeus/pix2text-mfd", local_dir=os.path.join(p2t_dir, "mfd"), revision="main")  # nosec B615
        logger.info("Checking Pix2Text MFR Model...")
        snapshot_download(repo_id="breezedeus/pix2text-mfr", local_dir=os.path.join(p2t_dir, "mfr-1.5-onnx"), revision="main")  # nosec B615
        logger.info("Checking CnSTD/CnOCR Models...")
        snapshot_download(repo_id="breezedeus/cnstd-cnocr-models", local_dir=os.path.join(p2t_dir, "cnstd-cnocr-models"), revision="main")  # nosec B615
        logger.info("Pix2Text models downloaded successfully.")
    except Exception as e:
        logger.error(f"Failed to download Pix2Text models: {e}")

    try:
        from modelscope.hub.snapshot_download import snapshot_download as ms_download
        logger.info("Checking DocLayout-YOLO Model...")
        ms_download(model_id="AI-ModelScope/DocLayout-YOLO-DocStructBench-onnx", local_dir=yolo_dir, revision="master")
        logger.info("DocLayout-YOLO models downloaded successfully.")
    except Exception as e:
        logger.error(f"Failed to download DocLayout-YOLO models: {e}")

def check_and_install_miktex():
    logger.info("Checking MiKTeX/TeX Live environment...")
    try:
        res = subprocess.run(["xelatex", "--version"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            logger.info("xelatex found. MiKTeX/TeX Live is installed.")
            return
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Error checking xelatex: {e}")

    logger.info("xelatex not found. Attempting to install MiKTeX (this may take a few minutes)...")
    if sys.platform != "win32":
        logger.warning("Auto-install of MiKTeX is only supported on Windows. Please install it manually.")
        return

    import urllib.request
    import tempfile

    installer_url = "https://mirrors.ctan.org/systems/win32/miktex/setup/windows-x64/basic-miktex-24.4-x64.exe"
    temp_dir = tempfile.gettempdir()
    installer_path = os.path.join(temp_dir, "miktex-setup.exe")

    try:
        logger.info(f"Downloading MiKTeX installer from {installer_url}...")
        urllib.request.urlretrieve(installer_url, installer_path)  # nosec B310
        logger.info("Download complete. Running silent installation...")
        expected_sha256 = os.environ.get("MIKTEX_INSTALLER_SHA256")
        if expected_sha256:
            import hashlib
            with open(installer_path, "rb") as f_sha:
                actual_sha256 = hashlib.sha256(f_sha.read()).hexdigest()
            if actual_sha256.lower() != expected_sha256.lower():
                raise RuntimeError("MiKTeX installer checksum mismatch; aborting installation.")
            logger.info("Checksum verified.")
        import shlex
        safe_path = shlex.quote(installer_path)
        subprocess.run([safe_path, "--unattended", "--private"], check=True)  # nosec B603
        logger.info("MiKTeX installed successfully.")

        # Add to PATH for current session if possible
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        miktex_bin = os.path.join(local_app_data, 'Programs', 'MiKTeX', 'miktex', 'bin', 'x64')
        if miktex_bin not in os.environ['PATH']:
            os.environ['PATH'] = f"{miktex_bin};{os.environ['PATH']}"

        logger.info("Checking and installing LaTeX packages...")
        packages = ["ctex", "amsmath", "amsfonts", "geometry", "graphicx", "xecjk", "cjk", "zhnumber"]
        for pkg in packages:
            result = subprocess.run(["mpm", f"--install={pkg}"], capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode != 0:
                logger.warning(f"Failed to install LaTeX package '{pkg}'. stdout: {result.stdout}, stderr: {result.stderr}")
        logger.info("LaTeX packages installation attempt finished.")

    except Exception as e:
        logger.error(f"Failed to install MiKTeX: {e}")
    finally:
        if os.path.exists(installer_path):
            try:
                os.remove(installer_path)
            except Exception as e:
                logger.debug(f"Cleanup failed: {e}")

def ensure_lancedb_tables():
    logger.info("Initializing LanceDB database and verifying core tables...")
    try:
        adapter = LanceDBAdapter()
        db = adapter.db

        try:
            db.open_table("questions")
            logger.info("Table 'questions' found.")
        except Exception:
            logger.info("Table 'questions' missing, creating it...")
            db.create_table(
                "questions",
                schema=pa.schema([
                    pa.field("id", pa.int64()),
                    pa.field("content", pa.string()),
                    pa.field("logic_descriptor", pa.string()),
                    pa.field("difficulty", pa.float64()),
                    pa.field("vector", pa.list_(pa.float32(), getattr(SettingsManager(), 'embedding_dimension', 1024))),
                    pa.field("diagram_base64", pa.string()),
                ]),
            )

        try:
            db.open_table("tags")
            logger.info("Table 'tags' found.")
        except Exception:
            logger.info("Table 'tags' missing, creating it...")
            db.create_table(
                "tags",
                schema=pa.schema([
                    pa.field("id", pa.int64()),
                    pa.field("name", pa.string()),
                ]),
            )

        try:
            db.open_table("question_tags")
            logger.info("Table 'question_tags' found.")
        except Exception:
            logger.info("Table 'question_tags' missing, creating it...")
            db.create_table(
                "question_tags",
                schema=pa.schema([
                    pa.field("question_id", pa.int64()),
                    pa.field("tag_id", pa.int64()),
                ]),
            )
        logger.info("LanceDB initialization complete.")
    except Exception as e:
        logger.error(f"Failed to initialize LanceDB tables: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    threading.Thread(target=download_models, daemon=True).start()
    threading.Thread(target=check_and_install_miktex, daemon=True).start()
    # 启动 GUI 主程序

    ensure_lancedb_tables()
    logger.info("Starting GUI main loop...")
    app = SmartQBApp()
    app.mainloop()
    logger.info("SmartQB Pro V3 stopped.")
