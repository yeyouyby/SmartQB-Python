import logging
import logging.handlers

def setup_logger():
    logger = logging.getLogger("SmartQB")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        file_handler = logging.handlers.RotatingFileHandler(
            "smartqb.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s")
        file_handler.setFormatter(file_formatter)
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

logger = setup_logger()

# utils.py
import io
import base64
from PIL import Image

# ==========================================
# 图像处理工具
# ==========================================

def optimize_diagram_to_base64(img_bytes):
    """
    将提取到的图样字节流转换为 Base64。
    保留原始图样（包括彩色、灰度、网格线等细节）。
    """
    try:
        # 直接读取原图，保留原格式和色彩
        img = Image.open(io.BytesIO(img_bytes))

        # 为了保证导出的统一性，统一转存为 PNG 格式的 Base64
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        logger.error(f"图样转换失败: {e}")
        return base64.b64encode(img_bytes).decode('utf-8')
import psutil
try:
    import torch
except ImportError:
    torch = None

def check_hardware_requirements():
    """
    Checks if hardware meets the requirements for Surya (16GB+ RAM, 6GB+ VRAM on GPU).
    Returns True if hardware is sufficient, False otherwise.
    """
    MIN_RAM_GB = 15.0
    MIN_VRAM_GB = 5.5
    try:
        # Check system memory (RAM) >= 16GB
        # psutil.virtual_memory().total returns bytes
        ram_gb = psutil.virtual_memory().total / (1024**3)
        if ram_gb < MIN_RAM_GB:  # Allow some margin (e.g. 15.X GB usable)
            logger.info(f"Hardware check: Insufficient RAM ({ram_gb:.1f}GB < 16GB). Surya will be disabled.")
            return False

        # Check GPU and VRAM >= 6GB
        if torch is None or not torch.cuda.is_available():
            logger.info("Hardware check: No CUDA GPU detected. Surya will be disabled.")
            return False

        # Check first available GPU (assuming index 0)
        vram_bytes = torch.cuda.get_device_properties(0).total_memory
        vram_gb = vram_bytes / (1024**3)
        if vram_gb < MIN_VRAM_GB: # Allow some margin
            logger.info(f"Hardware check: Insufficient GPU VRAM ({vram_gb:.1f}GB < 6GB). Surya will be disabled.")
            return False

        logger.info(f"Hardware check: Passed (RAM: {ram_gb:.1f}GB, VRAM: {vram_gb:.1f}GB).")
        return True
    except Exception as e:
        logger.warning(f"Hardware check failed: {e}. Assuming insufficient hardware.")
        return False
