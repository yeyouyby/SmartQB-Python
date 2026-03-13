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
        print(f"图样转换失败: {e}")
        return base64.b64encode(img_bytes).decode('utf-8')