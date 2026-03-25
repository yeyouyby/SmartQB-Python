import io
import base64
import numpy as np
import fitz  # PyMuPDF
import docx
from PIL import Image, ImageDraw
from utils import logger

# ==========================================
# 文档解析服务 (PDF / Word / Image)
# ==========================================

class DocumentService:

    @staticmethod
    def process_doc_with_layout(file_path, file_type, layout_predictor, ocr_engine, ocr_engine_type="Pix2Text", update_status=None, on_slice_ready=None, det_predictor=None):
        """
        使用 DocLayout-YOLO 进行版面分析 (Pass 1) + Pix2Text OCR 的双层分析引擎
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
                    update_status(f"🚀 AI 双擎分析与 OCR 提取中: 第 {page_index+1}/{total_pages} 页...")

                img = None
                if file_type == "pdf":
                    pix = doc[page_index].get_pixmap(dpi=150)
                    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert('RGB')
                else:
                    img = Image.open(file_path).convert('RGB')

                try:
                    # ==========================================
                    # PASS 1: Layout 图样提取
                    # ==========================================
                    layout_boxes = []
                    diagrams = []
                    text_regions = []

                    try:
                        if layout_predictor is not None:
                            # DocLayout-YOLO Predictor
                            layout_result = layout_predictor([img])[0]
                            for item in layout_result.bboxes:
                                box = item.bbox
                                p_type = item.label

                                # 加入 table 和 equation 等
                                if p_type in ['Picture', 'Figure', 'Table', 'Formula', 'Text-inline-math', 'Form']:
                                    x_min, y_min, x_max, y_max = box

                                    # Relax crop bounds slightly to capture edges
                                    crop_box = (
                                        max(0, int(x_min)-5),
                                        max(0, int(y_min)-5),
                                        min(img.width, int(x_max)+5),
                                        min(img.height, int(y_max)+5)
                                    )
                                    cropped = img.crop(crop_box)
                                    buf = io.BytesIO()
                                    cropped.save(buf, format='PNG')
                                    new_diagram = base64.b64encode(buf.getvalue()).decode('utf-8')
                                    diagrams.append({
                                        'y_center': (box[1] + box[3]) / 2,
                                        'diagram_b64': new_diagram,
                                        'box': crop_box,
                                        'type': p_type
                                    })
                                else:
                                    text_regions.append({
                                        'box': box,
                                        'y_center': (box[1] + box[3]) / 2,
                                        'type': p_type
                                    })
                    except Exception as e:
                        logger.error(f"Layout Analysis 识别失败: {e}", exc_info=True)



                    # ==========================================
                    # PASS 2: FULL PAGE OCR 文字提取
                    # ==========================================
                    ocr_blocks = []
                    annotated_img = img.copy()
                    draw = ImageDraw.Draw(annotated_img)

                    try:
                        if ocr_engine_type == "Pix2Text" and ocr_engine is not None:
                            # Pix2Text can process full page and return boxes
                            res = ocr_engine.recognize(img, return_text=False)
                            for block in res:
                                text = block.get('text', '').replace('\n', ' ').strip()
                                position = block.get('position', [])
                                if text and len(position) == 4:
                                    # [ [x_topleft, y_topleft], [x_topright, y_topright], [x_bottomright, y_bottomright], [x_bottomleft, y_bottomleft] ]
                                    x_coords = [p[0] for p in position]
                                    y_coords = [p[1] for p in position]
                                    box = (min(x_coords), min(y_coords), max(x_coords), max(y_coords))
                                    ocr_blocks.append({
                                        'text': text,
                                        'box': box,
                                        'y_center': (box[1] + box[3]) / 2,
                                        'type': 'TextLine'
                                    })
                                elif text and block.get('box_2d'): # fallback if it returns box_2d
                                    box = block.get('box_2d')
                                    ocr_blocks.append({
                                        'text': text,
                                        'box': box,
                                        'y_center': (box[1] + box[3]) / 2,
                                        'type': 'TextLine'
                                    })

                    except Exception as e:
                        logger.error(f"Full Page OCR failed: {e}", exc_info=True)

                    # Draw boxes
                    for b in ocr_blocks:
                        try:
                            draw.rectangle(b['box'], outline='orange', width=2)
                        except Exception as e:
                            logger.warning(f"Failed to draw OCR box: {e}")
                    for b in diagrams:
                        try:
                            x_min, y_min, x_max, y_max = b['box']
                            draw.rectangle([x_min, y_min, x_max, y_max], outline='green', width=3)
                            draw.text((x_min, max(0, y_min - 12)), f"Layout-{b['type']}", fill='green')
                        except Exception as e:
                            logger.warning(f"Failed to draw diagram box: {e}")

                    buf_anno = io.BytesIO()
                    annotated_img.save(buf_anno, format='PNG')
                    page_annotated_b64 = base64.b64encode(buf_anno.getvalue()).decode('utf-8')
# --- NEW LOGIC: Match diagrams to nearest OCR text box above it ---
                    # ocr_blocks: list of dicts with 'text', 'box', 'y_center', 'type'
                    # diagrams: list of dicts with 'diagram_b64', 'box', 'type'

                    # Sort text blocks by y_min top-down
                    ocr_blocks.sort(key=lambda x: x['box'][1])

                    diagram_map = {}  # Maps globally unique marker to base64

                    for d_idx, d in enumerate(diagrams):
                        d_x_min, d_y_min, d_x_max, d_y_max = d['box']
                        global_marker = f"{page_index}_{d_idx}"
                        diagram_map[global_marker] = d['diagram_b64']

                        best_t_idx = -1
                        min_dist = float('inf')

                        # Find the text block immediately above this diagram with horizontal overlap
                        for t_idx, t in enumerate(ocr_blocks):
                            t_x_min, t_y_min, t_x_max, t_y_max = t['box']

                            # Check for horizontal overlap
                            h_overlap = max(0, min(d_x_max, t_x_max) - max(d_x_min, t_x_min))
                            if h_overlap > 0 and t_y_max <= d_y_min:
                                dist = d_y_min - t_y_max
                                if dist < min_dist:
                                    min_dist = dist
                                    best_t_idx = t_idx

                        if best_t_idx != -1:
                            # Attach to the nearest text block above
                            marker = f"\n[[{{ima_dont_del_{global_marker}}}]]\n"
                            ocr_blocks[best_t_idx]['text'] += marker
                        elif ocr_blocks:
                            # If no text block is strictly above, attach to the nearest text block by center distance
                            d_cx = (d_x_min + d_x_max) / 2
                            d_cy = (d_y_min + d_y_max) / 2
                            def distance(t):
                                t_cx = (t['box'][0] + t['box'][2]) / 2
                                t_cy = (t['box'][1] + t['box'][3]) / 2
                                return (d_cx - t_cx)**2 + (d_cy - t_cy)**2

                            marker = f"[[{{ima_dont_del_{global_marker}}}]]\n"
                            nearest_idx = min(range(len(ocr_blocks)), key=lambda i: distance(ocr_blocks[i]))
                            ocr_blocks[nearest_idx]['text'] = marker + ocr_blocks[nearest_idx]['text']
                        else:
                            # Edge case: no text in the entire page, just diagram
                            ocr_blocks.append({
                                'text': f"[[{{ima_dont_del_{global_marker}}}]]",
                                'box': d['box'],
                                'y_center': d['y_center'],
                                'type': 'TextLine'
                            })

                    # Combine all text blocks into a single page-level text payload
                    full_page_text = "\n".join([t['text'] for t in ocr_blocks])

                    # Save the full page image for vision model
                    buf_page = io.BytesIO()
                    img.save(buf_page, format='PNG')
                    page_image_b64 = base64.b64encode(buf_page.getvalue()).decode('utf-8')

                    # Package the entire page as ONE slice
                    slice_obj = {
                        "text": full_page_text,
                        "image_b64": page_image_b64,  # Whole page for vision model
                        "diagram": next(iter(diagram_map.values()), None),  # Backward-compatible default; full mapping stays in diagram_map
                        "diagram_map": diagram_map, # New field holding the diagrams for this page
                        "page_annotated_b64": page_annotated_b64
                    }

                    pending_slices.append(slice_obj)
                    if on_slice_ready:
                        try:
                            on_slice_ready(slice_obj)
                        except Exception as e:
                            logger.error(f"Error in on_slice_ready callback: {e}", exc_info=True)

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
                    logger.error(f"Error extracting image from docx: {e}", exc_info=True)
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
                        row_data = [cell.text.strip().replace("\n", " ") for cell in row.cells]
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
                logger.error(f"Error processing word element: {e}", exc_info=True)
                continue

            if len(current_text) >= 10 or current_images:
                chunks.append({
                    "text": "\n".join(current_text),
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
                "text": "\n".join(current_text) if current_text else "",
                "image_b64": "",
                "diagram": current_images[0] if current_images else None
            })
            if len(current_images) > 1:
                for extra_img in current_images[1:]:
                    chunks.append({"text": "", "image_b64": "", "diagram": extra_img})

        if not chunks:
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            text_chunks = [chunk for chunk in full_text.split("\n\n") if chunk.strip()]
            chunks = [{"text": t.replace("\n", " "), "image_b64": "", "diagram": None} for t in text_chunks]

        return chunks
