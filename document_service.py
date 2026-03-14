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
    def process_doc_with_layout(file_path, file_type, p2t_engine, update_status=None, on_slice_ready=None):
        """
        使用 DocLayout-YOLO (Pass 1) + Pix2Text (Pass 2) 的双层版面分析引擎
        返回: pending_slices 列表，元素结构为 {"text": str, "image_b64": str, "diagram": str(图样)}
        """
        pending_slices = []

        doc = None
        try:
            total_pages = 1
            if file_type == "pdf":
                doc = fitz.open(file_path)
                total_pages = len(doc)

            yolo_engine = p2t_engine.layout_parser

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
                    # PASS 1: DocLayout-YOLO 图样提取
                    # ==========================================
                    yolo_boxes = []
                    yolo_diagrams = []
                    try:
                        if hasattr(yolo_engine, 'parse'):
                            import numpy as np
                            # p2t_engine.layout_parser (DocYoloLayoutParser) uses .parse(img)
                            predictions = yolo_engine.parse(img)
                            # returns LayoutBlock objects or dicts
                            for pred in predictions:
                                # In p2t, types are usually strings like 'figure', 'table' etc.
                                p_type = getattr(pred, 'type', pred.get('type', '')) if isinstance(pred, dict) else getattr(pred, 'type', '')

                                if p_type in ['figure', 'figure_caption', 'image']:
                                    # Get box coordinates
                                    # Sometimes it's pred.position, sometimes pred.box, or dict keys
                                    if isinstance(pred, dict) and 'box' in pred:
                                        box = pred['box']
                                        if isinstance(box, np.ndarray):
                                            box = box.flatten().tolist()
                                    elif hasattr(pred, 'position'):
                                        box = pred.position
                                        if isinstance(box, np.ndarray):
                                            # If it's 4 points [ [x,y], [x,y]... ]
                                            if box.shape == (4, 2):
                                                x_min, y_min = np.min(box, axis=0)
                                                x_max, y_max = np.max(box, axis=0)
                                                box = [x_min, y_min, x_max, y_max]
                                            elif box.size == 4:
                                                box = box.flatten().tolist()
                                            else:
                                                continue
                                    elif hasattr(pred, 'box'):
                                        box = pred.box
                                        if isinstance(box, np.ndarray):
                                            box = box.flatten().tolist()
                                    else:
                                        continue

                                    if len(box) == 4:
                                        x_min, y_min, x_max, y_max = box
                                        yolo_boxes.append({
                                            'box': box,
                                            'y_center': (box[1] + box[3]) / 2,
                                            'type': 'diagram'
                                        })
                                        # Crop and save diagram

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
                                    yolo_diagrams.append({
                                        'y_center': (box[1] + box[3]) / 2,
                                        'diagram_b64': new_diagram,
                                        'box': crop_box
                                    })
                    except Exception as e:
                        logger.error(f"DocLayout-YOLO 识别失败，跳过图样提取: {e}", exc_info=True)

                    # ==========================================
                    # PASS 2: P2T OCR 文字提取
                    # ==========================================
                    p2t_blocks = []
                    try:
                        blocks = p2t_engine.recognize(img, return_text=False)
                        if hasattr(blocks, 'blocks'): blocks = blocks.blocks
                        elif isinstance(blocks, dict) and 'blocks' in blocks: blocks = blocks['blocks']

                        for block in blocks:
                            if isinstance(block, str):
                                block = {'type': 'text', 'text': block, 'position': None}

                            b_type = block.get('type', 'text').lower()
                            b_text = block.get('text', '').replace('\n', '')
                            b_box = block.get('position', None)

                            if b_type in ['figure', 'image']:
                                # Skip P2T's figures since YOLO handles them better now
                                continue

                            if b_type in ['equation', 'isolated_equation', 'formula']:
                                if b_text.strip() and not b_text.startswith('$'):
                                    b_text = '$' + b_text + '$'

                            if b_text.strip() and b_box is not None:
                                try:
                                    box_arr = np.array(b_box).reshape(-1, 2)
                                    y_min = np.min(box_arr[:, 1])
                                    y_max = np.max(box_arr[:, 1])
                                    p2t_blocks.append({
                                        'text': b_text,
                                        'y_center': (y_min + y_max) / 2,
                                        'box': b_box,
                                        'type': b_type
                                    })
                                except Exception as e:
                                    logger.warning(f"Failed to parse P2T box: {e}", exc_info=True)
                    except Exception as e:
                        logger.error(f"P2T OCR 提取失败: {e}", exc_info=True)

                    # ==========================================
                    # 合并排序并生成 Slices
                    # ==========================================

                    # 绘制带标注的底图 (Annotated Image for UI)
                    annotated_img = img.copy()
                    draw = ImageDraw.Draw(annotated_img)
                    colors = {
                        'text': 'red', 'title': 'red', 'figure': 'green', 'table': 'blue',
                        'equation': 'purple', 'isolated_equation': 'purple', 'formula': 'purple',
                        'diagram': 'green'
                    }

                    # 画 P2T 框
                    for b in p2t_blocks:
                        try:
                            box_arr = np.array(b['box']).reshape(-1, 2)
                            x_min, y_min = np.min(box_arr, axis=0)
                            x_max, y_max = np.max(box_arr, axis=0)
                            color = colors.get(b['type'], 'orange')
                            draw.rectangle([x_min, y_min, x_max, y_max], outline=color, width=2)
                            draw.text((x_min, max(0, y_min - 12)), b['type'], fill=color)
                        except Exception:
                            pass

                    # 画 YOLO 框
                    for b in yolo_diagrams:
                        try:
                            x_min, y_min, x_max, y_max = b['box']
                            draw.rectangle([x_min, y_min, x_max, y_max], outline='green', width=3)
                            draw.text((x_min, max(0, y_min - 12)), 'YOLO-Figure', fill='green')
                        except Exception:
                            pass

                    buf_anno = io.BytesIO()
                    annotated_img.save(buf_anno, format='PNG')
                    page_annotated_b64 = base64.b64encode(buf_anno.getvalue()).decode('utf-8')

                    # 统一排序：按 y_center 进行从上到下的排序
                    all_elements = []
                    for b in p2t_blocks:
                        all_elements.append({'source': 'p2t', 'y_center': b['y_center'], 'data': b})
                    for d in yolo_diagrams:
                        all_elements.append({'source': 'yolo', 'y_center': d['y_center'], 'data': d})

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
                            except Exception:
                                pass

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
                        if elem['source'] == 'p2t':
                            b = elem['data']
                            current_text_chunk.append(b['text'])
                            try:
                                b_box_arr = np.array(b['box'])
                                if b_box_arr.size > 0 and b_box_arr.size % 2 == 0:
                                    current_boxes.append(b_box_arr.reshape(-1, 2))
                            except Exception:
                                pass
                        elif elem['source'] == 'yolo':
                            # 遇到图样，先把之前的文本打包
                            if current_text_chunk:
                                package_slice()
                            # 独立打包图样（可带上最近一小段上下文的截图，这里以空文本打出图样，后续GUI可以自动合并）
                            package_slice(diagram=elem['data']['diagram_b64'])

                    # 处理页面末尾剩余文本
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
