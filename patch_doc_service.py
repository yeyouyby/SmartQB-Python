with open("document_service.py", "r", encoding="utf-8") as f:
    content = f.read()

import re

# We will completely rewrite process_doc_with_layout to use Surya Layout and Surya/Pix2Text OCR
new_process_doc = """
    @staticmethod
    def process_doc_with_layout(file_path, file_type, layout_predictor, ocr_engine, ocr_engine_type="Pix2Text", update_status=None, on_slice_ready=None):
        \"\"\"
        使用 Surya 进行版面分析 (Pass 1) + (Surya或Pix2Text) OCR 的双层分析引擎
        返回: pending_slices 列表，元素结构为 {"text": str, "image_b64": str, "diagram": str(图样)}
        \"\"\"
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
                    # PASS 1: Surya Layout 版面提取
                    # ==========================================
                    layout_boxes = []
                    diagrams = []
                    text_regions = []

                    try:
                        if layout_predictor is not None:
                            layout_result = layout_predictor([img])[0]
                            for poly in layout_result.bboxes:
                                # poly.bbox = [x1, y1, x2, y2]
                                # poly.label = label string
                                box = poly.bbox
                                p_type = poly.label

                                # 将 table 和 equation 纳入图样截取范围
                                if p_type in ['Figure', 'Table', 'Equation']:
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
                        logger.error(f"Surya Layout 版面提取失败: {e}", exc_info=True)

                    # ==========================================
                    # PASS 2: OCR 区域文字提取
                    # ==========================================
                    ocr_blocks = []

                    # 绘制带标注的底图 (Annotated Image for UI)
                    annotated_img = img.copy()
                    draw = ImageDraw.Draw(annotated_img)

                    # 为了加速 OCR，我们可以把所有 text_regions 的截图合并起来 OCR，或者单独裁剪 OCR
                    # 如果使用的是 Pix2Text，可以直接丢给它让它自己切，或者指定坐标（P2T不支持坐标限定，只能裁出来）
                    for region in text_regions:
                        try:
                            x_min, y_min, x_max, y_max = region['box']
                            crop_box = (max(0, int(x_min)-2), max(0, int(y_min)-2), min(img.width, int(x_max)+2), min(img.height, int(y_max)+2))
                            cropped_text_img = img.crop(crop_box)

                            b_text = ""
                            if ocr_engine_type == "Pix2Text" and ocr_engine is not None:
                                # Pix2Text OCR
                                res = ocr_engine.recognize(cropped_text_img, return_text=True)
                                if isinstance(res, str):
                                    b_text = res
                                else:
                                    # Handle standard Pix2Text output
                                    b_text = "".join([b.get('text', '') for b in (res.blocks if hasattr(res, 'blocks') else res.get('blocks', []))])
                            elif ocr_engine_type == "Surya" and ocr_engine is not None:
                                # Surya OCR
                                # Surya OCR expects list of images, optionally langs
                                ocr_res = ocr_engine([cropped_text_img], langs=[["en", "zh"]])[0]
                                b_text = "".join([l.text for l in ocr_res.text_lines])

                            b_text = b_text.replace('\\n', ' ').strip()
                            if b_text:
                                ocr_blocks.append({
                                    'text': b_text,
                                    'y_center': region['y_center'],
                                    'box': region['box'],
                                    'type': region['type']
                                })

                            draw.rectangle(crop_box, outline="orange", width=2)
                            draw.text((crop_box[0], max(0, crop_box[1] - 12)), f"OCR({region['type']})", fill="orange")

                        except Exception as e:
                            logger.warning(f"Failed OCR on region: {e}")

                    # 绘制 Diagrams 框
                    for b in diagrams:
                        try:
                            x_min, y_min, x_max, y_max = b['box']
                            draw.rectangle([x_min, y_min, x_max, y_max], outline='green', width=3)
                            draw.text((x_min, max(0, y_min - 12)), f"Surya-{b['type']}", fill='green')
                        except Exception:
                            pass

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
                            except Exception:
                                pass

                        slice_obj = {
                            "text": "\\n".join(current_text_chunk),
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
                                # box is [x1, y1, x2, y2]
                                bx = b['box']
                                current_boxes.append(np.array([[bx[0], bx[1]], [bx[2], bx[3]]]))
                            except Exception:
                                pass
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
"""

content = re.sub(
    r'@staticmethod\s+def process_doc_with_layout.*?return pending_slices',
    new_process_doc,
    content,
    flags=re.DOTALL
)

with open("document_service.py", "w", encoding="utf-8") as f:
    f.write(content)
