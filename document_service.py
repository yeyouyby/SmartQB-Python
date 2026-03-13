# document_service.py
import io
import base64
import numpy as np
import fitz  # PyMuPDF
import docx
from PIL import Image

# ==========================================
# 文档解析服务 (PDF / Word / Image)
# ==========================================

class DocumentService:
    @staticmethod
    def process_doc_with_layout(file_path, file_type, p2t_engine, update_status=None):
        """
        使用 Pix2Text 版面分析引擎
        返回: pending_slices 列表，元素结构为 {"text": str, "image_b64": str, "diagram": str(图样)}
        """
        pending_slices = []
        
        images_to_process = []
        if file_type == "pdf":
            doc = fitz.open(file_path)
            for i in range(len(doc)):
                pix = doc[i].get_pixmap(dpi=150)
                images_to_process.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert('RGB'))
            doc.close()
        else:
            images_to_process.append(Image.open(file_path).convert('RGB'))

        for page_index, img in enumerate(images_to_process):
            if update_status:
                update_status(f"🚀 AI 版面分析与 OCR 提取中: 第 {page_index+1}/{len(images_to_process)} 页...")
                
            blocks = p2t_engine.recognize(img, return_text=False)
            if hasattr(blocks, 'blocks'): blocks = blocks.blocks
            elif isinstance(blocks, dict) and 'blocks' in blocks: blocks = blocks['blocks']
            
            current_text_chunk = []
            current_boxes = [] # 用于记录这一批文字的坐标
            current_diagram = None
            
            def package_current_slice():
                nonlocal current_text_chunk, current_boxes, current_diagram
                if not current_text_chunk:
                    return
                
                # 计算这段文字所在图像的包围盒，并截图 (用于视觉AI对齐)
                chunk_img_b64 = ""
                if current_boxes:
                    try:
                        all_pts = np.vstack(current_boxes)
                        x_min, y_min = np.min(all_pts, axis=0)
                        x_max, y_max = np.max(all_pts, axis=0)
                        cropped = img.crop((max(0, x_min-5), max(0, y_min-5), min(img.width, x_max+5), min(img.height, y_max+5)))
                        buf = io.BytesIO()
                        cropped.save(buf, format='PNG')
                        chunk_img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                    except:
                        pass
                
                pending_slices.append({
                    "text": "".join(current_text_chunk),
                    "image_b64": chunk_img_b64,
                    "diagram": current_diagram
                })
                current_text_chunk = []
                current_boxes = []
                current_diagram = None

            for block in blocks:
                b_type = block.get('type', 'text').lower()
                b_text = block.get('text', '').replace('\n', '') 
                b_box = block.get('position', None)
                
                if b_type in ['figure', 'table']:
                    if b_box is not None:
                        try:
                            box_arr = np.array(b_box).reshape(-1, 2)
                            x_min, y_min = np.min(box_arr, axis=0)
                            x_max, y_max = np.max(box_arr, axis=0)
                            cropped = img.crop((max(0, x_min-5), max(0, y_min-5), min(img.width, x_max+5), min(img.height, y_max+5)))
                            buf = io.BytesIO()
                            cropped.save(buf, format='PNG')
                            new_diagram = base64.b64encode(buf.getvalue()).decode('utf-8')
                            
                            package_current_slice() # 遇到图，先把前面的字打包
                            current_diagram = new_diagram # 暂存这张图分配给接下来的字
                        except:
                            pass
                else:
                    if b_text.strip():
                        current_text_chunk.append(b_text)
                        if b_box is not None:
                            current_boxes.append(np.array(b_box).reshape(-1, 2))
                            
            # 页面结束打包剩余
            package_current_slice()
                    
        return pending_slices

    @staticmethod
    def extract_from_word(docx_path):
        doc = docx.Document(docx_path)
        full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        chunks = [chunk for chunk in full_text.split('\n\n') if chunk.strip()]
        # 兼容新的数据结构
        return [{"text": t.replace('\n', ' '), "image_b64": "", "diagram": None} for t in chunks]