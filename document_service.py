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
    def process_doc_with_layout(file_path, file_type, layout_predictor, ocr_engine, ocr_engine_type="Pix2Text", update_status=None, on_slice_ready=None):
        """
        使用 Surya 进行版面分析 (Pass 1) + (Surya或Pix2Text) OCR 的双层分析引擎
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
                    # PASS 1: Surya Layout 图样提取
                    # ==========================================
                    layout_boxes = []
                    diagrams = []
                    text_regions = []

                    try:
                        if layout_predictor is not None:
                            # surya LayoutPredictor
                            layout_result = layout_predictor([img])[0]
                            for poly in layout_result.bboxes:
                                box = poly.bbox
                                p_type = poly.label

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
                    # PASS 2: OCR 文字提取
                    # ==========================================
                    ocr_blocks = []
                    annotated_img = img.copy()
                    draw = ImageDraw.Draw(annotated_img)

                    if not text_regions:
                        text_regions = [{
                            'box': (0, 0, img.width, img.height),
                            'y_center': img.height / 2,
                            'type': 'FullPage'
                        }]
                    for region in text_regions:
                        try:
                            x_min, y_min, x_max, y_max = region['box']
                            crop_box = (
                                max(0, int(x_min)-2),
                                max(0, int(y_min)-2),
                                min(img.width, int(x_max)+2),
                                min(img.height, int(y_max)+2)
                            )
                            cropped_img = img.crop(crop_box)

                            b_text = ""
                            if ocr_engine_type == "Pix2Text" and ocr_engine is not None:
                                res = ocr_engine.recognize(cropped_img, return_text=True)
                                if isinstance(res, str):
                                    b_text = res
                                else:
                                    try:
                                        b_text = "".join([b.get('text', '') for b in res])
                                    except Exception:
                                        pass
                            elif ocr_engine_type == "Surya" and ocr_engine is not None:
                                # RecognitionPredictor expects list of images
                                ocr_res = ocr_engine([cropped_img])[0]
                                b_text = " ".join([line.text for line in ocr_res.text_lines])

                            b_text = b_text.replace('\n', ' ').strip()
                            if b_text:
                                ocr_blocks.append({
                                    'text': b_text,
                                    'y_center': region['y_center'],
                                    'box': region['box'],
                                    'type': region['type']
                                })

                            draw.rectangle(crop_box, outline='orange', width=2)
                            draw.text((crop_box[0], max(0, crop_box[1] - 12)), f"OCR({region['type']})", fill='orange')
                        except Exception as e:
                            logger.warning(f"Failed OCR on region: {e}")

                    for b in diagrams:
                        try:
                            x_min, y_min, x_max, y_max = b['box']
                            draw.rectangle([x_min, y_min, x_max, y_max], outline='green', width=3)
                            draw.text((x_min, max(0, y_min - 12)), f"Layout-{b['type']}", fill='green')
                        except Exception as e:
                            logger.warning(f"Failed to draw diagram box: {e}", exc_info=True)

                    buf_anno = io.BytesIO()
                    annotated_img.save(buf_anno, format='PNG')
                    page_annotated_b64 = base64.b64encode(buf_anno.getvalue()).decode('utf-8')

                    # 统一排序：按 y_center 进行从上到下的排序
                    all_elements = []
                    for b in ocr_blocks:
                        all_elements.append({'source': 'ocr', 'y_center': b['y_center'], 'data': b})
                    for d in diagrams:
                        all_elements.append({'source': 'diagram', 'y_center': d['y_center'], 'data': d})

                    all_elements.sort(key=lambda x: x['y_center'])

                    current_text_chunk = []
                    current_boxes = []

                    def package_slice(diagram=None):
                        nonlocal current_text_chunk, current_boxes
                        if not current_text_chunk and not diagram:
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
                            except Exception as e:
                                logger.warning(f"Failed to crop diagram chunks: {e}", exc_info=True)

                        slice_obj = {
                            "text": "\n".join(current_text_chunk),
                            "image_b64": chunk_img_b64,
                            "diagram": diagram,
                            "page_annotated_b64": page_annotated_b64
                        }
                        pending_slices.append(slice_obj)
                        if on_slice_ready:
                            try:
                                on_slice_ready(slice_obj)
                            except Exception as e:
                                logger.error(f"Error in on_slice_ready callback: {e}", exc_info=True)

                        current_text_chunk = []
                        current_boxes = []

                    for elem in all_elements:
                        if elem['source'] == 'ocr':
                            b = elem['data']
                            current_text_chunk.append(b['text'])
                            try:
                                bx = b['box']
                                current_boxes.append(np.array([[bx[0], bx[1]], [bx[2], bx[3]]]))
                            except Exception as e:
                                logger.warning(f"Failed to process bounding box: {e}", exc_info=True)
                        elif elem['source'] == 'diagram':
                            if current_text_chunk:
                                package_slice()
                            package_slice(diagram=elem['data']['diagram_b64'])

                    if current_text_chunk:
                        package_slice()

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
