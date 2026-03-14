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
            with fitz.open(file_path) as doc:
                for i in range(len(doc)):
                    pix = doc[i].get_pixmap(dpi=150)
                    images_to_process.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert('RGB'))
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
                if not current_text_chunk and not current_diagram:
                    return

                # 计算这段文字所在图像的包围盒，并截图 (用于视觉AI对齐)
                chunk_img_b64 = ""
                if current_boxes:
                    try:
                        all_pts = np.vstack(current_boxes)
                        x_min, y_min = np.min(all_pts, axis=0)
                        x_max, y_max = np.max(all_pts, axis=0)
                        cropped = img.crop((max(0, int(x_min)-5), max(0, int(y_min)-5), min(img.width, int(x_max)+5), min(img.height, int(y_max)+5)))
                        buf = io.BytesIO()
                        cropped.save(buf, format='PNG')
                        chunk_img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                    except Exception:
                        pass

                pending_slices.append({
                    "text": "\n".join(current_text_chunk),
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
                            cropped = img.crop((max(0, int(x_min)-5), max(0, int(y_min)-5), min(img.width, int(x_max)+5), min(img.height, int(y_max)+5)))
                            buf = io.BytesIO()
                            cropped.save(buf, format='PNG')
                            new_diagram = base64.b64encode(buf.getvalue()).decode('utf-8')

                            package_current_slice() # 遇到图，先把前面的字打包
                            current_diagram = new_diagram # 暂存这张图分配给接下来的字
                        except Exception:
                            pass
                else:
                    if b_text.strip():
                        current_text_chunk.append(b_text)
                        if b_box is not None:
                            try:
                                b_box_arr = np.array(b_box)
                                if b_box_arr.size > 0 and b_box_arr.size % 2 == 0:
                                    current_boxes.append(b_box_arr.reshape(-1, 2))
                            except Exception:
                                pass

            # 页面结束打包剩余
            package_current_slice()

        return pending_slices

    @staticmethod
    def extract_from_word(docx_path):
        doc = docx.Document(docx_path)
        chunks = []
        current_text = []
        current_images = []

        for element in doc.element.body:
            # Check for paragraphs
            if element.tag.endswith('p'):
                para = docx.text.paragraph.Paragraph(element, doc)
                if para.text.strip():
                    current_text.append(para.text.replace('\n', ' '))
            elif element.tag.endswith('tbl'):
                # Handle tables - extract all text from all cells
                for row in element.findall('.//w:tr', namespaces=element.nsmap):
                    row_text = []
                    for cell in row.findall('.//w:tc', namespaces=element.nsmap):
                        cell_paras = cell.findall('.//w:p', namespaces=element.nsmap)
                        cell_text = []
                        for cp in cell_paras:
                            p = docx.text.paragraph.Paragraph(cp, doc)
                            if p.text.strip():
                                cell_text.append(p.text.strip())
                        if cell_text:
                            row_text.append(" ".join(cell_text))
                    if row_text:
                        current_text.append(" | ".join(row_text))

            # Check for images in current element using proper namespace resolution
            for run in element.findall('.//w:r', namespaces=element.nsmap):
                for drawing in run.findall('.//w:drawing', namespaces=element.nsmap):
                    ns_dict = {**element.nsmap, "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
                    for blip in drawing.findall('.//a:blip', namespaces=ns_dict):
                        r_ns = drawing.nsmap.get('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
                        embed = blip.get(f"{{{r_ns}}}embed")
                        if embed:
                            try:
                                part = doc.part.related_parts[embed]
                                if 'image' in part.content_type:
                                    img_data = part.blob
                                    img_b64 = base64.b64encode(img_data).decode('utf-8')
                                    current_images.append(img_b64)
                            except Exception as e:
                                print(f"Error extracting image from docx: {e}")

            # If we accumulate substantial text or hit an image, flush a chunk
            if len(current_text) >= 5 or current_images:
                # Flush the main chunk with the first image if any
                chunks.append({
                    "text": "\n".join(current_text),
                    "image_b64": "",
                    "diagram": current_images[0] if current_images else None
                })
                current_text = []

                # If there are extra images without text, flush them as separate empty-text chunks so they aren't lost
                if len(current_images) > 1:
                    for extra_img in current_images[1:]:
                        chunks.append({
                            "text": "",
                            "image_b64": "",
                            "diagram": extra_img
                        })
                current_images = []

        # Flush remaining
        if current_text or current_images:
            chunks.append({
                "text": "\n".join(current_text) if current_text else "",
                "image_b64": "",
                "diagram": current_images[0] if current_images else None
            })
            if len(current_images) > 1:
                for extra_img in current_images[1:]:
                    chunks.append({
                        "text": "",
                        "image_b64": "",
                        "diagram": extra_img
                    })
            current_images = []

        # Fallback if XML parsing missed things but standard paragraphs exist
        if not chunks:
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            text_chunks = [chunk for chunk in full_text.split('\n\n') if chunk.strip()]
            chunks = [{"text": t.replace('\n', ' '), "image_b64": "", "diagram": None} for t in text_chunks]

        return chunks