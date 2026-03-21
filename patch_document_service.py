import re

with open("document_service.py", "r", encoding="utf-8") as f:
    content = f.read()

old_logic = """# 统一排序: 按 y_center 进行从上到下的排序
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
                                bx = b['box']
                                current_boxes.append(np.array([[bx[0], bx[1]], [bx[2], bx[3]]]))
                            except Exception as e:
                                logger.warning(f"Failed to process bounding box: {e}", exc_info=True)
                        elif elem['source'] == 'diagram':
                            if current_text_chunk:
                                package_slice()
                            package_slice(diagram=elem['data']['diagram_b64'])

                    if current_text_chunk:
                        package_slice()"""

new_logic = """# --- NEW LOGIC: Match diagrams to nearest OCR text box above it ---
                    # ocr_blocks: list of dicts with 'text', 'box', 'y_center', 'type'
                    # diagrams: list of dicts with 'diagram_b64', 'box', 'type'

                    # Sort text blocks by y_min top-down
                    ocr_blocks.sort(key=lambda x: x['box'][1])

                    diagram_map = {}  # Maps globally unique marker to base64

                    for d_idx, d in enumerate(diagrams):
                        d_y_min = d['box'][1]
                        global_marker = f"{page_index}_{d_idx}"
                        diagram_map[global_marker] = d['diagram_b64']

                        best_t_idx = -1
                        min_dist = float('inf')

                        # Find the text block immediately above this diagram
                        for t_idx, t in enumerate(ocr_blocks):
                            t_y_max = t['box'][3]
                            if t_y_max <= d_y_min:
                                dist = d_y_min - t_y_max
                                if dist < min_dist:
                                    min_dist = dist
                                    best_t_idx = t_idx

                        if best_t_idx != -1:
                            # Attach to the nearest text block above
                            marker = f"\\n[[{{ima_dont_del_{global_marker}}}]]\\n"
                            ocr_blocks[best_t_idx]['text'] += marker
                        elif ocr_blocks:
                            # If no text block is above, attach to the first text block (below it)
                            marker = f"[[{{ima_dont_del_{global_marker}}}]]\\n"
                            ocr_blocks[0]['text'] = marker + ocr_blocks[0]['text']
                        else:
                            # Edge case: no text in the entire page, just diagram
                            ocr_blocks.append({
                                'text': f"[[{{ima_dont_del_{global_marker}}}]]",
                                'box': d['box'],
                                'y_center': d['y_center'],
                                'type': 'TextLine'
                            })

                    # Combine all text blocks into a single page-level text payload
                    full_page_text = "\\n".join([t['text'] for t in ocr_blocks])

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
                            logger.error(f"Error in on_slice_ready callback: {e}", exc_info=True)"""

if old_logic in content:
    content = content.replace(old_logic, new_logic)
    with open("document_service.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Patch applied to document_service.py")
else:
    print("Could not find the target code in document_service.py")
