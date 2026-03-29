import io
import base64
from PIL import Image
import logging
import logging.handlers


def setup_logger():
    logger = logging.getLogger("SmartQB")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        file_handler = logging.handlers.RotatingFileHandler(
            "smartqb.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger


logger = setup_logger()


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
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error(f"图样转换失败: {e}")
        return base64.b64encode(img_bytes).decode("utf-8")


def pad_or_truncate_vector(vec, target_dim):
    """
    Pads or truncates a list to exactly match the target_dim.
    Logs a warning if modification is necessary.
    """
    if len(vec) != target_dim:
        if len(vec) == 0:
            vec = [0.0] * target_dim
        elif len(vec) > target_dim:
            logger.warning(
                f"Vector dimension mismatch. Truncating vector from {len(vec)} to {target_dim}."
            )
            vec = vec[:target_dim]
        else:
            logger.warning(
                f"Vector dimension mismatch. Padding vector from {len(vec)} to {target_dim}."
            )
            vec.extend([0.0] * (target_dim - len(vec)))
    return vec
