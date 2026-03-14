from utils import logger
# document_service.py
import io
import base64
import numpy as np
import fitz  # PyMuPDF
import docx
from PIL import Image, ImageDraw

# ==========================================
# 文档解析服务 (PDF / Word / Image)
# ==========================================

class DocumentService:
    @staticmethod
    def process_doc_with_layout(file_path, file_type, p2t_engine, update_status=None, on_slice_ready=None):
        """
        使用 Pix2Text 版面分析引擎
        返回: pending_slices 列表，元素结构为 {"text": str, "image_b64": str, "diagram": str(图样)}
        """
        pending_slices = []

        doc = None
        try:
            total_pages = 1
            if file_type == "pdf":
                doc = fitz.open(file_path)
                total_pages = len(doc)

            for page_index in range(total_pages):
                if update_status:
                    update_status(f"🚀 AI 版面分析与 OCR 提取中: 第 {page_index+1}/{total_pages} 页...")

                img = None
                if file_type == "pdf":
                    pix = doc[page_index].get_pixmap(dpi=150)
                    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert('RGB')
                else:
                    img = Image.open(file_path).convert('RGB')

                try:
                    blocks = p2t_engine.recognize(img, return_text=True)
                    if hasattr(blocks, 'blocks'): blocks = blocks.blocks
                    elif isinstance(blocks, dict) and 'blocks' in blocks: blocks = blocks['blocks']

                    annotated_img = img.copy()
                    draw = ImageDraw.Draw(annotated_img)

                    colors = {
                        'text': 'red', 'title': 'red', 'figure': 'green', 'table': 'blue',
                        'equation': 'purple', 'isolated_equation': 'purple', 'formula': 'purple'
                    }

                    for block in blocks:
                        b_type = block.get('type', 'text').lower()
                        b_box = block.get('position', None)
                        if b_box is not None:
                            try:
                                box_arr = np.array(b_box).reshape(-1, 2)
                                x_min, y_min = np.min(box_arr, axis=0)
                                x_max, y_max = np.max(box_arr, axis=0)
                                color = colors.get(b_type, 'orange')
                                draw.rectangle([x_min, y_min, x_max, y_max], outline=color, width=2)
                                draw.text((x_min, max(0, y_min - 12)), b_type, fill=color)
                            except Exception:
                                pass

                    buf_anno = io.BytesIO()
                    annotated_img.save(buf_anno, format='PNG')
                    page_annotated_b64 = base64.b64encode(buf_anno.getvalue()).decode('utf-8')

                    current_text_chunk = []
                    current_boxes = []
                    current_diagram = None

                    def package_current_slice():
                        nonlocal current_text_chunk, current_boxes, current_diagram
                        if not current_text_chunk and not current_diagram:
                            return

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

                        slice_obj = {
                            "text": "\n".join(current_text_chunk),
                            "image_b64": chunk_img_b64,
                            "diagram": current_diagram,
                            "page_annotated_b64": page_annotated_b64
                        }
                        pending_slices.append(slice_obj)
                        if on_slice_ready:
                            try:
                                on_slice_ready(slice_obj)
                            except Exception as e:
                                logger.error(f"Error in on_slice_ready callback: {e}")

                        current_text_chunk = []
                        current_boxes = []
                        current_diagram = None

                    for block in blocks:
                        b_type = block.get('type', 'text').lower()
                        b_text = block.get('text', '').replace('\n', '')

                        if b_type in ['equation', 'isolated_equation', 'formula']:
                            if b_text.strip() and not b_text.startswith('$'):
                                b_text = '$' + b_text + '$'

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

                                    package_current_slice()
                                    current_diagram = new_diagram
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

                    package_current_slice()

                finally:
                    if 'annotated_img' in locals():
                        annotated_img.close()
                    if img:
                        img.close()

        finally:
            if doc:
                doc.close()

        return pending_slices

    @staticmethod
    def extract_from_word(docx_path):
        doc = docx.Document(docx_path)
        chunks = []
        current_text = []
        current_images = []

        def extract_image(embed_id):
            if embed_id:
                try:
                    part = doc.part.related_parts[embed_id]
                    if "image" in part.content_type:
                        img_data = part.blob
                        return base64.b64encode(img_data).decode("utf-8")
                except Exception as e:
                    logger.error(f"Error extracting image from docx: {e}")
            return None

        for element in doc.element.body:
            try:
                if element.tag.endswith("p"):
                    para = docx.text.paragraph.Paragraph(element, doc)
                    if para.text.strip():
                        prefix = ""
                        if para.style.name.startswith("Heading"):
                            prefix = "# "
                        elif element.xpath(".//w:numPr"):
                            prefix = "- "
                        current_text.append(prefix + para.text.strip())

                elif element.tag.endswith("tbl"):
                    table = docx.table.Table(element, doc)
                    for i, row in enumerate(table.rows):
                        if row_data:
                            current_text.append("| " + " | ".join(row_data) + " |")
                            if i == 0:
                                current_text.append("|" + "|".join(["---"] * len(row_data)) + "|")

                for blip in element.xpath(".//a:blip"):
                    embed_id = None
                    for key in blip.keys():
                        if key.endswith("embed"):
                            embed_id = blip.get(key)
                            break
                    img_b64 = extract_image(embed_id)
                    if img_b64: current_images.append(img_b64)

                for imagedata in element.xpath(".//v:imagedata"):
                    embed_id = None
                    for key in imagedata.keys():
                        if key.endswith("id"):
                            embed_id = imagedata.get(key)
                            break
                    img_b64 = extract_image(embed_id)
                    if img_b64: current_images.append(img_b64)

            except Exception as e:
                logger.error(f"Error processing word element: {e}")
                continue

            if len(current_text) >= 10 or current_images:
                chunks.append({
                    "text": "\\n".join(current_text),
                    "image_b64": "",
                    "diagram": current_images[0] if current_images else None
                })
                current_text = []
                if len(current_images) > 1:
                    for extra_img in current_images[1:]:
                        chunks.append({"text": "", "image_b64": "", "diagram": extra_img})
                current_images = []

        if current_text or current_images:
            chunks.append({
                "text": "\\n".join(current_text) if current_text else "",
                "image_b64": "",
                "diagram": current_images[0] if current_images else None
            })
            if len(current_images) > 1:
                for extra_img in current_images[1:]:
                    chunks.append({"text": "", "image_b64": "", "diagram": extra_img})

        if not chunks:
            full_text = "\\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            text_chunks = [chunk for chunk in full_text.split("\\n\\n") if chunk.strip()]
            chunks = [{"text": t.replace("\\n", " "), "image_b64": "", "diagram": None} for t in text_chunks]

        return chunks
